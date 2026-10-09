#!/usr/bin/env python3
"""Download the eight official annual rainfall CSVs without loading them into RAM.

Python standard library only. For gs:// output, the authenticated gcloud CLI is
also required. --output is a project data root; raw/year=YYYY/rainfall.csv is
appended. A yearly manifest is the commit marker used for safe reruns.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
COLLECTION_URL = "https://data.gov.sg/collections/2279/view"
METADATA_URL = (
    "https://api-production.data.gov.sg/v2/public/api/collections/2279/metadata"
    "?withDatasetMetadata=true"
)
DOWNLOAD_BASE = "https://api-open.data.gov.sg/v1/public/api/datasets"
REQUIRED_COLUMNS = {"timestamp", "station_id", "reading_value"}


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def log(message):
    print(message, file=sys.stderr, flush=True)


def pause(seconds):
    """Small sleeps keep long backoffs interruptible."""
    end = time.monotonic() + max(0.0, seconds)
    while time.monotonic() < end:
        time.sleep(min(10.0, max(0.0, end - time.monotonic())))


class DownloadError(RuntimeError):
    pass


class Api:
    def __init__(self, min_interval=13.0, retries=5, timeout=120):
        self.min_interval = min_interval
        self.retries = retries
        self.timeout = timeout
        self.last_request = None
        self.key = os.environ.get("DATA_GOV_SG_API_KEY", "")

    def get(self, url):
        """Throttle every attempt, including 429 retries; never log credentials."""
        for attempt in range(self.retries + 1):
            if self.last_request is not None:
                pause(self.min_interval - (time.monotonic() - self.last_request))
            self.last_request = time.monotonic()
            headers = {"Accept": "application/json", "User-Agent": "RainfallSparkProject/1.0"}
            if self.key:
                headers["x-api-key"] = self.key
            try:
                with urlopen(Request(url, headers=headers), timeout=self.timeout) as response:
                    result = json.load(response)
                if not isinstance(result, dict):
                    raise DownloadError("API returned a non-object JSON response")
                # Check the explicit error field rather than relying on
                # undocumented numeric response-code conventions.
                if result.get("errorMsg"):
                    raise DownloadError("API reported an error; inspect official API status")
                return result
            except HTTPError as exc:
                if exc.code not in {408, 429, 500, 502, 503, 504}:
                    raise DownloadError(f"API returned HTTP {exc.code}") from None
                if attempt == self.retries:
                    raise DownloadError(f"API still returned HTTP {exc.code} after retries") from None
                retry_after = exc.headers.get("Retry-After", "")
                wait = float(retry_after) if retry_after.isdigit() else min(60, 2 ** (attempt + 2))
                log(f"API HTTP {exc.code}; retrying after {wait:.0f} s")
                pause(wait + random.uniform(0, 1))
            except (URLError, TimeoutError, OSError, ValueError):
                if attempt == self.retries:
                    raise DownloadError("API network/JSON failure after retries") from None
                pause(min(60, 2 ** (attempt + 2)))
        raise DownloadError("API retry loop exhausted")


def discover(api, config_path, years, pinned_only=False):
    with open(config_path, encoding="utf-8") as handle:
        pinned = json.load(handle)
    selected = {int(item["year"]): item for item in pinned["datasets"]}
    provenance = "pinned_official_dataset_pages"
    collection_metadata = {"collectionId": "2279", "name": "Historical Rainfall across Singapore"}
    warning = None
    if not pinned_only:
        try:
            result = api.get(METADATA_URL)
            data = result.get("data", {})
            live = {}
            for item in data.get("datasetMetadata", []):
                match = re.search(r"Historical\s+Rainfall\s+across\s+Singapore\s*\((20\d\d)\)", item.get("name", ""), re.I)
                if not match:
                    continue
                year = int(match.group(1))
                dataset_id = item.get("datasetId", "")
                if not re.fullmatch(r"d_[a-f0-9]{32}", dataset_id):
                    raise DownloadError("Live catalog contains an unexpected dataset identifier")
                if year in live:
                    raise DownloadError(f"Live catalog has multiple rainfall datasets for {year}")
                live[year] = {
                    "year": year,
                    "dataset_id": dataset_id,
                    "name": item["name"],
                    "source_url": f"https://data.gov.sg/datasets/{dataset_id}/view",
                    "metadata": item,
                }
            missing = set(years) - set(live)
            if missing:
                raise DownloadError(f"Live catalog lacks annual metadata for {sorted(missing)}")
            selected.update(live)
            provenance = "live_collection_metadata"
            collection_metadata = data.get("collectionMetadata", collection_metadata)
        except DownloadError as exc:
            warning = str(exc)
            log(f"WARNING: catalog refresh unavailable ({warning}); using verified pinned IDs")
    unavailable = set(years) - set(selected)
    if unavailable:
        raise DownloadError(f"No dataset IDs available for {sorted(unavailable)}")
    return {
        "catalog_generated_at_utc": now_iso(),
        "collection_url": COLLECTION_URL,
        "metadata_endpoint": METADATA_URL,
        "discovery_method": provenance,
        "metadata_warning": warning,
        "pinned_catalog_verified_on": pinned.get("verified_on"),
        "collection_metadata": collection_metadata,
        "datasets": [selected[year] for year in sorted(years)],
    }


class Destination:
    def __init__(self, root):
        self.root = root.rstrip("/")
        self.remote = self.root.startswith("gs://")
        if self.remote:
            if not urlsplit(self.root).netloc:
                raise DownloadError("GCS output must include a bucket: gs://BUCKET/path")
            if shutil.which("gcloud") is None:
                raise DownloadError("gcloud CLI is required for a gs:// output")
        else:
            self.root = str(Path(root).expanduser().resolve())
            Path(self.root).mkdir(parents=True, exist_ok=True)

    def path(self, relative):
        return f"{self.root}/{relative}"

    def read_json(self, relative):
        if self.remote:
            result = subprocess.run(
                ["gcloud", "storage", "cat", self.path(relative)],
                text=True, capture_output=True,
            )
            if result.returncode:
                # Missing manifests are normal on a first run. Authentication and
                # permission problems must fail, not masquerade as a fresh run.
                if re.search(r"(404|not found|No URLs matched|matched no objects|does not exist)", result.stderr, re.I):
                    return None
                raise DownloadError("Cannot read GCS manifest: " + result.stderr.strip())
            return json.loads(result.stdout)
        path = Path(self.path(relative))
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def put(self, local, relative):
        target = self.path(relative)
        if self.remote:
            subprocess.run(["gcloud", "storage", "cp", str(local), target], check=True)
        else:
            path = Path(target)
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(local, path.with_suffix(path.suffix + ".part"))
            path.with_suffix(path.suffix + ".part").replace(path)
        return target

    def write_json(self, obj, relative):
        with tempfile.TemporaryDirectory(prefix="rainfall-metadata-") as temp:
            path = Path(temp) / "metadata.json"
            path.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            self.put(path, relative)

    def verify_existing(self, relative, metadata):
        if self.remote:
            result = subprocess.run(
                ["gcloud", "storage", "objects", "describe", self.path(relative), "--format=value(size)"],
                text=True, capture_output=True,
            )
            if result.returncode:
                raise DownloadError("Year manifest exists but raw object cannot be verified; use --force to re-download")
            if int(result.stdout.strip()) != metadata["bytes"]:
                raise DownloadError("Existing GCS object size differs from manifest; use --force")
            # GCS CRC32C is checked by gcloud during upload. SHA256 is preserved in
            # the manifest; remote resume avoids re-downloading >1GB just to hash.
            return "gcs_object_size_and_original_gcloud_transfer_checksum"
        path = Path(self.path(relative))
        if not path.is_file() or path.stat().st_size != metadata["bytes"]:
            raise DownloadError("Existing local CSV differs from manifest; use --force")
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for block in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(block)
        if digest.hexdigest() != metadata["sha256"]:
            raise DownloadError("Existing local SHA256 differs from manifest; use --force")
        return "local_sha256_verified"


def download_url(api, dataset_id, poll_attempts=60):
    api.get(f"{DOWNLOAD_BASE}/{dataset_id}/initiate-download")
    for _ in range(poll_attempts):
        result = api.get(f"{DOWNLOAD_BASE}/{dataset_id}/poll-download")
        data = result.get("data", {})
        url = data.get("url")
        if url:
            if urlsplit(url).scheme != "https":
                raise DownloadError("Download service returned a non-HTTPS URL")
            return url
        if str(data.get("status", "")).lower() in {"error", "failed", "failure"}:
            raise DownloadError("Server could not prepare the annual CSV")
        log(f"{dataset_id}: server is preparing the CSV")
    raise DownloadError("CSV not ready within polling limit; rerun later")


def stream_csv(url, target, timeout):
    """Stream bytes and hash; temporary URL and API key are never persisted."""
    digest = hashlib.sha256()
    count = 0
    last_log = time.monotonic()
    req = Request(url, headers={"User-Agent": "RainfallSparkProject/1.0"})
    with urlopen(req, timeout=timeout) as response, target.open("wb") as handle:
        expected = int(response.headers["Content-Length"]) if response.headers.get("Content-Length") else None
        if expected is not None and shutil.disk_usage(target.parent).free < expected + 100 * 1024**2:
            raise DownloadError("Insufficient scratch disk for one annual CSV; choose --work-dir on a larger disk")
        for block in iter(lambda: response.read(4 * 1024 * 1024), b""):
            handle.write(block)
            digest.update(block)
            count += len(block)
            if time.monotonic() - last_log >= 30:
                log(f"  downloaded {count / 1024**2:.0f} MiB")
                last_log = time.monotonic()
    if expected is not None and count != expected:
        raise DownloadError("Download was truncated (Content-Length mismatch)")
    if count == 0:
        raise DownloadError("Downloaded file is empty")
    with target.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        columns = next(reader)
        normalized = {re.sub(r"\s+", "_", col.strip().lower()) for col in columns}
        if not REQUIRED_COLUMNS.issubset(normalized):
            raise DownloadError("Downloaded response is not the expected rainfall CSV (invalid header)")
        first = next(reader, None)
        if first is None or len(first) != len(columns):
            raise DownloadError("Downloaded CSV has no valid first data row")
    parts = urlsplit(url)
    return {
        "bytes": count,
        "sha256": digest.hexdigest(),
        "header_columns": columns,
        "download_host": parts.netloc,
        "download_resource_without_query": urlunsplit((parts.scheme, parts.netloc, parts.path, "", "")),
    }


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--output", required=True, help="Data root (local directory or gs://bucket/prefix); raw/year=YYYY is appended")
    parser.add_argument("--years", type=int, nargs="+", default=list(range(2017, 2025)))
    parser.add_argument("--catalog", type=Path, default=ROOT / "config" / "datasets.json")
    parser.add_argument("--catalog-only", action="store_true", help="Save catalog.json; do not initiate large CSV downloads")
    parser.add_argument("--pinned-only", action="store_true", help="Skip metadata refresh; use the verified checked-in catalog")
    parser.add_argument("--force", action="store_true", help="Replace already completed annual files")
    parser.add_argument("--work-dir", type=Path, help="Temporary disk with space for one annual file (default: system temp)")
    parser.add_argument("--min-interval", type=float, default=13, help="API spacing in seconds; minimum 13")
    parser.add_argument("--retries", type=int, default=5)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--poll-attempts", type=int, default=60)
    args = parser.parse_args(argv)
    if any(year < 2017 or year > 2024 for year in args.years):
        parser.error("This project uses only annual datasets from 2017 through 2024")
    if args.min_interval < 13 or args.retries < 0 or args.timeout <= 0 or args.poll_attempts <= 0:
        parser.error("--min-interval must be >=13; retries >=0; timeout and poll-attempts >0")
    args.years = sorted(set(args.years))
    return args


def main(argv=None):
    args = parse_args(argv)
    destination = Destination(args.output)
    api = Api(args.min_interval, args.retries, args.timeout)
    catalog = discover(api, args.catalog, args.years, args.pinned_only)
    destination.write_json(catalog, "catalog.json")
    if args.catalog_only:
        log(f"Catalog saved: {destination.path('catalog.json')}")
        return 0
    completed = []
    if args.work_dir:
        args.work_dir.mkdir(parents=True, exist_ok=True)
    for item in catalog["datasets"]:
        year, dataset_id = item["year"], item["dataset_id"]
        relative = f"raw/year={year}/rainfall.csv"
        manifest_relative = f"manifests/{year}.json"
        prior = destination.read_json(manifest_relative)
        if prior and not args.force:
            if prior.get("dataset_id") != dataset_id:
                raise DownloadError(f"Dataset ID changed for {year}; inspect catalog and explicitly rerun with --force")
            verification = destination.verify_existing(relative, prior)
            log(f"{year}: already complete ({verification}), skipping")
            completed.append(prior)
        else:
            log(f"{year}: downloading {item['name']}")
            with tempfile.TemporaryDirectory(prefix=f"rainfall-{year}-", dir=args.work_dir) as temp:
                local = Path(temp) / "rainfall.csv"
                for attempt in range(args.retries + 1):
                    try:
                        # Refresh the signed URL on each retry. Do not retain a
                        # partial payload or append potentially duplicated bytes.
                        url = download_url(api, dataset_id, args.poll_attempts)
                        file_metadata = stream_csv(url, local, args.timeout)
                        break
                    except (HTTPError, URLError, TimeoutError, OSError, UnicodeError, csv.Error, DownloadError) as exc:
                        local.unlink(missing_ok=True)
                        if attempt == args.retries:
                            detail = str(exc) if isinstance(exc, DownloadError) else type(exc).__name__
                            raise DownloadError(f"{year}: download failed after retries ({detail}); check network/service and disk") from None
                        log(f"{year}: transfer failed ({type(exc).__name__}); retrying from the beginning")
                        pause(min(60, 2 ** (attempt + 2)))
                destination.put(local, relative)
                entry = {
                    "year": year,
                    "dataset_id": dataset_id,
                    "source_url": item["source_url"],
                    "collection_url": COLLECTION_URL,
                    "downloaded_at_utc": now_iso(),
                    "destination": destination.path(relative),
                    "dataset_metadata": item.get("metadata", item),
                    "catalog_discovery_method": catalog["discovery_method"],
                    **file_metadata,
                }
                destination.write_json(entry, manifest_relative)
                completed.append(entry)
                log(f"{year}: saved {file_metadata['bytes'] / 1024**2:.1f} MiB, SHA256 {file_metadata['sha256']}")
            # Successful years are committed only after upload and manifest.
            # Temporary files are cleaned on success or failure; reruns use the
            # manifest to skip complete years and retry uncommitted years.
        destination.write_json({
            "updated_at_utc": now_iso(),
            "requested_years": args.years,
            "datasets": completed,
            "note": "This summary describes this invocation. manifests/YYYY.json are the authoritative per-year records.",
        }, "manifest.json")
    log(f"Done. Raw CSVs: {destination.path('raw/year=*/rainfall.csv')}")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (DownloadError, subprocess.CalledProcessError, json.JSONDecodeError) as exc:
        log(f"ERROR: {exc}")
        sys.exit(1)

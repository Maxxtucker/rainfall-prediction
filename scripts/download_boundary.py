#!/usr/bin/env python3
"""Download a Singapore outline with source/license metadata (not rainfall data)."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from urllib.request import Request, urlopen

API = "https://www.geoboundaries.org/api/current/gbOpen/SGP/ADM0/"


def fetch(url):
    with urlopen(Request(url, headers={"User-Agent": "rainfall-course-project/1.0"}), timeout=120) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("assets/singapore.geojson"))
    parser.add_argument("--level", choices=["ADM0", "ADM2"], default="ADM0")
    args = parser.parse_args()
    api = API.replace("ADM0/", args.level + "/")
    metadata = json.loads(fetch(api))
    payload = fetch(metadata["gjDownloadURL"])
    boundary = json.loads(payload)
    if boundary.get("type") != "FeatureCollection" or not boundary.get("features"):
        raise ValueError("Expected a non-empty GeoJSON FeatureCollection")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_bytes(payload)
    metadata.update({"retrieved_utc": datetime.now(timezone.utc).isoformat(),
                     "metadata_url": api, "sha256": hashlib.sha256(payload).hexdigest()})
    args.output.with_suffix(".source.json").write_text(json.dumps(metadata, indent=2))
    print(args.output.resolve())
    print("Source:", metadata["boundarySource"], "License:", metadata["boundaryLicense"])
    print("Boundary reference year:", metadata["boundaryYearRepresented"], "(not annual coastline reconstruction)")


if __name__ == "__main__":
    main()

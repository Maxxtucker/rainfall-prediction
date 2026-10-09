#!/usr/bin/env python3
"""Plot LOCAL Spark aggregate CSVs as PNGs; no PDF or generated narrative.
Example: python scripts/plot_results.py --results outputs --output figures
For cleaning only, use --results outputs/steps/clean-all-v1.
"""
import argparse
import calendar
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

NAVY = "#123149"
TEAL = "#087F8C"
TABLES = ["annual_common", "monthly_common", "hourly", "station_year",
          "reliability", "feature_importance", "rainfall_distribution",
          "rainfall_positive_histogram", "comparison_policy"]

def find_input(root: Path | None, name: str) -> Path | None:
    if root is None:
        return None
    for base in (root, root / "eda", root / "metrics", root / "model" / "metrics",
                 root / "output" / "eda"):
        for candidate in (base / name, base / (name + ".csv")):
            if candidate.exists():
                return candidate
    hits = [p for p in root.rglob("*") if p.name in (name, name + ".csv")
            and not any(x.startswith(".") for x in p.relative_to(root).parts)]
    if len(hits) > 1:
        raise ValueError(f"Multiple inputs named {name}: {hits}. Pass one run's result directory.")
    return hits[0] if hits else None


def read_csv(path: Path | None) -> pd.DataFrame:
    if path is None:
        return pd.DataFrame()
    files = [path] if path.is_file() else sorted(path.glob("part-*.csv"))
    if path.is_dir() and not files:
        files = sorted(path.glob("*.csv"))
    frames = []
    for file in files:
        try:
            frames.append(pd.read_csv(file))
        except pd.errors.EmptyDataError:
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def require(df: pd.DataFrame, columns: list[str]) -> bool:
    return not df.empty and set(columns).issubset(df.columns)


def prepare_figures(data: dict[str, pd.DataFrame], outdir: Path) -> dict[str, Path]:
    outdir.mkdir(parents=True, exist_ok=True)
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 9,
                         "axes.spines.top": False, "axes.spines.right": False,
                         "axes.labelcolor": NAVY, "text.color": NAVY,
                         "axes.titleweight": "bold", "figure.facecolor": "white",
                         "savefig.facecolor": "white"})
    figures = {}

    def save(name, fig):
        path = outdir / (name + ".png")
        fig.savefig(path, dpi=180, bbox_inches="tight")
        plt.close(fig)
        figures[name] = path

    policy = data.get("comparison_policy", pd.DataFrame())
    matched = not policy.empty and "comparison_months" in policy
    df = data["annual_common"]
    if require(df, ["year", "mean_station_rainfall_mm"]):
        d = df.sort_values("year")
        fig, ax = plt.subplots(figsize=(9, 3.1))
        ax.bar(d.year.astype(str), d.mean_station_rainfall_mm, color=TEAL, width=.6)
        ax.set(xlabel="Year (SGT)", ylabel="Mean observed total per station (mm)",
               title=(f"Matched-month rainfall (not annual): {policy.iloc[0].comparison_months}"
                      if matched else "Annual rainfall: fixed eligible station panel"))
        ax.grid(axis="y", alpha=.18)
        for i, row in enumerate(d.itertuples()):
            ax.annotate(f"{row.mean_station_rainfall_mm:,.0f}", (i, row.mean_station_rainfall_mm),
                        xytext=(0, 4), textcoords="offset points", ha="center", fontsize=8)
        ax.set_ylim(0, max(d.mean_station_rainfall_mm.max() * 1.17, 1))
        save("annual_common", fig)

    df = data["monthly_common"]
    if require(df, ["year", "month", "mean_station_rainfall_mm"]):
        pivot = df.pivot(index="year", columns="month", values="mean_station_rainfall_mm")
        pivot = pivot.reindex(index=range(2017, 2025), columns=range(1, 13))
        fig, ax = plt.subplots(figsize=(9, 3.25))
        im = ax.imshow(np.ma.masked_invalid(pivot.to_numpy(float)), aspect="auto", cmap="YlGnBu")
        ax.set_xticks(range(12), [calendar.month_abbr[i] for i in range(1, 13)])
        ax.set_yticks(range(8), range(2017, 2025))
        ax.set(title="Monthly rainfall: fixed eligible station panel", xlabel="Month (SGT)", ylabel="Year")
        fig.colorbar(im, ax=ax, label="Mean observed station total (mm)", fraction=.032, pad=.03)
        save("monthly_common", fig)

    df = data["hourly"]
    if require(df, ["year", "hour", "wet_fraction"]):
        fig, ax = plt.subplots(figsize=(9, 3.0))
        palette = plt.get_cmap("viridis")
        years = sorted(df.year.dropna().unique())
        for i, year in enumerate(years):
            d = df[df.year == year].sort_values("hour")
            ax.plot(d.hour, 100 * d.wet_fraction, label=str(int(year)), linewidth=1.6,
                    color=palette(i / max(len(years) - 1, 1)))
        ax.set(xlabel="Hour of day (SGT)", ylabel="Observed five-minute intervals with rain (%)",
               title="Diurnal wet-interval frequency: available station network", xlim=(0, 23))
        ax.set_xticks(range(0, 24, 2)); ax.grid(alpha=.15)
        ax.legend(ncol=4, fontsize=7.5, loc="best", frameon=False)
        save("hourly", fig)

    df = data["station_year"]
    if require(df, ["station_id", "year", "coverage"]):
        pivot = df.pivot(index="station_id", columns="year", values="coverage")
        pivot = pivot.reindex(columns=range(2017, 2025)).sort_index()
        fig, ax = plt.subplots(figsize=(9, 3.8))
        im = ax.imshow(np.ma.masked_invalid(pivot.to_numpy(float)), aspect="auto", vmin=0, vmax=1,
                       cmap="YlGnBu", interpolation="nearest")
        ax.set_xticks(range(8), range(2017, 2025))
        tick = max(1, len(pivot) // 16)
        ax.set_yticks(range(0, len(pivot), tick), pivot.index[::tick], fontsize=7)
        ax.set(title="Station coverage before common-panel selection", xlabel="Year", ylabel="Station ID")
        fig.colorbar(im, ax=ax, label="Valid observations / full calendar grid", fraction=.032, pad=.03)
        save("coverage", fig)

    df = data["reliability"]
    if require(df, ["model", "threshold", "mean_probability", "event_rate", "n"]):
        if "split" in df.columns and (df.split == "test").any():
            df = df[df.split == "test"]
        thresholds = sorted(df.threshold.dropna().unique())
        selected = [q for q in [0, 5, 10] if q in thresholds] or thresholds[:3]
        if selected:
            fig, axes = plt.subplots(1, len(selected), figsize=(9, 3.0), squeeze=False)
            for ax, q in zip(axes[0], selected):
                ax.plot([0, 1], [0, 1], color="#9AA7AF", linestyle="--", linewidth=1)
                d = df[df.threshold == q]
                for model, rows in d.groupby("model"):
                    rows = rows.sort_values("mean_probability")
                    ax.plot(rows.mean_probability, rows.event_rate, marker="o", markersize=3,
                            label=str(model).replace("_", " "), linewidth=1)
                ax.set(xlabel="Mean predicted probability", ylabel="Observed event frequency",
                       title=f"Rainfall > {q:g} mm", xlim=(0, 1), ylim=(0, 1))
                ax.grid(alpha=.15)
            handles, labels = axes[0, 0].get_legend_handles_labels()
            fig.legend(handles, labels, loc="lower center", bbox_to_anchor=(.5, -.12),
                       ncol=min(3, max(len(labels), 1)), fontsize=7, frameon=False)
            fig.tight_layout()
            save("reliability", fig)

    df = data["feature_importance"]
    name = next((x for x in ["feature", "feature_name", "name"] if x in df.columns), None)
    val = next((x for x in ["importance", "value"] if x in df.columns), None)
    if not df.empty and name and val:
        d = df.nlargest(12, val).sort_values(val)
        fig, ax = plt.subplots(figsize=(9, 3.5))
        ax.barh(d[name].astype(str), d[val], color=TEAL)
        ax.set(xlabel="RF impurity importance (descriptive, not causal)", title="Most-used model features")
        ax.grid(axis="x", alpha=.15)
        save("feature_importance", fig)
    return figures


def plot_distribution(data, outdir):
    paths = {}
    summary = data["rainfall_distribution"]
    if require(summary, ["year", "zero_fraction"]):
        d = summary.sort_values("year")
        fig, ax = plt.subplots(figsize=(9, 3))
        ax.bar(d.year.astype(str), 100 * d.zero_fraction, color=TEAL)
        ax.set(xlabel="Year (SGT)", ylabel="Zero-rain observations (%)",
               title="Zero rainfall among valid observations")
        fig.tight_layout()
        path = outdir / "rainfall_zero_fraction.png"
        fig.savefig(path, dpi=180); plt.close(fig)
        paths["rainfall_zero_fraction"] = path
    columns = ["positive_p50_mm", "positive_p95_mm", "positive_p99_mm", "positive_p999_mm"]
    if require(summary, ["year"] + columns):
        d = summary.sort_values("year")
        fig, ax = plt.subplots(figsize=(9, 3))
        for col, label in zip(columns, ["P50", "P95", "P99", "P99.9"]):
            ax.plot(d.year, d[col], marker="o", label=label)
        ax.set(xlabel="Year (SGT)", ylabel="Five-minute rainfall (mm)",
               title="Approximate quantiles of positive rainfall only")
        ax.legend(); ax.grid(alpha=.15); fig.tight_layout()
        path = outdir / "rainfall_positive_quantiles.png"
        fig.savefig(path, dpi=180); plt.close(fig)
        paths["rainfall_positive_quantiles"] = path
    histogram = data["rainfall_positive_histogram", "comparison_policy"]
    if require(histogram, ["year", "lower_mm", "count"]):
        fig, ax = plt.subplots(figsize=(9, 3))
        for year, rows in histogram.groupby("year"):
            rows = rows.sort_values("lower_mm")
            ax.plot(rows.lower_mm, rows["count"], marker="o", label=str(int(year)))
        ax.set_xscale("log"); ax.set_yscale("log")
        ax.set(xlabel="Bin lower edge (mm); bins [x, 10x)", ylabel="Positive observations",
               title="Positive five-minute rainfall distribution (logarithmic bins)")
        ax.legend(ncol=4, fontsize=7); fig.tight_layout()
        path = outdir / "rainfall_positive_histogram.png"
        fig.savefig(path, dpi=180); plt.close(fig)
        paths["rainfall_positive_histogram", "comparison_policy"] = path
    return paths


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True, help="LOCAL results from ONE experiment")
    parser.add_argument("--output", type=Path, default=Path("figures"))
    args = parser.parse_args()
    if not args.results.is_dir():
        parser.error("Results directory does not exist; collect Spark outputs first.")
    data = {name: read_csv(find_input(args.results, name)) for name in TABLES}
    figures = prepare_figures(data, args.output)
    figures.update(plot_distribution(data, args.output))
    if not figures:
        raise SystemExit("No plottable aggregate results found. No placeholder figures generated.")
    for name, path in figures.items():
        print(f"{name}: {path.resolve()}")


if __name__ == "__main__":
    main()

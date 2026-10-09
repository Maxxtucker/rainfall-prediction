#!/usr/bin/env python3
"""Create Task 1 PNG/SVG figures and an interactive spatial explorer from Spark tables.
No PDF, raw-data collection, geographic extrapolation, or automatic outlier deletion.
"""
import argparse
import calendar
import html
import json
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as PolygonPath
from matplotlib.colors import Normalize, TwoSlopeNorm, PowerNorm
import numpy as np
import pandas as pd
from scipy.spatial import Delaunay, QhullError, cKDTree

from plot_results import find_input, read_csv, require

INK, TEAL, CORAL, BLUE = "#18354A", "#008C95", "#E97961", "#3776A8"
TABLES = ["annual_common", "monthly_common", "station_year", "station_month",
          "hourly_common", "month_hour_common", "spatial_year_common",
          "spatial_month_common", "daily_distribution_common", "daily_extremes",
          "annual_available_qualified", "common_stations", "station_metadata_changes",
          "monthly_available_qualified", "comparison_policy", "month_comparison_stations", "spatial_year_available"]
CAPTIONS = {}


def style():
    plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 10,
        "text.color": INK, "axes.labelcolor": INK, "axes.edgecolor": "#C6D2D8",
        "axes.titleweight": "bold", "axes.spines.top": False,
        "axes.spines.right": False, "axes.facecolor": "#F6F9FA",
        "figure.facecolor": "white", "savefig.facecolor": "white",
        "grid.color": "#D7E0E5", "grid.alpha": .6, "svg.fonttype": "none"})


class Gallery:
    def __init__(self, output, label):
        self.output = output
        self.output.mkdir(parents=True, exist_ok=True)
        self.label = label
        self.figures = {}
        self.skipped = []

    def save(self, name, fig, title, subtitle, note):
        fig.suptitle(title, x=.06, ha="left", fontsize=19, fontweight="bold", color=INK, y=.99)
        fig.text(.06, .90, subtitle, ha="left", fontsize=10, color="#587183")
        fig.text(.06, .025, textwrap.fill(f"{self.label}  |  {note}", width=160), fontsize=8, color="#587183", va="bottom")
        fig.subplots_adjust(top=.84, bottom=max(.15, 1.2 / fig.get_size_inches()[1]), left=.08, right=.87)
        for extension in ["png", "svg"]:
            fig.savefig(self.output / f"{name}.{extension}", dpi=260, bbox_inches="tight")
        plt.close(fig)
        self.figures[name] = {"title": title, "note": note, "png": f"{name}.png", "svg": f"{name}.svg"}


def heatmap(ax, pivot, cmap, label, fmt=None, center=False, fixed_limits=None):
    values = pivot.to_numpy(float)
    valid = values[np.isfinite(values)]
    norm = None
    if center:
        bound = max(float(np.max(np.abs(valid))) if valid.size else 0., .01)
        norm = TwoSlopeNorm(vmin=-bound, vcenter=0, vmax=bound)
    elif fixed_limits:
        norm = Normalize(*fixed_limits)
    colors = plt.get_cmap(cmap).copy(); colors.set_bad("#E2E8EB")
    im = ax.imshow(np.ma.masked_invalid(values), aspect="auto", cmap=colors, norm=norm)
    ax.set_xticks(range(len(pivot.columns)), pivot.columns)
    ax.set_yticks(range(len(pivot.index)), pivot.index)
    if fmt:
        for i, j in np.ndindex(values.shape):
            if np.isfinite(values[i, j]):
                ax.text(j, i, format(values[i, j], fmt), ha="center", va="center", fontsize=8,
                        color="white" if im.norm(values[i, j]) > .65 else INK)
    ax.figure.colorbar(im, ax=ax, label=label, fraction=.03, pad=.025)
    return im


def temporal(data, gallery):
    annual = data["annual_common"]
    if "year" in annual: annual = annual.sort_values("year")
    if require(annual, ["year", "mean_station_rainfall_mm", "wet_fraction", "mean_wet_interval_mm"]):
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        specs = [("mean_station_rainfall_mm", "Matched-month observed total (mm)", TEAL, 1),
                 ("wet_fraction", "Wet five-minute observations (%)", BLUE, 100),
                 ("mean_wet_interval_mm", "Mean amount per wet interval (mm)", CORAL, 1)]
        for ax, (col, ylabel, color, factor) in zip(axes, specs):
            y = annual[col] * factor
            ax.bar(annual.year.astype(str), y, color=color, width=.64)
            ax.set_ylabel(ylabel); ax.grid(axis="y"); ax.set_axisbelow(True)
            ax.tick_params(axis="x", rotation=35)
            for x, value in enumerate(y):
                if pd.notna(value): ax.annotate(f"{value:,.1f}", (x, value), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=8)
            ax.set_ylim(0, max(y.max() * 1.2 if y.notna().any() else 1, .01))
        gallery.save("01_annual_amount_frequency_intensity", fig, "Rainfall across years in matched calendar months",
                     "Amount, wet-interval frequency and intensity must be interpreted together",
                     "Same station panel and calendar months each year; partial-year totals, no gap filling; not area-weighted rainfall.")
    else:
        gallery.skipped.append("matched-month year comparison: no eligible fixed panel")
    monthly = data["monthly_available_qualified"]
    if require(monthly, ["year", "month", "mean_station_rainfall_mm", "wet_fraction", "mean_wet_interval_mm"]):
        pivot = monthly.pivot(index="year", columns="month", values="mean_station_rainfall_mm").reindex(index=range(2017, 2025), columns=range(1, 13))
        fig, ax = plt.subplots(figsize=(13, 6))
        display = pivot.copy(); display.columns = [calendar.month_abbr[x] for x in display.columns]
        heatmap(ax, display, "YlGnBu", "Mean observed station total (mm)", ".0f")
        gallery.save("02_year_month_rainfall", fig, "The seasonal fingerprint of each year",
                     "A shared colour scale reveals unusually wet and dry months", "Station-month coverage meets the saved threshold; station composition varies; grey = unavailable. See monthly sample-size figure.")
        baseline = pivot.mean(axis=0)
        anomalies = (pivot - baseline).divide(baseline.where(baseline > 0), axis=1) * 100
        fig, ax = plt.subplots(figsize=(13, 6))
        display = anomalies.copy(); display.columns = [calendar.month_abbr[x] for x in display.columns]
        heatmap(ax, display, "BrBG", "Departure from 2017–2024 same-month mean (%)", ".0f", center=True)
        gallery.save("03_monthly_relative_anomalies", fig, "Which months departed from their usual pattern?",
                     "Each month is compared with its mean over eligible years", "Eligible-year reference, not a climate normal; changing stations and missing years can affect anomalies; zero baselines blank.")
        fig, axes = plt.subplots(1, 3, figsize=(15, 5))
        for ax, col, ylabel, factor, color in zip(axes,
                ["mean_station_rainfall_mm", "wet_fraction", "mean_wet_interval_mm"],
                ["Monthly total (mm)", "Wet intervals (%)", "Wet-interval amount (mm)"],
                [1, 100, 1], [TEAL, BLUE, CORAL]):
            p = monthly.pivot(index="year", columns="month", values=col).reindex(columns=range(1, 13)) * factor
            ax.fill_between(range(1, 13), p.min(), p.max(), color=color, alpha=.13, label="Range across years")
            ax.plot(range(1, 13), p.mean(), color=color, marker="o", linewidth=2.5, label="Eligible-year mean")
            ax.set_xticks(range(1, 13), list(calendar.month_abbr)[1:], rotation=60)
            ax.set_ylabel(ylabel); ax.grid(axis="y"); ax.legend(fontsize=8)
        gallery.save("04_seasonal_amount_frequency_intensity", fig, "More rain: more often, or more intense?",
                     "Monthly averages with the observed range across years", "Qualified station-months; station composition and number of eligible years vary. Shading is range, not confidence interval; month lengths differ.")
    hours = data["hourly_common"]
    if require(hours, ["year", "hour", "wet_fraction"]):
        fig, axes = plt.subplots(1, 2, figsize=(14, 5))
        palette = plt.get_cmap("viridis")
        for i, (year, d) in enumerate(hours.groupby("year")):
            d = d.sort_values("hour")
            axes[0].plot(d.hour, d.wet_fraction * 100, color=palette(i / 7), linewidth=1.8, label=str(int(year)))
        axes[0].set(xlabel="Hour (SGT)", ylabel="Wet observations (%)", xticks=range(0, 24, 3))
        axes[0].legend(ncol=4, fontsize=8); axes[0].grid()
        p = hours.pivot(index="year", columns="hour", values="wet_fraction").reindex(index=range(2017, 2025), columns=range(24)) * 100
        heatmap(axes[1], p, "YlGnBu", "Wet observations (%)")
        axes[1].set_xlabel("Hour (SGT)")
        gallery.save("05_diurnal_by_year", fig, "When during the day does rain occur?",
                     "Same stations and matched calendar months in every year", "Frequency is weighted by valid observation exposure; missingness can still bias results.")
    mh = data["month_hour_common"]
    if require(mh, ["month", "hour", "mean_station_year_wet_fraction", "mean_station_year_wet_interval_mm"]):
        fig, axes = plt.subplots(1, 2, figsize=(15, 6))
        for ax, col, factor, label in zip(axes,
                ["mean_station_year_wet_fraction", "mean_station_year_wet_interval_mm"],
                [100, 1], ["Wet observations (%)", "Mean wet-interval amount (mm)"]):
            p = mh.pivot(index="month", columns="hour", values=col).reindex(index=range(1, 13), columns=range(24)) * factor
            p.index = list(calendar.month_abbr)[1:]
            heatmap(ax, p, "YlGnBu", label)
            ax.set_xlabel("Hour (SGT)")
        gallery.save("06_month_hour_frequency_intensity", fig, "Season and time of day interact",
                     "Wet frequency and wet intensity answer different questions",
                     "Equal station-year group means; each station-month-hour group needs >=90% coverage; intensity excludes groups with no wet intervals.")
    daily = data["daily_distribution_common"]
    if require(daily, ["year", "p95_daily_mm", "p99_daily_mm", "wet_day_fraction"]):
        fig, axes = plt.subplots(1, 2, figsize=(13, 5))
        for col, label, color in [("p95_daily_mm", "P95", TEAL), ("p99_daily_mm", "P99", CORAL)]:
            axes[0].plot(daily.year, daily[col], marker="o", linewidth=2.5, color=color, label=label)
        axes[0].set(xlabel="Year", ylabel="Daily station rainfall (mm)"); axes[0].legend(); axes[0].grid()
        axes[1].bar(daily.year.astype(str), daily.wet_day_fraction * 100, color=BLUE)
        axes[1].set_ylabel("Qualified station days with rain (%)"); axes[1].grid(axis="y")
        gallery.save("07_daily_tails_and_wet_days", fig, "The upper tail and the frequency of wet days",
                     "Daily extremes complement the five-minute distribution checks",
                     "Matched-month panel station days with >=95% coverage; approximate quantiles include dry days; values remain unadjusted for gaps.")


def coverage(data, gallery):
    yearly = data["station_year"]
    if require(yearly, ["station_id", "year", "coverage"]):
        p = yearly.pivot(index="station_id", columns="year", values="coverage").reindex(columns=range(2017, 2025)) * 100
        panels = np.array_split(np.arange(len(p)), max(1, int(np.ceil(len(p) / 40))))
        fig, axes = plt.subplots(1, len(panels), figsize=(max(12, 5 * len(panels)), 10), squeeze=False)
        for ax, indices in zip(axes.ravel(), panels):
            heatmap(ax, p.iloc[indices], "YlGnBu", "Coverage (%)", fixed_limits=(0, 100))
            ax.tick_params(axis="y", labelsize=8)
            ax.tick_params(axis="x", rotation=45)
        fig.subplots_adjust(wspace=.65)
        gallery.save("08_station_coverage", fig, "Check the observing network before interpreting trends",
                     "All stations, split into readable panels", "Zero coverage can mean an inactive station or missing records; it does not mean zero rainfall.")
    monthly = data["station_month"]
    if require(monthly, ["station_id", "year", "month", "coverage", "observed_intervals"]):
        active = monthly[monthly.observed_intervals > 0]
        summary = active.groupby(["year", "month"]).agg(
            median_coverage=("coverage", "median"),
            active_stations=("station_id", "nunique"))
        grid = pd.MultiIndex.from_product([range(2017, 2025), range(1, 13)], names=["year", "month"])
        summary = summary.reindex(grid)
        summary.to_csv(gallery.output / "monthly_coverage_summary.csv")
        fig, axes = plt.subplots(2, 1, figsize=(14, 11))
        for ax, column, factor, label, fmt, fixed in [
            (axes[0], "median_coverage", 100, "Median coverage (%)", ".1f", (0, 100)),
            (axes[1], "active_stations", 1, "Stations with observations", ".0f", None)]:
            pivot = summary[column].unstack() * factor
            pivot.columns = list(calendar.month_abbr)[1:]
            heatmap(ax, pivot, "YlGnBu", label, fmt, fixed_limits=fixed)
        gallery.save("08b_monthly_coverage", fig, "Where are the gaps in the observation calendar?",
            "Monthly median coverage and number of active stations",
            "Median excludes stations with no observations in that month. Grey = no active stations; gaps are not dry weather.")
    eligible = data["monthly_available_qualified"]
    if require(eligible, ["year", "month", "stations"]):
        fig, ax = plt.subplots(figsize=(13, 6))
        pivot = eligible.pivot(index="year", columns="month", values="stations").reindex(index=range(2017, 2025), columns=range(1, 13))
        pivot.columns = list(calendar.month_abbr)[1:]
        heatmap(ax, pivot, "YlGnBu", "Qualified stations", ".0f")
        gallery.save("09_monthly_analysis_support", fig, "Which months support the seasonal analysis?",
            "Counts of stations meeting the station-month coverage threshold",
            "Grey cells have no qualified station-months. This panel varies over time; consult comparison_policy.csv for the fixed matched-month panel.")


def polygons(boundary):
    result = []
    for feature in boundary.get("features", []):
        geometry = feature["geometry"]
        if geometry["type"] == "Polygon": result.append(geometry["coordinates"])
        elif geometry["type"] == "MultiPolygon": result.extend(geometry["coordinates"])
    if not result: raise ValueError("Boundary contains no Polygon/MultiPolygon geometries")
    return result


def land_mask(x, y, rings):
    points = np.column_stack([np.asarray(x).ravel(), np.asarray(y).ravel()])
    mask = np.zeros(len(points), dtype=bool)
    for polygon in rings:
        inside = PolygonPath(np.array(polygon[0])[:, :2]).contains_points(points)
        for hole in polygon[1:]: inside &= ~PolygonPath(np.array(hole)[:, :2]).contains_points(points)
        mask |= inside
    return mask.reshape(np.shape(x))


def interpolate(stations, x, y, rings, max_distance_km):
    # Local equirectangular coordinates suffice for distances across Singapore.
    d = stations.groupby(["longitude", "latitude"], as_index=False).rainfall_total_mm.mean()
    scale = np.array([111.32 * np.cos(np.deg2rad(1.35)), 111.32])
    coordinates = d[["longitude", "latitude"]].to_numpy() * scale
    points = np.column_stack([x.ravel(), y.ravel()]) * scale
    if len(coordinates) < 3: return None
    try: hull = Delaunay(coordinates)
    except QhullError: return None
    distances, indices = cKDTree(coordinates).query(points, k=min(6, len(coordinates)))
    distances = np.maximum(distances, 1e-8)
    weights = 1 / distances ** 2
    values = (weights * d.rainfall_total_mm.to_numpy()[indices]).sum(axis=1) / weights.sum(axis=1)
    valid = (hull.find_simplex(points) >= 0) & (distances[:, 0] <= max_distance_km) & land_mask(x, y, rings).ravel()
    return np.where(valid, values, np.nan).reshape(x.shape)


def spatial(data, gallery, boundary_path, max_distance_km, regions_path=None):
    station_year = data["spatial_year_common"]
    if not require(station_year, ["station_id", "year", "latitude", "longitude", "rainfall_total_mm", "coverage"]):
        gallery.skipped.append("spatial figures: no eligible common-panel station coordinates")
        return
    if boundary_path is None or not boundary_path.is_file():
        gallery.skipped.append("spatial figures: supply --boundary assets/singapore.geojson (download_boundary.py)")
        return
    boundary = json.loads(boundary_path.read_text())
    rings = polygons(boundary)
    vertices = np.concatenate([np.array(p[0])[:, :2] for p in rings])
    limits = [vertices[:, 0].min()-.015, vertices[:, 0].max()+.015,
              vertices[:, 1].min()-.015, vertices[:, 1].max()+.015]
    x, y = np.meshgrid(np.linspace(limits[0], limits[1], 200), np.linspace(limits[2], limits[3], 130))
    source_file = boundary_path.with_suffix(".source.json")
    source = json.loads(source_file.read_text()) if source_file.is_file() else {}
    attribution = f"Outline: {source.get('boundarySource', 'user-supplied GeoJSON')}; {source.get('boundaryLicense', 'verify license')}."

    def base(ax):
        ax.set_facecolor("#EAF2F6")
        for polygon in rings:
            outer = np.array(polygon[0])
            ax.fill(outer[:, 0], outer[:, 1], color="#F0F1EB", zorder=0)
            for ring in polygon:
                points = np.array(ring)
                ax.plot(points[:, 0], points[:, 1], color="#809598", linewidth=.5, zorder=2)
        ax.set_xlim(limits[:2]); ax.set_ylim(limits[2:]); ax.set_aspect(1 / np.cos(np.deg2rad(1.35)))
        ax.set_xlabel("Longitude (°E)"); ax.set_ylabel("Latitude (°N)")
        ax.tick_params(labelsize=8)

    average = station_year.groupby("station_id", as_index=False).agg(
        latitude=("latitude", "mean"), longitude=("longitude", "mean"),
        rainfall_total_mm=("rainfall_total_mm", "mean"), coverage=("coverage", "mean"))
    # Leave one station out to expose interpolation error and unsupported edges.
    diagnostics = []
    for period, stations in [("2017–2024 mean", average)] + list(station_year.groupby("year")):
        errors = []
        for index, held_out in stations.iterrows():
            train = stations.drop(index=index)
            estimate = interpolate(train, np.array([held_out.longitude]), np.array([held_out.latitude]), rings, max_distance_km)
            if estimate is not None and np.isfinite(estimate[0]):
                errors.append(float(estimate[0] - held_out.rainfall_total_mm))
        diagnostics.append({"period": str(period), "stations": len(stations), "scored_holdouts": len(errors),
            "unsupported_holdouts": len(stations)-len(errors),
            "mae_mm": float(np.mean(np.abs(errors))) if errors else None,
            "rmse_mm": float(np.sqrt(np.mean(np.square(errors)))) if errors else None,
            "interpretation": "spatial interpolation validation; not Task 2 forecast performance"})
    pd.DataFrame(diagnostics).to_csv(gallery.output / "spatial_idw_diagnostics.csv", index=False)
    # Mark observed points independently of the interpolated field.
    fig, axes = plt.subplots(1, 2, figsize=(15, 6))
    vmin, vmax = average.rainfall_total_mm.min(), average.rainfall_total_mm.max()
    norm = Normalize(vmin=vmin, vmax=max(vmax, vmin + .01))
    for ax in axes: base(ax)
    field = interpolate(average, x, y, rings, max_distance_km) if len(average) >= 6 else None
    sc = axes[0].scatter(average.longitude, average.latitude, c=average.rainfall_total_mm,
        cmap="YlGnBu", norm=norm, s=85, edgecolor="white", linewidth=1.1, zorder=3)
    axes[0].set_title("Observed station means", fontsize=12)
    if field is not None:
        axes[1].pcolormesh(x, y, np.ma.masked_invalid(field), cmap="YlGnBu", norm=norm, shading="auto", rasterized=True)
        axes[1].set_title("IDW spatial estimate · not an observation", fontsize=12)
    else:
        axes[1].text(.5, .88, f"{len(average)} stations: interpolation omitted" if len(average) < 6 else "Insufficient spatial support for interpolation", transform=axes[1].transAxes, ha="center", wrap=True)
        axes[1].set_title("Station locations · limited spatial support", fontsize=12)
    if field is None:
        axes[1].clear()
        ranked = average.sort_values("rainfall_total_mm")
        axes[1].barh(ranked.station_id.astype(str), ranked.rainfall_total_mm,
                     color=plt.get_cmap("YlGnBu")(norm(ranked.rainfall_total_mm)), edgecolor=INK, linewidth=.5)
        axes[1].set_aspect("auto")
        axes[1].set_title(f"{len(average)} station totals · no interpolation", fontsize=12)
        axes[1].set_xlabel("Mean matched-month total (mm)")
        axes[1].grid(axis="x", alpha=.3); axes[1].set_axisbelow(True)
    else:
        axes[1].scatter(average.longitude, average.latitude, c=average.rainfall_total_mm, cmap="YlGnBu", norm=norm, s=35, edgecolor="white", zorder=3)
    fig.colorbar(sc, ax=list(axes), label="Mean matched-month rainfall (mm)", fraction=.025, pad=.015)
    gallery.save("10_singapore_spatial_heatmap", fig, "Where do the stations record more rain?",
        "2017–2024 mean matched-month amounts · observed stations alongside a spatial estimate",
        f"IDW shown only with >=6 stations (display rule, not a validity guarantee); land + station hull + {max_distance_km:g} km mask. {attribution}")
    fig, axes = plt.subplots(2, 4, figsize=(17, 8))
    norm_year = Normalize(vmin=station_year.rainfall_total_mm.min(), vmax=max(station_year.rainfall_total_mm.max(), station_year.rainfall_total_mm.min()+.01))
    for ax, year in zip(axes.ravel(), range(2017, 2025)):
        base(ax); d = station_year[station_year.year == year]
        field_year = interpolate(d, x, y, rings, max_distance_km) if len(d) >= 6 else None
        if field_year is not None: ax.pcolormesh(x, y, np.ma.masked_invalid(field_year), cmap="YlGnBu", norm=norm_year, shading="auto", rasterized=True)
        ax.scatter(d.longitude, d.latitude, c=d.rainfall_total_mm, cmap="YlGnBu", norm=norm_year, s=18, edgecolor="white", linewidth=.5, zorder=3)
        ax.set_title(str(year)); ax.set_xlabel(""); ax.set_ylabel("")
    fig.colorbar(plt.cm.ScalarMappable(norm=norm_year, cmap="YlGnBu"), ax=list(axes.ravel()), label="Matched-month station total / IDW estimate (mm)", fraction=.018, pad=.01)
    gallery.save("11_spatial_change_by_year", fig, "Spatial rainfall patterns across eight years",
        f"{station_year.station_id.nunique()} fixed stations; same calendar months each year; partial-year totals",
        f"Measured station dots; IDW only with >=6 sites and masked support. No missing-total correction. {attribution}")
    monthly = data["spatial_month_common"]
    if require(monthly, ["station_id", "month", "latitude", "longitude", "rainfall_total_mm"]):
        month_stations = monthly.groupby(["station_id", "month"], as_index=False).agg(
            latitude=("latitude", "mean"), longitude=("longitude", "mean"), rainfall_total_mm=("rainfall_total_mm", "mean"))
        norm_month = Normalize(vmin=month_stations.rainfall_total_mm.min(), vmax=max(month_stations.rainfall_total_mm.max(), month_stations.rainfall_total_mm.min()+.01))
        fig, axes = plt.subplots(3, 4, figsize=(17, 11))
        for month, ax in enumerate(axes.ravel(), 1):
            base(ax); d = month_stations[month_stations.month == month]
            f = interpolate(d, x, y, rings, max_distance_km) if len(d) >= 6 else None
            if f is not None: ax.pcolormesh(x, y, np.ma.masked_invalid(f), cmap="YlGnBu", norm=norm_month, shading="auto", rasterized=True)
            ax.scatter(d.longitude, d.latitude, c=d.rainfall_total_mm, cmap="YlGnBu", norm=norm_month, s=16, edgecolor="white", linewidth=.5, zorder=3)
            if d.empty: ax.text(.5, .5, "No matched-month data", transform=ax.transAxes, ha="center", color=INK)
            ax.set_title(calendar.month_name[month]); ax.set_xlabel(""); ax.set_ylabel("")
        fig.colorbar(plt.cm.ScalarMappable(norm=norm_month, cmap="YlGnBu"), ax=list(axes.ravel()), label="Mean observed monthly station total / estimate (mm)", fraction=.018, pad=.01)
        gallery.save("12_spatial_seasonality", fig, "The geography of rainfall through the year",
            "Eight-year qualified panel within each calendar month; station panels differ between months",
            f"Blank months lack an eight-year matched panel. Month lengths and station panels differ; IDW is descriptive. {attribution}")
    interactive_map(station_year, rings, limits, gallery, attribution)
    if regions_path is not None and regions_path.is_file():
        regional_map(average, regions_path, gallery, limits)
    else:
        gallery.skipped.append("planning-area choropleth: supply --regions assets/planning_areas.geojson")


def spatial_snapshot(data, gallery, boundary_path, regions_path, max_distance_km=10):
    """Describe one complete calendar year with a larger eligible station network."""
    frame = data["spatial_year_available"]
    if not require(frame, ["year", "station_id", "latitude", "longitude", "rainfall_total_mm", "coverage"]):
        gallery.skipped.append("single-year spatial snapshot: no qualified full-year stations")
        return
    if boundary_path is None or not boundary_path.is_file():
        gallery.skipped.append("single-year spatial snapshot: missing boundary")
        return
    support = frame.groupby("year").agg(stations=("station_id", "nunique"), mean_coverage=("coverage", "mean")).reset_index()
    support = support.sort_values(["stations", "mean_coverage", "year"], ascending=[False, False, False])
    year = int(support.iloc[0].year)
    support.to_csv(gallery.output / "spatial_snapshot_year_selection.csv", index=False)
    d = frame[frame.year == year].copy()
    d.to_csv(gallery.output / f"spatial_snapshot_{year}_stations.csv", index=False)
    rings = polygons(json.loads(boundary_path.read_text()))
    vertices = np.concatenate([np.array(polygon[0])[:, :2] for polygon in rings])
    limits = [vertices[:, 0].min()-.015, vertices[:, 0].max()+.015,
              vertices[:, 1].min()-.015, vertices[:, 1].max()+.015]
    source_path = boundary_path.with_suffix(".source.json")
    source = json.loads(source_path.read_text()) if source_path.is_file() else {}
    original_label = gallery.label
    gallery.label = f"Singapore rainfall | {year} full-calendar-year snapshot | {len(d)} eligible stations"
    fig, ax = plt.subplots(figsize=(13, 7))
    for polygon in rings:
        outer = np.array(polygon[0])
        ax.fill(outer[:, 0], outer[:, 1], color="#EDF0EA")
        for hole in polygon[1:]:
            h = np.array(hole); ax.fill(h[:, 0], h[:, 1], color="#EAF2F6")
        for ring in polygon:
            xy = np.array(ring); ax.plot(xy[:, 0], xy[:, 1], color="#9BAEB6", linewidth=.5)
    ax.set_facecolor("#EAF2F6")
    dots = ax.scatter(d.longitude, d.latitude, c=d.rainfall_total_mm, s=75,
                     cmap="YlGnBu", edgecolor=INK, linewidth=.6, zorder=3)
    ax.set_xlim(limits[:2]); ax.set_ylim(limits[2:]); ax.set_aspect(1 / np.cos(np.deg2rad(1.35)))
    ax.set(xlabel="Longitude (°E)", ylabel="Latitude (°N)")
    fig.colorbar(dots, ax=ax, label="Observed annual station rainfall (mm)", fraction=.025, pad=.02)
    gallery.save(f"14_station_snapshot_{year}", fig, f"Rainfall across {len(d)} stations in {year}",
        "Year selected by eligible station count, then mean coverage; no rainfall-based selection",
        f"Annual coverage >=95%; each month meets saved threshold; stable coordinates. Recorded totals are not gap-filled. Boundary: {source.get('boundarySource', 'user GeoJSON')}; {source.get('boundaryLicense', 'verify license')}.")
    monthly = data["station_month"]
    if require(monthly, ["year", "month", "station_id", "rainfall_total_mm"]):
        selected = monthly[(monthly.year == year) & monthly.station_id.isin(d.station_id)]
        x, y = np.meshgrid(np.linspace(limits[0], limits[1], 200), np.linspace(limits[2], limits[3], 130))
        norm = PowerNorm(gamma=.5, vmin=0, vmax=max(selected.rainfall_total_mm.max(), 1))
        diagnostics = []
        fig, axes = plt.subplots(3, 4, figsize=(17, 11))
        for month, ax in enumerate(axes.ravel(), 1):
            for polygon in rings:
                outer = np.array(polygon[0]); ax.fill(outer[:, 0], outer[:, 1], color="#EDF0EA")
                for ring in polygon:
                    xy = np.array(ring); ax.plot(xy[:, 0], xy[:, 1], color="#9BAEB6", linewidth=.4)
            m = selected[selected.month == month]
            estimate = interpolate(m, x, y, rings, max_distance_km) if len(m) >= 6 else None
            errors = []
            for index, held_out in m.iterrows():
                prediction = interpolate(m.drop(index=index), np.array([held_out.longitude]), np.array([held_out.latitude]), rings, max_distance_km)
                if prediction is not None and np.isfinite(prediction[0]):
                    errors.append(float(prediction[0] - held_out.rainfall_total_mm))
            diagnostics.append({"year": year, "month": month, "stations": len(m), "scored_holdouts": len(errors),
                                "unsupported_holdouts": len(m)-len(errors), "mae_mm": float(np.mean(np.abs(errors))) if errors else None,
                                "rmse_mm": float(np.sqrt(np.mean(np.square(errors)))) if errors else None})
            if estimate is not None:
                ax.pcolormesh(x, y, np.ma.masked_invalid(estimate), cmap="YlGnBu", norm=norm, shading="auto", rasterized=True)
            ax.scatter(m.longitude, m.latitude, c=m.rainfall_total_mm, cmap="YlGnBu", norm=norm, s=12, edgecolor=INK, linewidth=.3, zorder=3)
            ax.set_xlim(limits[:2]); ax.set_ylim(limits[2:]); ax.set_aspect(1 / np.cos(np.deg2rad(1.35)))
            ax.set_title(f"{calendar.month_name[month]} · n={len(m)}", fontsize=11)
            ax.tick_params(labelsize=7)
        fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap="YlGnBu"), ax=list(axes.ravel()), label="Monthly total / IDW (mm; square-root colour scale)", fraction=.018, pad=.01)
        pd.DataFrame(diagnostics).to_csv(gallery.output / "spatial_snapshot_idw_diagnostics.csv", index=False)
        largest = selected.loc[selected.rainfall_total_mm.idxmax()]
        gallery.save(f"16_monthly_spatial_snapshot_{year}", fig, f"Spatial seasonality in {year} | the same {len(d)} stations",
            "Twelve calendar months with one eligible station panel and one colour scale",
            f"IDW clipped to land, hull and {max_distance_km:g} km support. Square-root colour scale retains all values; largest: {largest.station_id}, {calendar.month_abbr[int(largest.month)]}, {largest.rainfall_total_mm:,.1f} mm. Month lengths differ; one-year pattern only. See interpolation diagnostics.")
    if regions_path is not None and regions_path.is_file():
        regional_map(d, regions_path, gallery, limits, snapshot_year=year)
    gallery.label = original_label


def regional_map(average, regions_path, gallery, limits, snapshot_year=None):
    from matplotlib.patches import Polygon
    regions = json.loads(regions_path.read_text())
    region_polygons = [polygons({"features": [feature]}) for feature in regions["features"]]
    lon, lat = average.longitude.to_numpy(), average.latitude.to_numpy()
    membership = np.column_stack([land_mask(lon, lat, rings) for rings in region_polygons])
    # Exclude ambiguous boundary assignments rather than counting a station twice.
    unambiguous = membership.sum(axis=1) == 1
    records = []
    for index, feature in enumerate(regions["features"]):
        props = feature.get("properties", {})
        name = props.get("shapeName", props.get("PLN_AREA_N", props.get("name", f"Area {index+1}")))
        d = average[membership[:, index] & unambiguous]
        records.append({"area": name, "stations": len(d),
            "mean_matched_month_mm": d.rainfall_total_mm.mean(),
            "mean_coverage": d.coverage.mean()})
    table = pd.DataFrame(records)
    if snapshot_year is not None:
        table = table.rename(columns={"mean_matched_month_mm": "mean_observed_annual_mm"})
        value_column = "mean_observed_annual_mm"
        name = f"15_planning_area_snapshot_{snapshot_year}"
        label = f"{snapshot_year} observed annual station total (mm)"
    else:
        value_column = "mean_matched_month_mm"
        name = "13_planning_area_station_heatmap"
        label = "Mean matched-month station total (mm)"
    table.to_csv(gallery.output / (f"planning_area_snapshot_{snapshot_year}.csv" if snapshot_year else "planning_area_station_means.csv"), index=False)
    assignments = average[["station_id", "latitude", "longitude"]].copy()
    assignments["area"] = [records[int(np.flatnonzero(membership[i])[0])]["area"] if unambiguous[i] else "UNASSIGNED_OR_AMBIGUOUS" for i in range(len(average))]
    assignments.to_csv(gallery.output / f"{name}_station_assignments.csv", index=False)
    valid = table[value_column].dropna()
    if valid.empty:
        gallery.skipped.append("planning areas: no stations assigned unambiguously")
        return
    norm = Normalize(valid.min(), max(valid.max(), valid.min()+.01))
    colors = plt.get_cmap("YlGnBu")
    fig, axes = plt.subplots(1, 2, figsize=(16, 7), gridspec_kw={"width_ratios": [1.6, 1]})
    fig.subplots_adjust(wspace=.9)
    axes[0].set_facecolor("#EAF2F6")
    for index, rings in enumerate(region_polygons):
        value = table.iloc[index][value_column]
        color = "#DCE3E6" if pd.isna(value) else colors(norm(value))
        for polygon in rings:
            axes[0].add_patch(Polygon(np.array(polygon[0])[:, :2], facecolor=color, edgecolor="white", linewidth=.6))
            for hole in polygon[1:]:
                axes[0].add_patch(Polygon(np.array(hole)[:, :2], facecolor="#EAF2F6", edgecolor="white", linewidth=.4))
    axes[0].scatter(lon, lat, s=18, c=INK, edgecolor="white", linewidth=.4, zorder=3)
    axes[0].set_xlim(limits[:2]); axes[0].set_ylim(limits[2:])
    axes[0].set_aspect(1 / np.cos(np.deg2rad(1.35)))
    axes[0].set(xlabel="Longitude (°E)", ylabel="Latitude (°N)")
    ranked = table.dropna(subset=[value_column]).sort_values(value_column).tail(12)
    axes[1].barh([f"{r.area} (n={r.stations})" for r in ranked.itertuples()], ranked[value_column], color=TEAL)
    axes[1].set_xlabel(label); axes[1].tick_params(axis="y", labelsize=8)
    color_axis = fig.add_axes([.925, .28, .015, .45])
    fig.colorbar(plt.cm.ScalarMappable(norm=norm, cmap=colors), cax=color_axis, label=label)
    metadata_path = regions_path.with_suffix(".source.json")
    source = json.loads(metadata_path.read_text()) if metadata_path.is_file() else {}
    gallery.save(name, fig, f"Rainfall by planning area | {snapshot_year or str(len(average)) + ' matched stations'}",
        "Each coloured area shows its included station mean; grey = no eligible station. This is not an area-average measurement.",
        f"Not area-weighted district rainfall; dots = station locations; n = stations. Ambiguous/unassigned stations excluded: {int((~unambiguous).sum())}. Boundary: {source.get('boundarySource', 'user GeoJSON')}; {source.get('boundaryLicense', 'verify license')}.")


def interactive_map(station_year, rings, limits, gallery, attribution):
    import plotly.graph_objects as go
    fig = go.Figure()
    for polygon in rings:
        for ring in polygon:
            xy = np.array(ring)
            fig.add_trace(go.Scatter(x=xy[:, 0], y=xy[:, 1], mode="lines", line={"color": "#9CAFB8", "width": 1}, hoverinfo="skip", showlegend=False))
    first_station = len(fig.data)
    norm = [station_year.rainfall_total_mm.min(), station_year.rainfall_total_mm.max()]
    for year in range(2017, 2025):
        d = station_year[station_year.year == year]
        details = np.column_stack([d.station_id, d.coverage * 100, d.rainfall_total_mm])
        fig.add_trace(go.Scatter(x=d.longitude, y=d.latitude, mode="markers", visible=year == 2017,
            customdata=details, marker={"size": 13, "color": d.rainfall_total_mm, "colorscale": "YlGnBu", "cmin": norm[0], "cmax": norm[1], "showscale": True, "colorbar": {"title": "Matched-month mm"}, "line": {"color": "white", "width": 1}},
            hovertemplate="Station %{customdata[0]}<br>Observed total %{customdata[2]:,.1f} mm<br>Coverage %{customdata[1]:.1f}%<extra></extra>", showlegend=False))
    buttons = []
    for i, year in enumerate(range(2017, 2025)):
        visible = [True] * first_station + [j == i for j in range(8)]
        buttons.append({"label": str(year), "method": "update", "args": [{"visible": visible}, {"title": f"Singapore rainfall · {year} · measured stations"}]})
    fig.update_layout(title="Singapore rainfall · 2017 · measured stations", template="plotly_white", width=1100, height=650,
        updatemenus=[{"buttons": buttons, "x": 0, "y": 1.12}],
        xaxis={"title": "Longitude (°E)", "range": limits[:2]},
        yaxis={"title": "Latitude (°N)", "range": limits[2:], "scaleanchor": "x", "scaleratio": 1 / np.cos(np.deg2rad(1.35))},
        annotations=[{"text": attribution + "<br>Fixed station panel and matched calendar months; partial-year totals, not area-weighted rainfall.", "xref": "paper", "yref": "paper", "x": 0, "y": -.15, "showarrow": False, "xanchor": "left", "font": {"size": 10}}], margin={"b": 110})
    fig.write_html(gallery.output / "spatial_explorer.html", include_plotlyjs=True)


def numeric_findings(data, output):
    records = []
    annual, monthly = data["annual_common"], data["monthly_common"]
    if require(annual, ["year", "mean_station_rainfall_mm"]):
        valid = annual.dropna(subset=["mean_station_rainfall_mm"])
        for label, selector in [("highest_matched_month_total", "idxmax"), ("lowest_matched_month_total", "idxmin")]:
            if not valid.empty:
                row = valid.loc[getattr(valid.mean_station_rainfall_mm, selector)()]
                records.append({"finding": label, "year": int(row.year), "value": row.mean_station_rainfall_mm, "unit": "mm per common-panel station", "basis": "same stations and calendar months across years; partial-year total, no gap scaling"})
    if require(monthly, ["month", "mean_station_rainfall_mm"]):
        means = monthly.groupby("month").mean_station_rainfall_mm.mean().dropna()
        for label, fn in [("highest_mean_month", means.idxmax), ("lowest_mean_month", means.idxmin)]:
            if not means.empty:
                month = fn()
                records.append({"finding": label, "month": int(month), "value": means.loc[month], "unit": "mm per common-panel station", "basis": "among matched comparison months only; 2017–2024 same-month mean, not climate normal"})
    pd.DataFrame(records, columns=["finding", "year", "month", "value", "unit", "basis"]).to_csv(output / "descriptive_findings.csv", index=False)


def write_gallery_index(output, manifest):
    """A portable local index; only links to figures generated in this run."""
    cards = []
    for number, item in manifest["figures"].items():
        cards.append(f'<article><h2>{html.escape(number)} · {html.escape(item["title"])}</h2>'
                     f'<a href="{html.escape(item["png"])}"><img loading="lazy" src="{html.escape(item["png"])}"></a>'
                     f'<p>{html.escape(item["note"])}</p><a href="{html.escape(item["svg"])}">SVG vector</a></article>')
    extra = '<p><a href="spatial_explorer.html">Interactive matched-station map</a></p>' if (output / "spatial_explorer.html").exists() else ''
    page = ('<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>Singapore rainfall · Task 1 figures</title><style>'
            'body{font-family:system-ui;background:#edf3f5;color:#18354a;max-width:1200px;margin:40px auto;padding:0 24px}'
            'article{background:white;padding:24px;margin:24px 0;border-radius:12px}img{width:100%;height:auto}h2{font-size:18px}'
            'a{color:#087f8c}p{line-height:1.6}</style><h1>Singapore rainfall · Task 1</h1>'
            '<p>Click an image for full resolution. Filename numbers identify figures, not data values.</p>'
            '<p>Matched-month comparisons use fixed stations and selected months. The single-year snapshot uses a larger eligible network; its annual totals have a different meaning.</p>'
            + extra + ''.join(cards) + '<p>Input: ' + html.escape(manifest["input_directory"]) + '</p></html>')
    (output / "index.html").write_text(page)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=Path("figures/task1"))
    parser.add_argument("--boundary", type=Path)
    parser.add_argument("--regions", type=Path, help="Planning-area GeoJSON, optional")
    parser.add_argument("--max-distance-km", type=float, default=10)
    parser.add_argument("--only", choices=["all", "coverage", "temporal", "spatial"], default="all", help="Run just one plotting stage")
    parser.add_argument("--label", default="2017–2024 · Singapore rainfall")
    args = parser.parse_args()
    if not args.results.is_dir(): parser.error("Provide one LOCAL experiment directory containing Spark tables")
    if args.output.exists() and (not args.output.is_dir() or any(args.output.iterdir())):
        parser.error("Choose a fresh output directory so old figures cannot be mistaken for this experiment's results")
    if not 0 < args.max_distance_km <= 100: parser.error("max-distance-km must be in (0, 100]")
    style()
    gallery = Gallery(args.output, args.label)
    data = {name: read_csv(find_input(args.results, name)) for name in TABLES}
    if args.only != "coverage" and not require(data["comparison_policy"], ["policy", "comparison_months"]):
        parser.error("Legacy EDA has no comparison_policy. Run the updated analyze job first, or use --only coverage.")
    policy = data["comparison_policy"].fillna("")
    if not policy.empty:
        policy.to_csv(args.output / "comparison_policy.csv", index=False)
        months = str(policy.iloc[0].comparison_months)
        gallery.label += f" | matched comparison months: {months}; seasonal plots use qualified available months"
    if args.only in ("all", "coverage"): coverage(data, gallery)
    if args.only in ("all", "temporal"):
        temporal(data, gallery)
        numeric_findings(data, args.output)
    if args.only in ("all", "spatial"):
        spatial(data, gallery, args.boundary, args.max_distance_km, args.regions)
        spatial_snapshot(data, gallery, args.boundary, args.regions, args.max_distance_km)
    manifest = {"input_directory": str(args.results.resolve()), "label": gallery.label, "stage": args.only,
        "comparison_policy": policy.to_dict("records"),
        "boundary": str(args.boundary) if args.boundary else None, "figures": gallery.figures,
        "skipped": gallery.skipped, "idw": {"power": 2, "neighbors": 6, "minimum_display_stations": 6, "max_distance_km": args.max_distance_km},
        "warning": "Spatial interpolation is not district-level measurement or Task 2 forecast validation. No claims of long-term climate trends."}
    manifest["geographic_sources"] = [json.loads(p.with_suffix(".source.json").read_text())
        for p in [args.boundary, args.regions] if p and p.with_suffix(".source.json").is_file()]
    (args.output / "figure_manifest.json").write_text(json.dumps(manifest, indent=2))
    write_gallery_index(args.output, manifest)
    if not gallery.figures: raise SystemExit("No Task 1 figures produced; inspect missing tables and common-panel eligibility.")
    print(f"Generated {len(gallery.figures)} PNG/SVG figures in {args.output.resolve()}")
    for reason in gallery.skipped: print("SKIPPED:", reason)


if __name__ == "__main__":
    main()

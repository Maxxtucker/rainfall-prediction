# Task 1 图表入口

当前图集是 `figures/task1-v5-report/index.html`；交互地图是同目录的 `spatial_explorer.html`，可离线切换全部 96 个年月。

正文统一放在 `report/project_report.pdf`。中文解读见 `report/task1/FIGURE_GUIDE_ZH.md`。PDF 矢量图和 PNG 图集预览保留；重复 SVG 已清理，需要时可用 `scripts/plot_task1_report.py` 在新目录重新生成。

图集包括：雨量分布、覆盖与源缺口、月度和季节变化、共同站点跨年比较、完整年累计、日内与日尾部、80/90/95% 覆盖敏感性，以及全月份空间图。月图不插值；灰色表示没有合格支持，不是没有下雨。

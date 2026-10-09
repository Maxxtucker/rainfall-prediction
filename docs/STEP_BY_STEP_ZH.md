# 提交与复现步骤

1. 阅读根目录 [README.md](../README.md)，这是唯一正式运行入口说明。
2. 最终报告在 `report/project_report.pdf`；姓名和学号先留空，提交前填写并重新编译。
3. 两个已训练模型在 `outputs/steps/task2-dual-v2/models/`，可直接重载，不必重训。
4. 只复现图表/报告时使用已保存汇总结果，无需原始数据或 GCP。
5. 要完整复现训练，按 README 的 GCP 步骤生成原始数据、清洗结果和特征；新运行使用新结果名。
6. 执行现有测试与 `scripts/build_submission.py`，最后提交 `dist/rainfall-submission.zip`。

不得把缺测补成零，也不要把旧版四站四个月结果当成当前报告。旧报告和临时产物已经清理；最终源码快照与证据保留。

# 提交与复现步骤

1. 从根目录 [README.md](../README.md) 选择工作流：查询保存模型、重建报告，或完整复现 Spark 实验。
2. 阅读唯一提交报告 `report/project_report.pdf`。在 `report/project_report.template.tex` 填写组员姓名和学号，按 [报告指南](../report/README.md) 编辑正文来源，再运行 `bash report/build.sh`。
3. 原始正式模型在 `outputs/steps/task2-dual-v2/models/`，可直接重载。模型 A 还需要近期清洗观测；模型 B 只需站点、时间和雨量阈值。
4. 只更新报告时使用现有汇总结果和图表，无需原始数据或 GCP。不要直接编辑生成的 `project_report.tex`。
5. 要完整复现训练，按 [GCP 指南](GCP_GUIDE_ZH.md) 下载数据、清洗、生成特征并训练。新实验使用新结果名。RF 后续抽样与调参流程见 [RF_SENSITIVITY.md](RF_SENSITIVITY.md)。
6. 原始最终结果使用 2024 测试集；RF 后续实验使用 2022 验证集。后续候选模型与正式模型分别保存，报告中也须区分。
7. 按需查看或执行 [验证说明](VALIDATION.md) 中的软件与模型检查。提交前检查生成 PDF、组员信息和 AI 声明，然后运行 `python scripts/build_submission.py`，生成 `dist/rainfall-submission.zip`。

提交包包含同一个正式 PDF、源码、训练模型、图表和证据。原始 CSV、完整清洗/特征缓存和个人云配置不在包内。缺失观测不应补成零；早期四站四个月分析不能替代当前覆盖八年日历的结果。

# GCP 运行指南

正式、完整命令以根目录 [README.md](../README.md) 的 “Reproduce processing and training on GCP” 为准。配置模板是 `cloud/env.example`，规格与实测一致：1 个 master + 2 个 worker，每个 e2-standard-4、80 GB pd-balanced 磁盘。

只看报告、图集或使用模型 B 本地预测，不需要启动 GCP。完整复现顺序为 setup → download → create cluster → smoke → clean → analyse → features → 两种训练 → compare → download → delete cluster。各阶段可独立运行，已有清洗数据可以复用。

Task 2 原训练复用 `task2-dual-v1/data`，最终模型在 `task2-dual-v2/models`。本地大型特征缓存已删除，准备审计与 GCS 路径保留。提交压缩包不含 `cloud/env.sh`，接收者需要填写自己的项目与桶。

# GCP 完整复现指南

只阅读报告、重建图表或本地查询已保存的模型 B，无需启动 GCP。以下流程用于从原始数据重新完成 Spark 清洗、分析与训练；创建集群会产生云资源费用。

实测环境为 Dataproc 2.2.87 / Debian 12、Spark 3.5.3 on YARN，区域为 `asia-southeast1-c`。集群有 1 个 master 和 2 个 worker，每台为 `e2-standard-4`（4 vCPU、16 GB RAM、80 GB `pd-balanced` 磁盘）。正式实验集群已删除。

## 准备和运行

从项目根目录开始。先安装根目录 README 中的 Python 依赖及 Google Cloud CLI，在自己的项目中完成 `gcloud` 认证并启用计费。复制 `cloud/env.example` 后填写 `PROJECT_ID` 和全局唯一的 `BUCKET` 名称。模板规格与实测的 12-vCPU 集群一致；本地云配置和凭据不应提交到仓库。

```bash
cp cloud/env.example cloud/env.sh
# Edit cloud/env.sh before continuing.
bash cloud/01_setup.sh
source cloud/_env.sh
python3 scripts/download_data.py --output "$PROJECT_ROOT"
bash cloud/02_create_cluster.sh
python3 scripts/build_package.py
gcloud storage cp dist/rainfall.zip "${PROJECT_ROOT}/code/rainfall.zip"
gcloud storage cp jobs/smoke_test.py "${PROJECT_ROOT}/code/jobs/smoke_test.py"
gcloud dataproc jobs submit pyspark "${PROJECT_ROOT}/code/jobs/smoke_test.py" \
  --project "$PROJECT_ID" --region "$REGION" --cluster "$CLUSTER" \
  --py-files "${PROJECT_ROOT}/code/rainfall.zip"
bash cloud/05_clean_only.sh all clean-all-v1
bash cloud/06_analyze_only.sh clean-all-v1 task1-new \
  --shuffle-partitions 128 --raw "${PROJECT_ROOT}/raw"
bash cloud/07_download_task1.sh task1-new
bash cloud/08_task2.sh features task2-new
bash cloud/08_task2.sh train-calendar task2-new --train-fraction 0.15 --eval-fraction 1
bash cloud/08_task2.sh train-short-term task2-new --train-fraction 0.15 --eval-fraction 1
bash cloud/08_task2.sh compare task2-new
# Download to a fresh local directory after all jobs finish.
gcloud storage rsync --recursive "${PROJECT_ROOT}/steps/task2-new/models" outputs/steps/task2-new/models
gcloud storage rsync --recursive "${PROJECT_ROOT}/steps/task2-new/comparison" outputs/steps/task2-new/comparison
bash cloud/99_delete_cluster.sh
```

请使用新的运行名称；任务会拒绝已存在的输出路径。重新运行所需的配额和权限由你的项目配置决定。数据来源与下载清单规则见 [DATA_SOURCES.md](DATA_SOURCES.md)。

## 已保存的实验与后续分析

正式训练复用 `task2-dual-v1/data` 特征表，最终模型保存在 `task2-dual-v2/models`。上面的新运行名称仅用于独立复现，不覆盖已报告结果。Feature 缓存、清洗后的 Parquet 和原始年度 CSV 不随提交包分发；准备审计和原始执行路径保留在结果目录中。

RF 的 15%/30% 抽样和参数敏感性实验有单独的 [运行协议](RF_SENSITIVITY.md)。新候选模型只在 2022 验证集上比较，不能代替已完成 2024 测试的正式模型。

如果要对上面新建的 `task2-new` 运行做 RF 后续实验，请在删除集群前执行以下命令。两个环境变量覆盖脚本默认的历史输入路径，输出仍使用另一个新名称：

```bash
source cloud/_env.sh
RAINFALL_SENSITIVITY_DATA="${PROJECT_ROOT}/steps/task2-new/data" \
RAINFALL_SENSITIVITY_MODELS="${PROJECT_ROOT}/steps/task2-new/models" \
  bash cloud/09_rf_sensitivity.sh rf-sensitivity-task2-new
```

按 RF 运行协议下载和分析这个新结果目录。模型打包时，`--original-models` 也应指向对应的 `outputs/steps/task2-new/models`。该敏感性方案固定了参考森林参数，运行前须确认新模型的参数与协议相符。

下载汇总结果后，按 [报告指南](../report/README.md) 重建图表与 PDF。重建报告使用本地保存的统计结果，不会重新创建集群。任务结束前确认结果已经下载或安全保存在 Cloud Storage，再删除集群。

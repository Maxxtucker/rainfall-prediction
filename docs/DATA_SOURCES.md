# 官方数据来源与下载复现

本项目仅使用 NEA 在 data.gov.sg 发布的 **Historical Rainfall across Singapore** 系列中 **2017–2024** 八个年度 CSV。集合：[collection 2279](https://data.gov.sg/collections/2279/view)。数据集名称和 ID 已于 2026-10-06 根据官方网页核对；准备阶段没有把完整年度 CSV 下载到本地，因此网页展示的概况不能当作已经完成的项目实验结果。

| 年份 | 官方年度数据集 |
|---|---|
| 2017 | [d_1990a5a1aeaf3dd243cf4dae294a61c4](https://data.gov.sg/datasets/d_1990a5a1aeaf3dd243cf4dae294a61c4/view) |
| 2018 | [d_024fb501ce7092b71bb713eaf54fa7eb](https://data.gov.sg/datasets/d_024fb501ce7092b71bb713eaf54fa7eb/view) |
| 2019 | [d_61995f092320e7155b7528050880b502](https://data.gov.sg/datasets/d_61995f092320e7155b7528050880b502/view) |
| 2020 | [d_9e7de44094f876f6804b8b5bcee45c81](https://data.gov.sg/datasets/d_9e7de44094f876f6804b8b5bcee45c81/view) |
| 2021 | [d_3b41598f74f1f11fc3430348fea51af5](https://data.gov.sg/datasets/d_3b41598f74f1f11fc3430348fea51af5/view) |
| 2022 | [d_42d64cc6c176ace1c52fbb40b9ede302](https://data.gov.sg/datasets/d_42d64cc6c176ace1c52fbb40b9ede302/view) |
| 2023 | [d_f864cc30d58b467db83659ad17c737bf](https://data.gov.sg/datasets/d_f864cc30d58b467db83659ad17c737bf/view) |
| 2024 | [d_a0b69d3e02576a1fd0ab673e71f83507](https://data.gov.sg/datasets/d_a0b69d3e02576a1fd0ab673e71f83507/view) |

## 必须保留的数据语义

官方说明：时间戳采用 Singapore Time (SGT)，ISO 8601 格式；数据可能有缺失，且未经过官方气候记录所采用的质量控制。本项目的质量检查不能将这套数据升级为官方气候记录。

2017 年官方预览有 12 个字段：`date`, `timestamp`, `update_timestamp`, `station_id`, `station_name`, `station_device_id`, `location_longitude`, `location_latitude`, `reading_update_timestamp`, `reading_value`, `reading_type`, `reading_unit`。`reading_type` 在已查看的 2017 预览中标识五分钟累计雨量，`reading_unit` 为 `mm`。下载后的真实 CSV 表头保存在年度 manifest，清洗程序还会实际验证单位与读数。

预览的一条记录以 `2017-01-01T08:04:59+08:00` 为观测时刻，更新时间为 `2017-01-01T08:13:31+08:00`。因此：

- 不要简单把秒数不等于 0 的记录全部删除。
- `timestamp` 是观测时间；`update_timestamp` / `reading_update_timestamp` 不能替代它。
- 雨量是五分钟区间累计量，不是累计到当天该时刻的仪器总数。
- 回测必须区分“已观测”和“当时已发布”。若使用观测时间回测而没有重建数据发布时间，应在报告里明确说明这是离线观测时间假设。
- 零雨量和缺失雨量不同，缺失不能自动填成零。

以上样例用于核查字段语义，不是从八年数据运算得出的统计结论。

## 下载命令

下载脚本只依赖 Python 3 标准库。保存到 GCS 时还需已登录的 `gcloud` CLI。

```bash
# --output 是项目数据根目录；脚本自动追加 raw/year=YYYY/rainfall.csv。
python3 scripts/download_data.py --output gs://YOUR_BUCKET/rainfall --catalog-only
python3 scripts/download_data.py --output gs://YOUR_BUCKET/rainfall

# 单年调试
python3 scripts/download_data.py --output ./data --years 2017

# 网络暂时无法读取 collection metadata 时，可显式采用核验后的固定 ID。
python3 scripts/download_data.py --output gs://YOUR_BUCKET/rainfall --pinned-only
```

公共下载支持不带 API key 的调用。若自己申请了 key，可以在终端使用 `read -s DATA_GOV_SG_API_KEY` 后 `export DATA_GOV_SG_API_KEY`，避免把真实 key 写入源码、报告或共享 shell 历史。脚本只通过 `x-api-key` 请求头使用它，不打印、不保存。

脚本首先刷新集合元数据：

```text
GET https://api-production.data.gov.sg/v2/public/api/collections/2279/metadata?withDatasetMetadata=true
```

若刷新失败，保留警告并使用 `config/datasets.json` 中核验后的 ID；此状态明确写入 `catalog.json`。注意集合元数据域名与下载域名不同。

每个年度依次调用：

```text
GET https://api-open.data.gov.sg/v1/public/api/datasets/{datasetId}/initiate-download
GET https://api-open.data.gov.sg/v1/public/api/datasets/{datasetId}/poll-download
```

然后流式下载 `data.url`，每次只保留一个年度临时文件。上传 GCS 成功并写入年度 manifest 后，释放该年度临时磁盘。不会一次性把全部年度 CSV 读进内存或 Cloud Shell 磁盘。官方 2017 页面展示的单文件大小约 960.7 MB；这只是存储规划信息，不是实际下载后的 manifest 字节数。建议临时盘至少预留 **3 GB 空闲**；若在本地保留八个年度及中间产物，应使用较大磁盘。用 `--work-dir /path/on/larger/disk` 改变临时目录。

所有 API 请求默认至少间隔 13 秒，并对 429、暂时性服务器错误和网络中断重试。下载指南与集中式速率页面的额度说明不同；13 秒为保守默认值，同时满足两处已公布的不带 key 限制。CSV 网络重试会从头开始并重新获取临时 URL，不把不完整文件标记为完成。

## 输出与恢复

```text
data-root/
  catalog.json
  manifest.json
  manifests/2017.json ... manifests/2024.json
  raw/year=2017/rainfall.csv ... raw/year=2024/rainfall.csv
```

年度 manifest 是成功标记，包含下载 UTC 时间、源数据集 ID/URL、可用的官方元数据、实际字节数、SHA-256 和实际 CSV 表头。带签名的下载 URL 查询参数不保存。`manifest.json` 汇总本次请求的年份；分年度 manifest 是各年度的完整下载记录。

重新执行相同命令会检查已完成年度并跳过。对本地文件重新计算 SHA-256；对 GCS 对象核对大小，并依赖首次 `gcloud storage cp` 的上传校验，避免把 GB 级文件重新拉回本地仅为恢复检查。怀疑 GCS 文件被修改时，应下载文件并自行核对 manifest 的 SHA-256，或使用 `--force` 重下。原始 CSV 无 manifest 的年度视为未完成，可以安全重试；`--force` 会覆盖对应年度数据和 manifest。

## 官方接口文档

1. [Collection APIs](https://guide.data.gov.sg/developer-guide/collection-apis)
2. [Download dataset](https://guide.data.gov.sg/developer-guide/dataset-apis/download-dataset)
3. [API Rate Limits](https://guide.data.gov.sg/developer-guide/api-overview/api-rate-limits)
4. [How to use your API Key](https://guide.data.gov.sg/developer-guide/api-overview/how-to-use-your-api-key)
5. [2017 年数据字段与示例](https://data.gov.sg/datasets/d_1990a5a1aeaf3dd243cf4dae294a61c4/view)

下载阶段请保存 manifest 到最终提交的实验材料；报告可以根据 manifest 列出实际获取日期，并根据质量报告填写实际读取/保留行数。

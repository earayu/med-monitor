# med-monitor

医药文献与临床试验定期监控工具。定期拉取 PubMed 与 ClinicalTrials.gov，与本地基线对比，只报告**新增文献、新增临床试验、试验状态变更**，输出 Markdown 周报。

## 特性

- 双数据源：PubMed（NCBI E-utilities）+ ClinicalTrials.gov API v2，均免费、无需 API key
- 增量报告：state diff，只报变化，无变化不打扰
- ⭐ 关键词高亮：标题含 antibody / ADC / bispecific / CAR-T / VHH / nanobody 自动标星
- 临床试验按 Sponsor 分组
- 零依赖：纯 Python 3 标准库，无需 pip install
- 多标的：config.json 配置任意靶点/药物

## 快速开始

```bash
# 1. 配置监控标的
vim config.json

# 2. 建立基线（首次，不产生"新增"报告）
python3 monitor.py --init

# 3. 日常运行（建议每周一次，cron/launchd 均可）
python3 monitor.py
```

报告输出到 `reports/`，基线状态存于 `state/state.json`（**不要删除**，否则全部内容会被当成新增）。

## config.json 说明

```json
{
  "targets": [
    {
      "name": "CDH3",
      "pubmed_query": "CDH3 OR cadherin-3 OR P-cadherin",
      "pubmed_filter": "antibody OR ADC OR bispecific",
      "ctgov_query": "CDH3 OR P-cadherin"
    }
  ],
  "lookback_days": 7,
  "pubmed_max_results": 50,
  "ctgov_max_results": 50
}
```

- `pubmed_query` / `ctgov_query`：检索式，支持布尔语法
- `pubmed_filter`：可选，叠加在 query 上的过滤条件（如限定抗体/ADC 相关）
- `lookback_days`：PubMed 文献的时间窗口

## 定时运行示例（cron）

```cron
0 9 * * 1 cd /path/to/med-monitor && /usr/bin/python3 monitor.py >> monitor.log 2>&1
```

## 数据与隐私

- 只访问公开数据库（PubMed / ClinicalTrials.gov），不处理任何私有数据
- state 与 reports 均为本地文件，可自行归档

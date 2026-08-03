#!/usr/bin/env python3
"""med-monitor: 医药文献/临床试验定期监控工具 v0.1

用法:
    python3 monitor.py              # 拉取 + 对比 state + 生成周报
    python3 monitor.py --init       # 只初始化基线(不产生"新增"报告)

数据源(均免费、无需 API key):
    - PubMed: NCBI E-utilities (esearch + esummary)
    - ClinicalTrials.gov: API v2
"""
import json
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state" / "state.json"
REPORTS_DIR = BASE_DIR / "reports"
LOGS_DIR = BASE_DIR / "logs"

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ESUMMARY_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esummary.fcgi"
CTGOV_URL = "https://clinicaltrials.gov/api/v2/studies"

USER_AGENT = "med-monitor/0.1 (research monitoring)"

# 强制直连: 绕过 macOS 系统级代理 (urllib 会读系统配置, 本机代理对 NCBI 隧道不稳定)
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_get_json(url, retries=3):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    for attempt in range(retries):
        try:
            with _OPENER.open(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            if attempt == retries - 1:
                raise
            time.sleep(2 * (attempt + 1))


def fetch_pubmed(query, extra_filter, lookback_days, max_results):
    """返回 {pmid: {title, journal, pubdate}} 近 N 天文献。"""
    date_from = (datetime.now(timezone.utc) - timedelta(days=lookback_days)).strftime("%Y/%m/%d")
    date_to = datetime.now(timezone.utc).strftime("%Y/%m/%d")
    term = f"({query})"
    if extra_filter:
        term = f"({query}) AND ({extra_filter})"
    params = {
        "db": "pubmed",
        "term": term,
        "datetype": "pdat",
        "mindate": date_from,
        "maxdate": date_to,
        "retmax": str(max_results),
        "retmode": "json",
    }
    url = ESEARCH_URL + "?" + urllib.parse.urlencode(params)
    data = http_get_json(url)
    ids = data.get("esearchresult", {}).get("idlist", [])
    if not ids:
        return {}
    time.sleep(0.4)  # NCBI 限速: 无 key 时 <=3 req/s
    params = {"db": "pubmed", "id": ",".join(ids), "retmode": "json"}
    data = http_get_json(ESUMMARY_URL + "?" + urllib.parse.urlencode(params))
    result = {}
    for pmid in ids:
        doc = data.get("result", {}).get(pmid, {})
        result[pmid] = {
            "title": doc.get("title", "").strip(),
            "journal": doc.get("fulljournalname", ""),
            "pubdate": doc.get("pubdate", ""),
        }
    return result


def fetch_ctgov(query, max_results, relevance_terms=()):
    """返回 {nct_id: {title, status, phase, last_update, sponsor}}。

    API 分词宽泛 ("P-cadherin" 会命中 E/VE/N-cadherin), 因此取宽召回后
    在本地按 title+interventions 做整词/子串过滤 (relevance_terms)。
    """
    params = {
        "query.term": query,
        "pageSize": str(min(max_results, 100)),
        "fields": "NCTId,BriefTitle,OverallStatus,Phase,LastUpdatePostDate,LeadSponsorName,InterventionName",
        "format": "json",
    }
    url = CTGOV_URL + "?" + urllib.parse.urlencode(params)
    data = http_get_json(url)
    result = {}
    for study in data.get("studies", []):
        proto = study.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        status = proto.get("statusModule", {})
        design = proto.get("designModule", {})
        sponsor = proto.get("sponsorCollaboratorsModule", {})
        arms = proto.get("armsInterventionsModule", {})
        nct = ident.get("nctId")
        if not nct:
            continue
        interventions = [i.get("name", "") for i in arms.get("interventions", [])]
        # 本地相关性过滤: title 或任一 intervention 命中任一 term (大小写不敏感)
        if relevance_terms:
            haystack = (ident.get("briefTitle", "") + " " + " ".join(interventions)).lower()
            if not any(t.lower() in haystack for t in relevance_terms):
                continue
        phases = design.get("phases", [])
        result[nct] = {
            "title": ident.get("briefTitle", ""),
            "status": status.get("overallStatus", ""),
            "phase": "/".join(phases) if phases else "N/A",
            "last_update": status.get("lastUpdatePostDateStruct", {}).get("date", ""),
            "sponsor": sponsor.get("leadSponsor", {}).get("name", ""),
        }
    return result


def diff_items(old, new):
    """返回 (新增, 状态变更)。old/new 均为 {id: dict}。"""
    added = {k: v for k, v in new.items() if k not in old}
    changed = {}
    for k, v in new.items():
        if k in old and old[k] != v:
            diff_fields = {
                f: {"old": old[k].get(f), "new": v.get(f)}
                for f in v
                if old[k].get(f) != v.get(f)
            }
            if diff_fields:
                changed[k] = {"item": v, "diff": diff_fields}
    return added, changed


HIGHLIGHT_KEYWORDS = ["antibody", "adc", "bispecific", "car-t", "car t", "vhh", "nanobody"]


def star(title):
    t = title.lower()
    return " ⭐" if any(k in t for k in HIGHLIGHT_KEYWORDS) else ""


def render_report(target_name, pubmed_added, ct_added, ct_changed, lookback_days):
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        f"# 监控周报: {target_name} ({today})",
        "",
        f"覆盖窗口: 近 {lookback_days} 天 | 数据源: PubMed, ClinicalTrials.gov | ⭐=标题含抗体/ADC/双抗等关键词",
        "",
    ]
    if not pubmed_added and not ct_added and not ct_changed:
        lines.append("**本周无新增/无变更。**")
        lines.append("")
        return "\n".join(lines)

    lines.append(f"## PubMed 新文献 ({len(pubmed_added)})")
    lines.append("")
    for pmid, item in pubmed_added.items():
        lines.append(f"- PMID {pmid} | {item['pubdate']} | {item['journal']}{star(item['title'])}")
        lines.append(f"  {item['title']}")
        lines.append(f"  https://pubmed.ncbi.nlm.nih.gov/{pmid}/")
    lines.append("")

    lines.append(f"## 临床试验新增 ({len(ct_added)}, 按 Sponsor 分组)")
    lines.append("")
    by_sponsor = {}
    for nct, item in ct_added.items():
        by_sponsor.setdefault(item["sponsor"] or "未知", []).append((nct, item))
    for sponsor in sorted(by_sponsor):
        lines.append(f"### {sponsor}")
        for nct, item in by_sponsor[sponsor]:
            lines.append(
                f"- {nct} | {item['phase']} | {item['status']}{star(item['title'])}"
            )
            lines.append(f"  {item['title']}")
            lines.append(f"  https://clinicaltrials.gov/study/{nct}")
        lines.append("")

    lines.append(f"## 临床试验状态变更 ({len(ct_changed)})")
    lines.append("")
    for nct, entry in ct_changed.items():
        item = entry["item"]
        lines.append(f"- {nct} | {item['title'][:80]}")
        for field, d in entry["diff"].items():
            lines.append(f"  - {field}: {d['old']} → {d['new']}")
    lines.append("")
    return "\n".join(lines)


def main():
    init_mode = "--init" in sys.argv
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    state = json.loads(STATE_PATH.read_text(encoding="utf-8")) if STATE_PATH.exists() else {}

    for target in config["targets"]:
        name = target["name"]
        lookback = config.get("lookback_days", 7)
        print(f"[{name}] 拉取 PubMed ...", flush=True)
        pubmed = fetch_pubmed(
            target["pubmed_query"],
            target.get("pubmed_filter", ""),
            lookback,
            config.get("pubmed_max_results", 50),
        )
        print(f"[{name}] PubMed: {len(pubmed)} 条", flush=True)

        print(f"[{name}] 拉取 ClinicalTrials.gov ...", flush=True)
        ctgov = fetch_ctgov(
            target["ctgov_query"],
            config.get("ctgov_max_results", 50),
            target.get("ctgov_relevance_terms", []),
        )
        print(f"[{name}] CT.gov: {len(ctgov)} 条", flush=True)

        old = state.get(name, {"pubmed": {}, "ctgov": {}})
        pubmed_added, _ = diff_items(old.get("pubmed", {}), pubmed)
        ct_added, ct_changed = diff_items(old.get("ctgov", {}), ctgov)

        if init_mode:
            print(f"[{name}] 基线模式: 记录 {len(pubmed)} 文献 / {len(ctgov)} 试验, 不生成报告", flush=True)
        else:
            report = render_report(name, pubmed_added, ct_added, ct_changed, lookback)
            today = datetime.now().strftime("%Y%m%d")
            report_path = REPORTS_DIR / f"{name}_monitor_{today}.md"
            report_path.write_text(report, encoding="utf-8")
            print(f"[{name}] 报告: {report_path.name} "
                  f"(新文献 {len(pubmed_added)}, 新试验 {len(ct_added)}, 变更 {len(ct_changed)})", flush=True)

        state[name] = {"pubmed": pubmed, "ctgov": ctgov}

        # 运行日志: 每次运行追加一行 (时间, 标的, 统计)
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        log_line = (
            f"{datetime.now().isoformat(timespec='seconds')}\t{name}\t"
            f"pubmed={len(pubmed)}\tctgov={len(ctgov)}\t"
            f"new_pubmed={len(pubmed_added)}\tnew_ct={len(ct_added)}\tchanged_ct={len(ct_changed)}\n"
        )
        with (LOGS_DIR / "monitor.log").open("a", encoding="utf-8") as f:
            f.write(log_line)

    STATE_PATH.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    print("state 已更新。", flush=True)

    # Drive 归档: 报告 + 日志直传 (不过 Raft), config.drive_archive 非空时启用
    archive = config.get("drive_archive", "").strip()
    if archive and not init_mode:
        import subprocess
        for local_path in [REPORTS_DIR, LOGS_DIR]:
            r = subprocess.run(
                ["rclone", "copy", str(local_path), archive, "-v"],
                capture_output=True, text=True, timeout=300,
            )
            if r.returncode == 0:
                print(f"Drive 归档完成: {local_path.name} → {archive}", flush=True)
            else:
                print(f"⚠️ Drive 归档失败 ({local_path.name}): {r.stderr.strip()[:200]}", flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2: merge ct.gov + PubMed outputs into tce_report_20260803_v2.md.
Changes vs v1: two-axis classification (molecule type x lifecycle),
reviewer-mandated identity/efficacy-context fixes, 8 new products,
NCT fallback to full trial list, updated wording."""
import csv, json, os
from collections import Counter

BASE = os.path.dirname(os.path.abspath(__file__))

# ---------- load ----------
products = []
with open(os.path.join(BASE, "tce_products.txt"), encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        q, disp, tgt, comp, cat, note = (line.split("|") + [""] * 6)[:6]
        products.append(dict(query=q, display=disp, target=tgt, company=comp,
                             category=cat, note=note))

trials = {}
with open(os.path.join(BASE, "tce_trials_summary.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        trials[row["display"]] = row

raw = json.load(open(os.path.join(BASE, "tce_trials_raw.json"), encoding="utf-8"))

clin = {}
with open(os.path.join(BASE, "tce_clinical_results.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        clin.setdefault(row["显示名"], []).append(row)

NOLIT = "2023+ PubMed 未检出同行评议临床结果"

# ---------- short result strings (numbers verbatim from tce_clinical_results.csv) ----------
SHORT = {
 "Tarlatamab (Imdelltra)": "回顾性真实世界 n=204: mPFS 3.8m, mOS 11.2m (Clin Lung Cancer 2026-07, PMID 42501611)",
 "Tebentafusp/IMCgp100 (Kimmtrak)": "病例报告: 治疗>2年持久SD (Front Immunol 2026-07, PMID 42465753)",
 "Catumaxomab (Korjuny/Removab)": "CATUVAB 术中血回收可行性 n=31, 非疗效研究 (BMC Anesthesiol 2026-06, PMID 42332547)",
 "Pasritamig/JNJ-78278343": "I期 n=174: RP2D疗效人群(n=33) rPFS 7.85月, PSA50 42.4% (14/33); CRS 8.9% 全1级 (JCO 2025-08, PMID 40450573)",
 "Obrixtamig/BI 764532": "非随机I期剂量递增/扩展 n=168: ORR 23% (95% CI, 17.4%-30.2%), B2/B3方案 28%, DoR 8.5月; CRS 任意级57%/≥3级3% (JCO 2025-09, PMID 40706016)",
 "AZD5863": "临床前(亲和力调谐); I期 NCT06005493 设计中 (JITC 2025-08, PMID 40759445)",
 "ERY974": "临床前CRS机制(猴替代分子ERY22) (Toxicol Sci 2026-07, PMID 42371773)",
 "Cibisatamab/RO6958688/RO6958689": "1b期联合方案 n=52: 确认PR 7/52 (13.5%, 联合FAP-4-1BBL+obinutuzumab预处理, 非单药); CRS 57.7% (Nat Med 2026-07, PMID 42010119)",
 "Obrindatamab/MGD009": "临床前(89Zr影像, GBM模型) (PMID 40183579)",
 "Acapatamab/AMG 160": "I期: 剂量扩展队列(n=56) PSA50 30.4%, 影像PR 7.4%, rPFS 3.7月; CRS 97.4%-98.2% (CCR 2024-04, PMID 38300720)",
 "TAK-186": "文献明确已终止临床开发 (MAbs 2025-12, PMID 41207862)",
 "M701": "对照II期恶性腹水 n=84: PuFS 75 vs 25天 (p=0.0065, 显著); mOS 110 vs 76天 (p=0.1443, 未达显著) (Exp Hematol Oncol 2025-11, PMID 41275209)",
 "Ubamatamab/REGN4018": "FIH PK/剂量选择研究, 无疗效数字 (Clin Transl Sci 2024-12, PMID 39652449)",
 "Ertumaxomab": "TCE毒性系统综述/meta分析纳入 (Cancer Treat Rev 2025-09, PMID 40644745)",
 "Gocatamig/MK-6070/HPN328": "临床前NEPC模型; I/II期 NCT04471727 进行中 (Mol Cancer Ther 2026-02, PMID 41041866)",
 "Xaluritamig/AMG 509": "二手综述转述, 终点不一致: PSA50 59% (PMID 42455319) vs ~41% responses (PMID 41976311), 待原始临床报告",
 "Brenetafusp/IMC-F106C": "临床前NUT癌(预印本) (PMID 40161761)",
 "IBI389": "I期(安全性全集 n=121): CLDN18.2+ GC/GEJC亚组 ORR 22.2% (6/27), DCR 74.1%, mPFS 4.3月, mOS 10.3月; CRS 59.5% (BMC Med 2026-01, PMID 41540424)",
 "AMG 910": "临床前GC/PDAC模型 (Gastroenterology 2023-11, PMID 37507075)",
 "AMG 596": "综述: I期 acceptable safety, early indications of efficacy, 无数字 (PMID 41689667)",
 "IMC-C103C": "1/2期 n=68: 未报ORR; MAGE-A4+卵巢癌肿瘤缩小+ctDNA下降 (JITC 2026-07, PMID 42476725)",
 "Solitomab/MT110": "临床前PDX panel阳性对照 (Cells 2023-04, PMID 37190054)",
 "Pasotuxizumab/AMG 212/BAY 2010112": "FIH免疫原性分析: SC组全员中和性ADA致暴露丧失/PSA反应逆转; CIV组无ADA (Front Immunol 2023-10, PMID 37942314)",
 "CC-1": NOLIT + " (PubMed命中均为'%ID cc-1'单位误配)",
 "CM350": NOLIT + " (PubMed唯一命中为化工论文误配)",
 "HPN424": NOLIT + " (PubMed仅2020年临床前论文, 窗口外)",
 "BI 836909": NOLIT + " (PubMed仅2017年临床前论文, 窗口外)",
}

# ---------- helpers ----------
PHASE_RANK = {"已上市": 5, "Phase 3": 4, "Phase 2": 3, "Phase 1/2": 2, "Phase 1": 1, "N/A": 0, "": 0}
MARKETED = {"Tarlatamab (Imdelltra)", "Tebentafusp/IMCgp100 (Kimmtrak)",
            "Catumaxomab (Korjuny/Removab)"}

def phase_of(p):
    if p["display"] in MARKETED:
        return "已上市"
    t = trials.get(p["display"])
    ph = t["highest_phase"] if t else ""
    return "" if ph == "N/A" else ph

def lifecycle_of(p):
    if p["display"] in MARKETED:
        return "获批"
    t = trials.get(p["display"])
    if not t or t["trial_count"] == "0":
        return "无登记"
    rec = sum(int(t[s]) for s in ("status_RECRUITING", "status_NOT_YET_RECRUITING",
                                  "status_ACTIVE_NOT_RECRUITING",
                                  "status_ENROLLING_BY_INVITATION"))
    term = int(t["status_TERMINATED"]) + int(t["status_SUSPENDED"])
    wd = int(t["status_WITHDRAWN"])
    comp = int(t["status_COMPLETED"])
    unk = int(t["status_UNKNOWN"])
    if rec:
        return "招募中"
    if term:
        return "终止"
    if wd:
        return "撤回"
    if comp:
        return "完成"
    if unk:
        return "未知"
    return "未知"

def status_of(p):
    t = trials.get(p["display"])
    if not t:
        return "-"
    parts = [f'{t["trial_count"]}项']
    rec = int(t["status_RECRUITING"]) + int(t["status_NOT_YET_RECRUITING"]) + int(t["status_ENROLLING_BY_INVITATION"])
    act = int(t["status_ACTIVE_NOT_RECRUITING"])
    comp = int(t["status_COMPLETED"])
    term = int(t["status_TERMINATED"]) + int(t["status_WITHDRAWN"]) + int(t["status_SUSPENDED"])
    unk = int(t["status_UNKNOWN"])
    if rec: parts.append(f"招{rec}")
    if act: parts.append(f"进行中{act}")
    if comp: parts.append(f"完{comp}")
    if term: parts.append(f"终{term}")
    if unk: parts.append(f"未知{unk}")
    return " ".join(parts)

def all_ncts(p):
    e = raw.get(p["display"], {})
    return [t["NCTId"] for t in e.get("trials", [])]

def ncts_of(p, n=3):
    t = trials.get(p["display"])
    ids = []
    if t and t["key_ncts"]:
        ids = [x.strip() for x in t["key_ncts"].split(";") if x.strip()]
    if not ids:  # v2: fall back to full trial list (incl. terminated/completed)
        ids = all_ncts(p)
    if not ids:
        return "-"
    s = ", ".join(ids[:n])
    if len(ids) > n:
        s += f" 等{len(ids)}项"
    return s

CAT_ORDER = ["常规抗体TCE", "TCR×CD3", "条件激活", "TriTAC·三特异"]

def sorted_products(cat):
    ps = [p for p in products if p["category"] == cat]
    return sorted(ps, key=lambda p: (-PHASE_RANK.get(phase_of(p), 0), p["query"]))

# ---------- stats ----------
n_total = len(products)
phase_dist = Counter(phase_of(p) for p in products)
n_with_results = sum(1 for p in products
                     if p["display"] in clin
                     and not clin[p["display"]][0]["关键疗效结果"].startswith(NOLIT))
assoc = sum(int(trials[p["display"]]["trial_count"]) for p in products if p["display"] in trials)
unique_ncts = len({nct for p in products for nct in all_ncts(p)})
crosstab = Counter((p["category"], lifecycle_of(p)) for p in products)

# ---------- build ----------
L = []
A = L.append
A("# 实体瘤 TCE 产品进展与最新临床结果 v2 (截至 2026-08-03)")
A("")
A("> **数据来源**: ClinicalTrials.gov 试验登记 (一阶段, 52 产品全命中) + PubMed 2023-01-01 以来临床结果类文献 (二阶段, E-utilities 拉取, 疗效数字一律照抄摘要原文)。")
A("> **编制说明**: 本报告为机械拉取初稿, 研究侧 (@徐陆恺) 复核流程中。会议摘要 (ASCO/ESMO/AACR) 与公司更新未纳入本版。")
A("> **v2 变更**: 按 @徐陆恺 复核意见修订 — 产品身份修正 (pasritamig/KLK2、alveltamig/泽璟、nivatrotamab=Hu3F8-BsAb 合并、PF-07062119/GUCY2C、QLF4113/CD2 等)、分类改两轴 (分子类型×生命周期)、新增 8 产品、补漏 NCT、疗效语境逐条标注。")
A("")
A("## 1. 总览统计")
A("")
A(f"- 产品总数: **{n_total}** (v1 47 - 移除 2 - 合并 1 + 新增 8)")
A(f"- 试验登记口径: **{assoc} 个产品-试验关联, {unique_ncts} 个唯一 NCT** (同一 NCT 可关联多个产品; 共享 NCT 2 个: NCT04262466→tebentafusp/brenetafusp, NCT07258121→alveltamig/ZGGS34)")
A(f"  - 口径说明: 复核意见中的 191/186 对应 v1 (47 产品) 数据集; v2 新增 8 品 (+10 关联)、移除/合并 3 项 (-6 关联) 后实为 {assoc}/{unique_ncts}")
A(f"- 已获批: **3** — Tarlatamab (SCLC), Tebentafusp (葡萄膜黑色素瘤), Catumaxomab (2025-02-10 以 Korjuny 获 EU 上市许可, EMA EPAR; 旧品牌 Removab 曾撤市)")
dist = " | ".join(f"{k or '无登记'}: {v}" for k, v in
                 sorted(phase_dist.items(), key=lambda kv: -PHASE_RANK.get(kv[0], 0)))
A(f"- 最高阶段分布: {dist}")
A(f"- 有 2023+ 公开结果/文献的产品: **{n_with_results}** / {n_total} (含明确 ORR 数字: Obrixtamig, IBI389; 联合方案 PR 率: Cibisatamab; PSA50: Pasritamig, Acapatamab)")
A("")
A("### 分子类型 × 生命周期 交叉统计")
A("")
lifes = ["获批", "招募中", "完成", "终止", "撤回", "未知"]
A("| 分子类型 | " + " | ".join(lifes) + " | 合计 |")
A("|" + "---|" * (len(lifes) + 2))
for cat in CAT_ORDER:
    cells = [str(crosstab.get((cat, lf), 0)) for lf in lifes]
    tot = sum(crosstab.get((cat, lf), 0) for lf in lifes)
    A(f"| {cat} | " + " | ".join(cells) + f" | {tot} |")
sums = [str(sum(crosstab.get((c, lf), 0) for c in CAT_ORDER)) for lf in lifes]
A(f"| 合计 | " + " | ".join(sums) + f" | {n_total} |")
A("")
A("## 2. 主表 (按分子类型分组, 组内按最高阶段降序)")
A("")
hdr = "| 产品 | 靶点 | 厂家 | 最高阶段 | 生命周期 | 登记状态 | 最新临床结果 | 关键 NCT |"
sep = "|---|---|---|---|---|---|---|---|"
for cat in CAT_ORDER:
    ps = sorted_products(cat)
    if not ps:
        continue
    A(f"### {cat} ({len(ps)} 项)")
    A("")
    A(hdr); A(sep)
    for p in ps:
        res = SHORT.get(p["display"], NOLIT)
        A(f'| {p["query"]} | {p["target"]} | {p["company"]} | {phase_of(p) or "-"} | {lifecycle_of(p)} | {status_of(p)} | {res} | {ncts_of(p)} |')
    A("")
A("> 注: 「关键 NCT」优先列招募中/有结果的试验; 无在研试验的产品列出全部登记 NCT。登记状态的 UNKNOWN 为 ct.gov 长期未更新标记。")
A("")

# ---------- highlights ----------
A("## 3. 重点产品 (有明确疗效/生存数字)")
A("")
HIGHLIGHTS = [
 ("Pasritamig/JNJ-78278343", "KLK2×CD3, Janssen"),
 ("Obrixtamig/BI 764532", "DLL3×CD3, Boehringer Ingelheim"),
 ("IBI389", "CLDN18.2×CD3, 信达生物"),
 ("Cibisatamab/RO6958688/RO6958689", "CEA×CD3, Roche"),
 ("Acapatamab/AMG 160", "PSMA×CD3, Amgen"),
 ("Xaluritamig/AMG 509", "STEAP1×CD3, Amgen"),
 ("M701", "EpCAM×CD3, 武汉友芝友"),
 ("Tarlatamab (Imdelltra)", "DLL3×CD3, Amgen (获批)"),
]
for disp, sub in HIGHLIGHTS:
    rows = clin.get(disp, [])
    if not rows:
        continue
    r = rows[0]
    A(f"### {disp.split('(')[0].strip()} ({sub})")
    A("")
    A(f"- 来源: {r['期刊']} {r['发表日期']}, PMID {r['PMID']}; 阶段: {r['阶段']}; 样本量: {r['样本量']}")
    A(f"- 疗效 (摘要原文): \"{r['关键疗效结果']}\"")
    if r["安全性要点"] and r["安全性要点"] != "摘要未报告":
        A(f"- 安全性 (摘要原文): \"{r['安全性要点']}\"")
    else:
        A("- 安全性: 摘要未报告")
    if r["备注"]:
        A(f"- 语境/备注: {r['备注']}")
    for r2 in rows[1:]:
        A(f"- 另见 {r2['期刊']} {r2['发表日期']} (PMID {r2['PMID']}): \"{r2['关键疗效结果']}\"")
    A("")

# ---------- terminated ----------
A("## 4. 终止 / 撤回项目")
A("")
tak = clin.get("TAK-186", [{}])[0]
A(f"- **TAK-186** (EGFR×CD3, Takeda): ct.gov 2 项试验终止/撤回; 文献 (MAbs 2025-12, PMID {tak.get('PMID','41207862')}) 明确其为 \"a multidomain T cell engager that has been discontinued from clinical development\"。")
A("- **Ertumaxomab** (HER2×CD3, Neovii): ct.gov 4 项试验全部终止 (最近更新 2016-05); 2023+ 仅见于 TCE 毒性系统综述 (PMID 40644745)。")
A("- **PF-06671008** (P-cadherin×CD3, Pfizer): 唯一 I 期 NCT02659631 已终止 (2020-05); 2023+ PubMed 未检出同行评议临床结果。")
term_others = [p["query"] for p in products
               if lifecycle_of(p) in ("终止", "撤回")
               and p["query"] not in ("TAK-186", "ertumaxomab", "PF-06671008")]
A(f"- 其余生命周期为终止/撤回的产品 ({len(term_others)}): {', '.join(term_others)} (详见主表生命周期列)。")
A("")
A("## 5. 监管状态备注")
A("")
A("- **Catumaxomab** (EpCAM×CD3, Lindis/Neovii): 2025-02-10 以 **Korjuny** 获 EU 上市许可 (EMA EPAR Korjuny); 旧品牌 Removab 曾撤市, 现为重新获批。ct.gov 18 项试验多为历史研究 (13 完成、2 终止、3 未知, 最近更新 2025-01); 2023+ 文献仅 CATUVAB 术中血回收可行性研究 (PMID 42332547), 无新疗效数据。")
A("")
A("## 6. 附录")
A("")
A("### 6.1 全部产品 NCT 清单 (压缩版)")
A("")
A("| 产品 | 试验数 | NCT |")
A("|---|---|---|")
for p in products:
    ids = all_ncts(p)
    if not ids:
        s = "-"
    else:
        s = ", ".join(ids[:4]) + (f" 等{len(ids)}项" if len(ids) > 4 else "")
    t = trials.get(p["display"], {})
    A(f'| {p["query"]} | {t.get("trial_count","-")} | {s} |')
A("")
A("### 6.2 v2 移出产品")
A("")
A("- **JNJ-87189401** (PSMA×CD28): 共刺激配伍双抗, 非 CD3 TCE, 误命中移除 (仍见于 NCT06095089 联合方案)。")
A("- **JNJ-101556143**: 联合试验误命中 (NCT06800313 的 HLD-0915 为口服胶囊), 移除。")
A("")
A("---")
A("*v2: 已按 @徐陆恺 复核意见修订, 待最终统计核对。数字均照抄 ct.gov 登记与 PubMed 摘要原文, 未经人工独立核实; 会议摘要 (ASCO/ESMO/AACR) 与公司更新未纳入本版。*")

out = os.path.join(BASE, "tce_report_20260803_v2.md")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")
print("written:", out, "lines:", len(L))
print(f"products={n_total} assoc={assoc} unique_ncts={unique_ncts} with_results={n_with_results}")
print("phase dist:", dict(phase_dist))
print("crosstab:")
for cat in CAT_ORDER:
    print(" ", cat, {lf: crosstab.get((cat, lf), 0) for lf in lifes})

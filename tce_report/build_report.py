#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Merge stage-1 (ct.gov) + stage-2 (PubMed) outputs into tce_report_20260803.md.
All efficacy numbers are copied verbatim from the two source CSVs."""
import csv, os, re

BASE = os.path.dirname(os.path.abspath(__file__))

# ---------- load sources ----------
products = []  # query, display, target, company, category, note
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

clin = {}  # display -> list of rows
with open(os.path.join(BASE, "tce_clinical_results.csv"), encoding="utf-8") as f:
    for row in csv.DictReader(f):
        clin.setdefault(row["显示名"], []).append(row)

# ---------- short result strings for main table (numbers verbatim from tce_clinical_results.csv) ----------
SHORT = {
 "Tarlatamab (Imdelltra)": "真实世界 n=204: mPFS 3.8m, mOS 11.2m (Clin Lung Cancer 2026-07, PMID 42501611)",
 "Tebentafusp/IMCgp100 (Kimmtrak)": "病例报告: 治疗>2年持久SD (Front Immunol 2026-07, PMID 42465753)",
 "Catumaxomab (Removab)": "CATUVAB 术中血回收可行性 n=31, 非疗效研究 (BMC Anesthesiol 2026-06, PMID 42332547)",
 "Obrixtamig/BI 764532": "I期 n=168: ORR 23% (95% CI, 17.4%-30.2%), B2/B3方案 28%, DoR 8.5月; CRS 任意级57%/≥3级3% (JCO 2025-09, PMID 40706016)",
 "AZD5863": "临床前(亲和力调谐); I期 NCT06005493 设计中 (JITC 2025-08, PMID 40759445)",
 "ERY974": "临床前CRS机制(猴替代分子ERY22) (Toxicol Sci 2026-07, PMID 42371773)",
 "Cibisatamab/RO6958688/RO6958689": "1b期 n=52: 确认PR 7/52 (13.5%); CRS 57.7% (≥3级 3.8%) (Nat Med 2026-07, PMID 42010119)",
 "Obrindatamab/MGD009": "临床前(89Zr影像, GBM模型) (PMID 40183579)",
 "Acapatamab/AMG 160": "I期 n=133: PSA50 30.4%, 影像PR 7.4%, rPFS 3.7月; CRS 97.4%-98.2% (CCR 2024-04, PMID 38300720)",
 "TAK-186": "文献明确已终止临床开发 (MAbs 2025-12, PMID 41207862)",
 "M701": "II期恶性腹水 n=84: PuFS 75 vs 25天 (p=0.0065), mOS 110 vs 76天 (Exp Hematol Oncol 2025-11, PMID 41275209)",
 "Ubamatamab/REGN4018": "FIH PK/剂量选择研究, 无疗效数字 (Clin Transl Sci 2024-12, PMID 39652449)",
 "Ertumaxomab": "TCE毒性系统综述/meta分析纳入 (Cancer Treat Rev 2025-09, PMID 40644745)",
 "Gocatamig/MK-6070/HPN328": "临床前NEPC模型; I/II期 NCT04471727 进行中 (Mol Cancer Ther 2026-02, PMID 41041866)",
 "Xaluritamig/AMG 509": "综述转述: PSA50 59% (PMID 42455319); mCRPC ~41% responses, step-up给药降CRS (PMID 41976311)",
 "Brenetafusp/IMC-F106C": "临床前NUT癌(预印本) (PMID 40161761)",
 "IBI389": "I期 n=121: ORR 22.2% (6/27), DCR 74.1%, mPFS 4.3月, mOS 10.3月; CRS 59.5% (BMC Med 2026-01, PMID 41540424)",
 "AMG 910": "临床前GC/PDAC模型 (Gastroenterology 2023-11, PMID 37507075)",
 "AMG 596": "综述: I期 acceptable safety, early indications of efficacy, 无数字 (PMID 41689667)",
 "IMC-C103C": "1/2期 n=68: 未报ORR; MAGE-A4+卵巢癌肿瘤缩小+ctDNA下降 (JITC 2026-07, PMID 42476725)",
 "Solitomab/MT110": "临床前PDX panel阳性对照 (Cells 2023-04, PMID 37190054)",
 "CC-1": "暂无 2023+ 公开结果 (PubMed命中均为'%ID cc-1'单位误配)",
 "CM350": "暂无 2023+ 公开结果 (PubMed唯一命中为化工论文误配)",
}
NO_RESULT = "暂无 2023+ 公开结果"

# ---------- helpers ----------
PHASE_RANK = {"已上市": 5, "Phase 3": 4, "Phase 2": 3, "Phase 1/2": 2, "Phase 1": 1, "": 0}
MARKETED = {"Tarlatamab (Imdelltra)", "Tebentafusp/IMCgp100 (Kimmtrak)"}

def phase_of(p):
    if p["display"] in MARKETED:
        return "已上市"
    t = trials.get(p["display"])
    return t["highest_phase"] if t else ""

def status_of(p):
    t = trials.get(p["display"])
    if not t:
        return "-"
    parts = [f'{t["trial_count"]}项']
    rec = int(t["status_RECRUITING"]) + int(t["status_NOT_YET_RECRUITING"]) + int(t["status_ENROLLING_BY_INVITATION"])
    act = int(t["status_ACTIVE_NOT_RECRUITING"])
    comp = int(t["status_COMPLETED"])
    term = int(t["status_TERMINATED"]) + int(t["status_WITHDRAWN"]) + int(t["status_SUSPENDED"])
    if rec: parts.append(f"招{rec}")
    if act: parts.append(f"进行中{act}")
    if comp: parts.append(f"完{comp}")
    if term: parts.append(f"终{term}")
    return " ".join(parts)

def ncts_of(p, n=3):
    t = trials.get(p["display"])
    if not t or not t["key_ncts"]:
        return "-"
    ids = [x.strip() for x in t["key_ncts"].split(";") if x.strip()]
    s = ", ".join(ids[:n])
    if len(ids) > n:
        s += f" 等{len(ids)}项"
    return s

CAT_ORDER = ["常规抗体TCE", "TCR×CD3", "掩蔽/条件激活", "三特异", "历史终止"]

def sorted_products(cat):
    ps = [p for p in products if p["category"] == cat]
    return sorted(ps, key=lambda p: (-PHASE_RANK.get(phase_of(p), 0), p["query"]))

# ---------- section 2 stats ----------
n_total = len(products)
n_marketed = len(MARKETED)
from collections import Counter
phase_dist = Counter(phase_of(p) for p in products)
n_with_results = sum(1 for p in products
                     if p["display"] in clin and not clin[p["display"]][0]["关键疗效结果"].startswith("无 2023+"))

# ---------- build markdown ----------
L = []
A = L.append
A("# 实体瘤 TCE 产品进展与最新临床结果 (截至 2026-08-03)")
A("")
A("> **数据来源**: ClinicalTrials.gov 试验登记 (一阶段, 47 产品全命中) + PubMed 2023-01-01 以来临床结果类文献 (二阶段, E-utilities 拉取, 疗效数字一律照抄摘要原文)。")
A("> **编制说明**: 本报告为机械拉取初稿, 研究侧 (@徐陆恺) 复核流程中。")
A("")
A("## 1. 总览统计")
A("")
A(f"- 产品总数: **{n_total}** (含历史终止 2 项)")
A(f"- 已上市: **{n_marketed}** (Tarlatamab/SCLC, Tebentafusp/葡萄膜黑色素瘤); Catumaxomab 监管状态待核准")
dist = " | ".join(f"{k or '无登记'}: {v}" for k, v in
                 sorted(phase_dist.items(), key=lambda kv: -PHASE_RANK.get(kv[0], 0)))
A(f"- 最高阶段分布: {dist}")
A(f"- 有 2023+ 公开结果/文献的产品: **{n_with_results}** / {n_total} (其中含明确 ORR 数字的仅 Obrixtamig, IBI389; Cibisatamab 报确认 PR 率)")
A("")
A("## 2. 主表 (按分类分组, 组内按最高阶段降序)")
A("")
hdr = "| 产品 | 靶点 | 厂家 | 最高阶段 | 登记状态摘要 | 最新临床结果 | 关键 NCT |"
sep = "|---|---|---|---|---|---|---|"
for cat in CAT_ORDER:
    ps = sorted_products(cat)
    if not ps:
        continue
    A(f"### {cat} ({len(ps)} 项)")
    A("")
    A(hdr); A(sep)
    for p in ps:
        res = SHORT.get(p["display"], NO_RESULT)
        note = f' ({p["note"]})' if p["note"] and p["note"] not in ("已上市(SCLC)", "已上市(葡萄膜黑色素瘤)") else ""
        A(f'| {p["query"]} | {p["target"]} | {p["company"]} | {phase_of(p)} | {status_of(p)} | {res} | {ncts_of(p)} |')
    A("")

# ---------- section 3 highlights ----------
A("## 3. 重点产品 (有明确疗效/生存数字)")
A("")
HIGHLIGHTS = [
 ("Obrixtamig/BI 764532", "DLL3×CD3, Boehringer Ingelheim"),
 ("IBI389", "CLDN18.2×CD3, 信达生物"),
 ("Cibisatamab/RO6958688/RO6958689", "CEA×CD3, Roche"),
 ("Acapatamab/AMG 160", "PSMA×CD3, Amgen"),
 ("Xaluritamig/AMG 509", "STEAP1×CD3, Amgen"),
 ("M701", "EpCAM×CD3, 武汉友芝友"),
 ("Tarlatamab (Imdelltra)", "DLL3×CD3, Amgen (已上市)"),
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
    for r2 in rows[1:]:
        A(f"- 另见 {r2['期刊']} {r2['发表日期']} (PMID {r2['PMID']}): \"{r2['关键疗效结果']}\"")
    A("")

# ---------- section 4 terminated ----------
A("## 4. 终止 / 下架 / 监管待定项目")
A("")
tak = clin.get("TAK-186", [{}])[0]
A(f"- **TAK-186** (EGFR×CD3, Takeda): ct.gov 2 项试验均终止/撤回; 文献 (MAbs 2025-12, PMID {tak.get('PMID','41207862')}) 明确其为 \"a multidomain T cell engager that has been discontinued from clinical development\"。")
A("- **Ertumaxomab** (HER2×CD3, Neovii, 历史终止): ct.gov 4 项试验全部终止 (最近更新 2016-05); 2023+ 仅见于 TCE 毒性系统综述 (PMID 40644745)。")
A("- **PF-06671008** (P-cadherin×CD3, Pfizer, 历史终止): 唯一 I 期 NCT02659631 已终止 (2020-05); 无 2023+ 文献。")
A("- **Catumaxomab** (EpCAM×CD3, Lindis/Neovii): 监管状态**待核准**; ct.gov 18 项中 13 项完成、2 项终止、3 项状态未知 (最近更新 2025-01); 2023+ 文献仅 CATUVAB 术中血回收可行性研究 (PMID 42332547), 无新疗效数据。")
A("")

# ---------- section 5 appendix ----------
A("## 5. 附录: 全部产品 NCT 清单 (压缩版)")
A("")
A("| 产品 | 试验数 | 关键 NCT |")
A("|---|---|---|")
for p in products:
    t = trials.get(p["display"], {})
    A(f'| {p["query"]} | {t.get("trial_count","-")} | {ncts_of(p, 4)} |')
A("")
A("---")
A("*本报告为数据拉取初稿, 待研究侧 (@徐陆恺) 复核。数字均照抄 ct.gov 登记与 PubMed 摘要原文, 未经人工独立核实。*")

out = os.path.join(BASE, "tce_report_20260803.md")
with open(out, "w", encoding="utf-8") as f:
    f.write("\n".join(L) + "\n")
print("written:", out, "lines:", len(L))
print("with results:", n_with_results, "phase dist:", dict(phase_dist))

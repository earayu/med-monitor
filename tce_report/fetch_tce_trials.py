#!/usr/bin/env python3
"""Fetch ClinicalTrials.gov v2 trials for solid-tumor TCE product list.

Stdlib only. Direct connection (bypass system proxy). Rate limit >=0.4s.
Outputs: tce_trials_raw.json, tce_trials_summary.csv, tce_fetch_log.txt
"""
import csv
import json
import os
import re
import time
import urllib.parse
import urllib.request

BASE = "https://clinicaltrials.gov/api/v2/studies"
FIELDS = ("NCTId,BriefTitle,OverallStatus,Phase,LeadSponsorName,"
          "InterventionName,StartDate,LastUpdatePostDate,HasResults,EnrollmentCount")
HERE = os.path.dirname(os.path.abspath(__file__))
PRODUCTS = os.path.join(HERE, "tce_products.txt")
RAW_JSON = os.path.join(HERE, "tce_trials_raw.json")
SUMMARY_CSV = os.path.join(HERE, "tce_trials_summary.csv")
LOG_FILE = os.path.join(HERE, "tce_fetch_log.txt")

OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))
MIN_INTERVAL = 0.4
_last_req = 0.0

PHASE_RANK = {
    "NA": 0, "EARLY_PHASE1": 1, "PHASE1": 2, "PHASE1_PHASE2": 3,
    "PHASE2": 4, "PHASE2_PHASE3": 5, "PHASE3": 6, "PHASE4": 7,
}
PHASE_LABEL = {
    "NA": "N/A", "EARLY_PHASE1": "Early Phase 1", "PHASE1": "Phase 1",
    "PHASE1_PHASE2": "Phase 1/2", "PHASE2": "Phase 2",
    "PHASE2_PHASE3": "Phase 2/3", "PHASE3": "Phase 3", "PHASE4": "Phase 4",
}
STATUS_ORDER = ["RECRUITING", "NOT_YET_RECRUITING", "ACTIVE_NOT_RECRUITING",
                "ENROLLING_BY_INVITATION", "COMPLETED", "SUSPENDED",
                "TERMINATED", "WITHDRAWN", "UNKNOWN"]


def http_get(url, retries=3):
    global _last_req
    for attempt in range(retries):
        wait = MIN_INTERVAL - (time.time() - _last_req)
        if wait > 0:
            time.sleep(wait)
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "tce-monitor/1.0"})
            with OPENER.open(req, timeout=30) as resp:
                _last_req = time.time()
                return json.loads(resp.read().decode("utf-8"))
        except Exception as e:
            _last_req = time.time()
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt * 2)
    return None


def fetch_query(param_key, param_val):
    """Fetch all pages for one query; returns list of raw study dicts."""
    studies = []
    page_token = None
    while True:
        params = {"format": "json", "pageSize": "100", "fields": FIELDS,
                  param_key: param_val, "countTotal": "true"}
        if page_token:
            params["pageToken"] = page_token
        url = BASE + "?" + urllib.parse.urlencode(params)
        data = http_get(url)
        studies.extend(data.get("studies", []))
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    return studies


def fetch_product(query_name):
    """query.intr first; fallback query.term on 0 hits. Returns (studies, notes)."""
    notes = []
    studies = fetch_query("query.intr", query_name)
    if studies:
        notes.append(f"intr '{query_name}': {len(studies)} hits")
        return studies, notes
    studies = fetch_query("query.term", f'"{query_name}"')
    notes.append(f"intr 0 hits -> term '\"{query_name}\"': {len(studies)} hits")
    return studies, notes


def alias_terms(query_name, display_name):
    """Candidate terms: query name + slash-separated aliases from display name."""
    terms = [query_name]
    # strip parenthetical brand names e.g. "(Imdelltra)"
    disp = re.sub(r"\([^)]*\)", "", display_name)
    for part in re.split(r"[/|]", disp):
        part = part.strip()
        if part and part.lower() not in {t.lower() for t in terms}:
            terms.append(part)
    return terms


def norm_study(s):
    proto = s.get("protocolSection", {})
    ident = proto.get("identificationModule", {})
    status = proto.get("statusModule", {})
    design = proto.get("designModule", {})
    arms = proto.get("armsInterventionsModule", {})
    derived = s.get("derivedSection", {})
    phases = design.get("phases", ["NA"])
    phase = phases[0] if phases else "NA"
    if len(phases) > 1:
        phase = "_".join(phases)
    return {
        "NCTId": ident.get("nctId", ""),
        "BriefTitle": ident.get("briefTitle", ""),
        "OverallStatus": status.get("overallStatus", ""),
        "Phase": phase,
        "LeadSponsorName": proto.get("sponsorCollaboratorsModule", {})
                                 .get("leadSponsor", {}).get("name", ""),
        "InterventionName": "; ".join(
            i.get("name", "") for i in arms.get("interventions", [])),
        "StartDate": status.get("startDateStruct", {}).get("date", ""),
        "LastUpdatePostDate": status.get("lastUpdatePostDateStruct", {}).get("date", ""),
        "HasResults": bool(s.get("hasResults", False)),
        "EnrollmentCount": design.get("enrollmentInfo", {}).get("count", ""),
    }


# Product-specific relevance post-filters (short query names cause intr
# partial-match noise). Key: query name. Value: predicate on normed trial.
RELEVANCE_FILTERS = {
    "CC-1": lambda t: bool(re.search(r"\bCC-1\b", t["InterventionName"], re.I)),
}

# v2: NCTs known to belong to a product but not matched by name queries
# (reviewer-supplied). Key: display name. Fetched via single-study endpoint.
EXTRA_NCTS = {
    "CX-904": ["NCT05387265"],
    "ISB 1302": ["NCT03983395"],
    "M802": ["NCT04501770"],
    "IBI389": ["NCT05164458"],
    "Obrindatamab/MGD009": ["NCT02628535", "NCT03406949"],
    "HPN536": ["NCT03872206"],
    "IMC-C103C": ["NCT03973333"],
    "Solitomab/MT110": ["NCT00635596"],
}

# v3: manual adjudication exclusions. NCT07258121 has conflicting ct.gov
# fields (title=ZGGS34, intervention mistakenly filled as ZG006); research
# side ruled it belongs to ZGGS34 only.
EXCLUDE_NCTS = {
    "Alveltamig/ZG006": ["NCT07258121"],
}


def fetch_study_by_id(nct_id):
    """Fetch one study by NCT id via the single-study endpoint."""
    url = f"{BASE}/{nct_id}?" + urllib.parse.urlencode(
        {"format": "json", "fields": FIELDS})
    return http_get(url)


def main():
    products = []
    with open(PRODUCTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = [p.strip() for p in line.split("|")]
            parts += [""] * (6 - len(parts))
            products.append({
                "query": parts[0], "display": parts[1], "target": parts[2],
                "company": parts[3], "category": parts[4], "note": parts[5],
            })

    log_lines = [f"# fetch log {time.strftime('%Y-%m-%d %H:%M:%S')}"]
    raw = {}
    summary_rows = []
    zero_hit = []

    for p in products:
        merged = {}
        notes = []
        try:
            terms = alias_terms(p["query"], p["display"])
            for term in terms:
                studies, ns = fetch_product(term)
                notes.extend(ns)
                for s in studies:
                    n = norm_study(s)
                    if n["NCTId"]:
                        merged[n["NCTId"]] = n
            for nct in EXTRA_NCTS.get(p["display"], []):
                if nct not in merged:
                    s = fetch_study_by_id(nct)
                    if s:
                        n = norm_study(s)
                        if n["NCTId"]:
                            merged[n["NCTId"]] = n
                            notes.append(f"extra NCT added: {nct}")
        except Exception as e:
            log_lines.append(f"ERROR {p['display']}: {e!r}")
            notes.append(f"ERROR: {e!r}")

        trials = sorted(merged.values(), key=lambda t: t["NCTId"])
        excl = set(EXCLUDE_NCTS.get(p["display"], []))
        if excl:
            before = len(trials)
            trials = [t for t in trials if t["NCTId"] not in excl]
            if len(trials) != before:
                notes.append(f"manual exclusion: {before} -> {len(trials)} "
                             f"({', '.join(sorted(excl))})")
        filt = RELEVANCE_FILTERS.get(p["query"])
        if filt:
            before = len(trials)
            trials = [t for t in trials if filt(t)]
            if len(trials) != before:
                notes.append(f"relevance filter: {before} -> {len(trials)}")
        raw[p["display"]] = {
            "meta": {k: p[k] for k in ("query", "target", "company", "category", "note")},
            "query_notes": notes,
            "trial_count": len(trials),
            "trials": trials,
        }
        log_lines.append(f"{p['display']}: {len(trials)} trials | " + "; ".join(notes))
        if not trials:
            zero_hit.append(p["display"])

        statuses = {}
        for t in trials:
            statuses[t["OverallStatus"]] = statuses.get(t["OverallStatus"], 0) + 1
        best_phase = "NA"
        for t in trials:
            if PHASE_RANK.get(t["Phase"], 0) > PHASE_RANK.get(best_phase, 0):
                best_phase = t["Phase"]
        latest_update = max((t["LastUpdatePostDate"] for t in trials
                             if t["LastUpdatePostDate"]), default="")
        n_results = sum(1 for t in trials if t["HasResults"])
        key_ncts = "; ".join(
            t["NCTId"] for t in trials
            if t["OverallStatus"] in ("RECRUITING", "ACTIVE_NOT_RECRUITING",
                                      "NOT_YET_RECRUITING")
            or t["HasResults"])[:500]
        row = {
            "display": p["display"], "target": p["target"], "company": p["company"],
            "trial_count": len(trials),
            "highest_phase": PHASE_LABEL.get(best_phase, best_phase),
            "latest_update": latest_update, "has_results_count": n_results,
            "key_ncts": key_ncts,
        }
        for st in STATUS_ORDER:
            row["status_" + st] = statuses.get(st, 0)
        summary_rows.append(row)
        print(f"[{len(summary_rows)}/{len(products)}] {p['display']}: {len(trials)}", flush=True)

    with open(RAW_JSON, "w", encoding="utf-8") as f:
        json.dump(raw, f, ensure_ascii=False, indent=2)

    fieldnames = (["display", "target", "company", "trial_count", "highest_phase"]
                  + ["status_" + s for s in STATUS_ORDER]
                  + ["latest_update", "has_results_count", "key_ncts"])
    with open(SUMMARY_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(summary_rows)

    log_lines.append("")
    log_lines.append(f"TOTAL products: {len(products)}")
    log_lines.append(f"ZERO-HIT products ({len(zero_hit)}): " +
                     (", ".join(zero_hit) if zero_hit else "none"))
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(log_lines) + "\n")

    print(f"DONE. products={len(products)} zero_hit={len(zero_hit)}")
    for z in zero_hit:
        print(f"  ZERO: {z}")


if __name__ == "__main__":
    main()

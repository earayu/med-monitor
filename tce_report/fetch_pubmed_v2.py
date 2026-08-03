#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""v2 incremental PubMed fetch: only renamed/merged/new products.
Merges into pubmed_hits.json; removes stale keys from v1."""
import json, os, re, sys, time, urllib.parse, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE, "pubmed_abstracts")
SUMMARY = os.path.join(BASE, "pubmed_hits.json")
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
DATE_MIN, DATE_MAX = "2023/01/01", "2026/08/03"

# display -> explicit alias list (avoids relying on display-name parsing)
TARGETS = {
    "Pasritamig/JNJ-78278343": ["pasritamig", "JNJ-78278343"],
    "Alveltamig/ZG006": ["alveltamig", "ZG006"],
    "Nivatrotamab/Hu3F8-BsAb": ["nivatrotamab", "Hu3F8-BsAb", "hu3F8 bispecific"],
    "ZGGS34": ["ZGGS34"],
    "HPN424": ["HPN424"],
    "Pasotuxizumab/AMG 212/BAY 2010112": ["pasotuxizumab", "AMG 212", "BAY 2010112"],
    "AMG 211/MEDI-565": ["AMG 211", "MEDI-565"],
    "BI 836909": ["BI 836909"],
    "GEN1044": ["GEN1044"],
    "GEN1047": ["GEN1047"],
    "AMX-818/SAR446368": ["AMX-818", "SAR446368"],
}
STALE_KEYS = ["JNJ-78278343", "JNJ-87189401", "JNJ-101556143", "ZG006",
              "Nivatrotamab", "hu3F8×CD3 bispecific"]

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
os.makedirs(OUTDIR, exist_ok=True)
_last = [0.0]

def http_get(url):
    wait = 0.45 - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):
        try:
            _last[0] = time.time()
            with opener.open(url, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:
            print(f"  retry {attempt+1}/3: {e}", file=sys.stderr)
            time.sleep(1.5 * (attempt + 1))
    return None

def esearch(term):
    q = urllib.parse.urlencode({
        "db": "pubmed", "term": term, "retmode": "json",
        "retmax": "5", "sort": "date",
        "mindate": DATE_MIN, "maxdate": DATE_MAX, "datetype": "pdat"})
    txt = http_get(f"{ESEARCH}?{q}")
    if not txt:
        return []
    try:
        return json.loads(txt)["esearchresult"].get("idlist", [])
    except Exception:
        return []

def efetch(pmid):
    q = urllib.parse.urlencode({"db": "pubmed", "id": pmid,
                                "rettype": "abstract", "retmode": "text"})
    return http_get(f"{EFETCH}?{q}")

def main():
    with open(SUMMARY, encoding="utf-8") as f:
        results = json.load(f)
    for k in STALE_KEYS:
        results.pop(k, None)
    for disp, als in TARGETS.items():
        alias_clause = " OR ".join(f'"{a}"[Title/Abstract]' for a in als)
        strict = (f'({alias_clause}) AND (clinical trial[Publication Type] OR '
                  f'phase[Title/Abstract] OR patients[Title/Abstract])')
        ids = esearch(strict)
        relaxed = False
        if not ids:
            ids = esearch(f'({alias_clause})')
            relaxed = True
        print(f"{disp}: {len(ids)} hits {'(relaxed)' if relaxed and ids else ''}",
              flush=True)
        entry = {"ids": ids, "relaxed": relaxed, "abstracts": {}}
        for pmid in ids[:2]:
            abst = efetch(pmid)
            if abst:
                entry["abstracts"][pmid] = abst
                with open(os.path.join(OUTDIR, f"{pmid}.txt"), "w",
                          encoding="utf-8") as f:
                    f.write(abst)
        results[disp] = entry
    with open(SUMMARY, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print("merged into pubmed_hits.json")

if __name__ == "__main__":
    main()

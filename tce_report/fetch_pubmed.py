#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Stage 2: fetch recent clinical-result abstracts from PubMed for each TCE product.
Bypasses system proxy, stdlib only, rate-limited, retries."""
import json, os, re, sys, time, urllib.parse, urllib.request

BASE = os.path.dirname(os.path.abspath(__file__))
PRODUCTS = os.path.join(BASE, "tce_products.txt")
OUTDIR = os.path.join(BASE, "pubmed_abstracts")
SUMMARY = os.path.join(BASE, "pubmed_hits.json")
ESEARCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
EFETCH = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
DATE_MIN, DATE_MAX = "2023/01/01", "2026/08/03"

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
os.makedirs(OUTDIR, exist_ok=True)

_last = [0.0]
def http_get(url):
    # rate limit: >=0.4s between requests
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
        "mindate": DATE_MIN, "maxdate": DATE_MAX, "datetype": "pdat",
    })
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

def aliases(query_name, display_name):
    """Build OR-combined alias list from query name and parenthesized/slashed names."""
    als = [query_name]
    # pull slash-separated aliases out of display name, e.g. "Obrixtamig/BI 764532"
    base = re.sub(r"\(.*?\)", "", display_name).strip()
    for part in base.split("/"):
        part = part.strip()
        if part and part.lower() not in [a.lower() for a in als]:
            als.append(part)
    return als

def main():
    products = []
    with open(PRODUCTS, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            q, disp, target, maker, cat, note = (line.split("|") + [""] * 6)[:6]
            products.append({"query": q, "display": disp, "target": target})

    results = {}
    for i, p in enumerate(products, 1):
        als = aliases(p["query"], p["display"])
        alias_clause = " OR ".join(f'"{a}"[Title/Abstract]' for a in als)
        strict = (f'({alias_clause}) AND (clinical trial[Publication Type] OR '
                  f'phase[Title/Abstract] OR patients[Title/Abstract])')
        ids = esearch(strict)
        relaxed = False
        if not ids:
            ids = esearch(f'({alias_clause})')
            relaxed = True
        print(f"[{i}/{len(products)}] {p['display']}: {len(ids)} hits"
              f"{' (relaxed)' if relaxed and ids else ''}", flush=True)
        entry = {"ids": ids, "relaxed": relaxed, "abstracts": {}}
        for pmid in ids[:2]:  # most recent 1-2
            abst = efetch(pmid)
            if abst:
                entry["abstracts"][pmid] = abst
                with open(os.path.join(OUTDIR, f"{pmid}.txt"), "w",
                          encoding="utf-8") as f:
                    f.write(abst)
        results[p["display"]] = entry

    with open(SUMMARY, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    nohit = [d for d, e in results.items() if not e["ids"]]
    print(f"\nDone. {len(results)} products, {len(nohit)} with no hits: {nohit}")

if __name__ == "__main__":
    main()

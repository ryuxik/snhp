"""
CFPB Consumer Complaint Database — dispute corpus fetcher.

Pulls real consumer refund/billing disputes from the CFPB Consumer
Complaint Database, a U.S. government public-domain dataset. Each record
is a genuine consumer complaint: a free-text narrative plus structured
fields (product, issue, company, and how the company resolved it).

The corpus has two uses, both on the INPUT side of SNHP:
  - grounding the synthetic scenario generator in realistic language and
    dollar figures (see snhp/cs_negotiation_dataset.py);
  - seeding the free-text -> structured extraction step (roadmap Phase 2).

It does NOT feed the negotiation engine (pure game-theory math — it does
not train on data), and it is NOT Phase-1 validation data: these are
historical, already-resolved complaints, not live disputes to negotiate.

Source:  https://www.consumerfinance.gov/data-research/consumer-complaints/
Licence: U.S. federal government work — public domain. The CFPB scrubs PII
         before publication; consumers opt in to narrative publication.

No API key required.
Run:  python3 snhp/fetch_cfpb_disputes.py --n 300
"""
from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone

import requests

_API = "https://www.consumerfinance.gov/data-research/consumer-complaints/search/api/v1/"
_PAGE = 100          # CFPB search API page-size cap
_TIMEOUT = 30
_USER_AGENT = "snhp-dispute-research/1.0 (prototype; contact via github.com/ryuxik/snhp)"


def _fetch_page(search_term: str, frm: int, size: int) -> list[dict]:
    params = {
        "search_term": search_term,
        "has_narrative": "true",
        "size": size,
        "frm": frm,
        "sort": "created_date_desc",
        "no_aggs": "true",
    }
    resp = requests.get(_API, params=params,
                        headers={"User-Agent": _USER_AGENT}, timeout=_TIMEOUT)
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("hits", {}).get("hits", [])


def _normalise(hit: dict) -> dict:
    s = hit.get("_source", {})
    return {
        "id": s.get("complaint_id"),
        "date_received": s.get("date_received"),
        "product": s.get("product"),
        "sub_product": s.get("sub_product"),
        "issue": s.get("issue"),
        "sub_issue": s.get("sub_issue"),
        "company": s.get("company"),
        "state": s.get("state"),
        "narrative": s.get("complaint_what_happened"),
        "company_response": s.get("company_response"),
        "company_public_response": s.get("company_public_response"),
        "consumer_disputed": s.get("consumer_disputed"),
        "timely": s.get("timely"),
    }


def fetch(search_term: str, n: int) -> list[dict]:
    out: list[dict] = []
    frm = 0
    while len(out) < n:
        size = min(_PAGE, n - len(out))
        try:
            hits = _fetch_page(search_term, frm, size)
        except Exception as e:                       # noqa: BLE001
            print(f"  page at frm={frm} failed ({e}); retrying once...")
            time.sleep(2)
            try:
                hits = _fetch_page(search_term, frm, size)
            except Exception as e2:                  # noqa: BLE001
                print(f"  retry failed ({e2}); stopping with {len(out)} records.")
                break
        if not hits:
            break
        out.extend(_normalise(h) for h in hits)
        frm += len(hits)
        print(f"  fetched {len(out)}/{n} ...")
        time.sleep(0.4)
    return out[:n]


def main() -> None:
    p = argparse.ArgumentParser(description="Fetch a CFPB dispute corpus")
    p.add_argument("--n", type=int, default=300)
    p.add_argument("--search-term", default="refund")
    p.add_argument("--out", default=os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "cfpb_disputes.json"))
    args = p.parse_args()

    print(f"Fetching {args.n} CFPB complaints (search_term={args.search_term!r})...")
    complaints = fetch(args.search_term, args.n)
    if not complaints:
        print("No complaints fetched — check connectivity / the API.")
        return

    by_resolution: dict[str, int] = {}
    by_product: dict[str, int] = {}
    for c in complaints:
        r = c.get("company_response") or "(none)"
        pr = c.get("product") or "(none)"
        by_resolution[r] = by_resolution.get(r, 0) + 1
        by_product[pr] = by_product.get(pr, 0) + 1

    dataset = {
        "source": "CFPB Consumer Complaint Database",
        "source_url": "https://www.consumerfinance.gov/data-research/consumer-complaints/",
        "licence": "U.S. federal government work — public domain",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "query": {"search_term": args.search_term, "has_narrative": True},
        "n": len(complaints),
        "by_resolution": by_resolution,
        "by_product": by_product,
        "complaints": complaints,
    }
    with open(args.out, "w") as f:
        json.dump(dataset, f, indent=2)

    print(f"\n=== {len(complaints)} complaints ===")
    print("By resolution:")
    for k, v in sorted(by_resolution.items(), key=lambda x: -x[1]):
        print(f"  {v:>4}  {k}")
    print("Top products:")
    for k, v in sorted(by_product.items(), key=lambda x: -x[1])[:6]:
        print(f"  {v:>4}  {k}")
    print(f"\nSaved -> {args.out}")


if __name__ == "__main__":
    main()

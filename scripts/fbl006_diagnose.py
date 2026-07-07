"""
A0 diagnostic (FBL-006 negative gating) — READ-ONLY.

Server must be running with the reranker on:
    RERANKER_ENABLED=true RERANKER_CANDIDATES=10 \
        uv run uvicorn dev_rag.api:app --host 127.0.0.1 --port 8000

Queries the 3 out-of-scope negatives + a spread of positives, records the
top-1 relevance_score (= cross-encoder logit in reranker mode) and whether
the expected_source is retrieved. Question: is there a logit threshold T
that puts all 3 negatives below and the positives above, and at what cost
in wrongly-rejected positives?

Run: uv run python scripts/fbl006_diagnose.py
"""
import sys
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))
from loader import load_questions  # noqa: E402

BASE = "http://localhost:8000"

# 3 negatives + 10 positives spread across all 4 books (5 DDD / 4 Compose / 1 RLA).
NEGATIVES = ["devops-007", "devops-018", "devops-027", "devops-035", "devops-036"]
POSITIVES = [
    "devops-002", "devops-009", "devops-010", "devops-015", "devops-021",  # DDD
    "devops-001", "devops-024", "devops-025", "devops-030",                # Compose
    "devops-034",                                                          # RLA
]
IDS = NEGATIVES + POSITIVES


def main():
    qs = {q.id: q for q in load_questions()}
    rows = []
    with httpx.Client(timeout=180) as client:
        for qid in IDS:
            q = qs[qid]
            r = client.post(f"{BASE}/search", json={
                "query": q.question, "domain": "devops", "n_results": 5,
            })
            r.raise_for_status()
            results = r.json()["results"]
            top = results[0] if results else {}
            top_logit = top.get("relevance_score")
            top_source = top.get("source", "")
            sources3 = [x.get("source", "") for x in results[:3]]
            expected = q.expected_source
            hit3 = (expected in sources3) if (expected and not q.no_answer) else None
            rows.append({
                "id": qid, "kind": "NEG" if q.no_answer else "pos",
                "logit": top_logit, "top_source": top_source,
                "expected": expected, "hit@3": hit3,
                "question": q.question,
            })
            print(f"  {qid:14s} {rows[-1]['kind']:3s} logit={top_logit:+.3f} "
                  f"top={top_source[:38]:38s} hit@3={hit3}")

    print("\n" + "=" * 78)
    negs = [r for r in rows if r["kind"] == "NEG"]
    pos = [r for r in rows if r["kind"] == "pos"]
    max_neg = max(r["logit"] for r in negs)
    min_pos = min(r["logit"] for r in pos)
    print(f"Negatives (n={len(negs)}): logits "
          f"{sorted(round(r['logit'],3) for r in negs)}  max={max_neg:+.3f}")
    print(f"Positives (n={len(pos)}): logits "
          f"{sorted(round(r['logit'],3) for r in pos)}  min={min_pos:+.3f}")
    print(f"\nSeparation: max(neg)={max_neg:+.3f}  vs  min(pos)={min_pos:+.3f}")
    if max_neg < min_pos:
        print(f"  CLEAN: a threshold in ({max_neg:+.3f}, {min_pos:+.3f}) "
              f"separates all negatives below, all positives above.")
    else:
        print(f"  OVERLAP: no threshold separates them. Positives below "
              f"max(neg): "
              f"{[r['id'] for r in pos if r['logit'] <= max_neg]}")
        # cost curve: how many positives must be sacrificed to reject all 3 negs?
        T = max_neg + 1e-6
        rejected_pos = [r['id'] for r in pos if r['logit'] < T]
        print(f"  To reject all 3 negatives (T>{max_neg:+.3f}), you also reject "
              f"{len(rejected_pos)}/{len(pos)} positives: {rejected_pos}")
    print("=" * 78)


if __name__ == "__main__":
    main()

"""FAQ match over question text only.

BM25 on a 2-row corpus gives IDF=0 for terms that appear once (N=2, n=1).
We therefore require token overlap on the question and use BM25 only as a
tie-break among overlapping candidates.
"""
from __future__ import annotations

import logging
import re
from typing import Optional

from gateway.config import settings

log = logging.getLogger(__name__)

_TOKEN = re.compile(r"[a-z0-9]+")
_STOP = {
    "the", "a", "an", "is", "are", "of", "to", "for", "and", "or", "in",
    "on", "what", "who", "how", "do", "does", "me", "please",
}


def tokenize(text: str) -> list[str]:
    return [t for t in _TOKEN.findall(text.lower()) if t not in _STOP]


def rank_faq(
    query: str,
    entries: list[dict],
    min_score: float | None = None,
) -> Optional[dict]:
    """entries: [{id, question, answer}, ...]. Ranks on question tokens only."""
    if not entries:
        return None
    threshold = settings.FAQ_MIN_SCORE if min_score is None else min_score
    q_tokens = tokenize(query)
    if not q_tokens:
        return None
    q_set = set(q_tokens)
    corpus = [tokenize(e["question"]) for e in entries]

    raw_scores = [0.0] * len(entries)
    try:
        from rank_bm25 import BM25Okapi
        if any(corpus):
            raw_scores = [float(x) for x in BM25Okapi(corpus).get_scores(q_tokens)]
    except Exception as exc:
        log.warning("bm25 unavailable, overlap only: %s", exc)

    ranked = []
    for i, row in enumerate(entries):
        overlap = q_set & set(corpus[i])
        if not overlap:
            continue
        frac = len(overlap) / len(q_set)
        score = raw_scores[i] + 5.0 * frac
        ranked.append((score, frac, row))
    if not ranked:
        return None
    ranked.sort(key=lambda x: x[0], reverse=True)
    score, frac, row = ranked[0]
    # Overlap is mandatory. A tiny shared token ("collections") must not
    # beat a dunning-email with the SLA FAQ via the BM25 additive bonus.
    min_frac = max(0.5, threshold if threshold <= 1 else 0.5)
    if frac < min_frac:
        return None
    return {
        "response": row["answer"],
        "score": score,
        "faq_id": row["id"],
        "question": row["question"],
    }


async def attempt(query: str, pool) -> Optional[dict]:
    if pool is None:
        return None
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT id, question, answer FROM faq_entries"
            )
            if not rows:
                log.info("ras.faq: no FAQ entries yet — miss")
                return None
            entries = [{"id": r["id"], "question": r["question"], "answer": r["answer"]} for r in rows]
            hit = rank_faq(query, entries)
            if not hit:
                log.info("ras.faq MISS query=%r", query[:60])
                return None
            await conn.execute(
                "UPDATE faq_entries SET hit_count = hit_count + 1, updated_at = now() WHERE id = $1",
                hit["faq_id"],
            )
            log.info("ras.faq HIT faq_id=%s score=%.3f", hit["faq_id"], hit["score"])
            return hit
    except Exception as exc:
        log.warning("ras.faq error: %s", exc)
        return None

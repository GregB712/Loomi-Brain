from __future__ import annotations

import math
import re
from collections import Counter
from collections.abc import Iterable, Sequence

TOKEN_RE = re.compile(r"[a-zA-Z0-9][a-zA-Z0-9_-]*")
STOP_WORDS = {
    "a",
    "an",
    "and",
    "are",
    "as",
    "does",
    "for",
    "from",
    "how",
    "is",
    "it",
    "of",
    "or",
    "should",
    "that",
    "the",
    "to",
    "what",
    "when",
    "where",
    "who",
    "why",
    "with",
}


def tokenize(value: str) -> list[str]:
    return [
        token
        for match in TOKEN_RE.finditer(value)
        if (token := match.group(0).casefold()) not in STOP_WORDS
    ]


def lexical_score(query: str, text: str, *, title: str = "") -> tuple[float, dict[str, object]]:
    query_terms = tokenize(query)
    if not query_terms:
        return 0.0, {"term_overlap": 0.0, "matched_terms": []}

    text_terms = tokenize(text)
    title_terms = tokenize(title)
    text_counts = Counter(text_terms)
    unique_query_terms = set(query_terms)
    matched_terms = sorted(term for term in unique_query_terms if text_counts[term] > 0)
    title_matches = sum(1 for term in unique_query_terms if term in title_terms)
    hit_count = sum(min(text_counts[term], 3) for term in unique_query_terms)
    coverage = len(matched_terms) / len(unique_query_terms)
    density = min(hit_count / max(len(unique_query_terms) * 3, 1), 1.0)
    phrase_boost = 0.18 if query.casefold() in text.casefold() else 0.0
    title_boost = min(title_matches / max(len(unique_query_terms), 1), 1.0) * 0.08
    score = min((coverage * 0.68) + (density * 0.24) + phrase_boost + title_boost, 1.0)
    return score, {
        "term_overlap": round(coverage, 4),
        "matched_terms": matched_terms,
        "hit_count": hit_count,
        "phrase_match": phrase_boost > 0,
        "title_matches": title_matches,
    }


def cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def normalized_cosine_score(left: Sequence[float], right: Sequence[float]) -> float:
    return max(0.0, min((cosine_similarity(left, right) + 1.0) / 2.0, 1.0))


def reciprocal_rank_fusion(
    rankings: Iterable[tuple[float, Sequence[str]]],
    *,
    k: int = 60,
) -> dict[str, float]:
    fused: dict[str, float] = {}
    for weight, chunk_ids in rankings:
        for index, chunk_id in enumerate(chunk_ids, start=1):
            fused[chunk_id] = fused.get(chunk_id, 0.0) + (weight / (k + index))
    if not fused:
        return {}
    max_score = max(fused.values())
    if max_score <= 0:
        return fused
    return {chunk_id: score / max_score for chunk_id, score in fused.items()}


def token_jaccard(left: str, right: str) -> float:
    left_tokens = set(tokenize(left))
    right_tokens = set(tokenize(right))
    if not left_tokens or not right_tokens:
        return 0.0
    return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

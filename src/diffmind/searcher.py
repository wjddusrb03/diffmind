"""Semantic search over learned diff history."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional

import numpy as np

from .models import DiffHunk, DiffMindIndex


@dataclass
class SearchResult:
    """A single search result."""
    hunk: DiffHunk
    score: float


def search(
    query: str,
    index: DiffMindIndex,
    k: int = 5,
    model=None,
    file_path: Optional[str] = None,
    author: Optional[str] = None,
    language: Optional[str] = None,
    bugfix_only: bool = False,
    after: Optional[datetime] = None,
    before: Optional[datetime] = None,
) -> List[SearchResult]:
    """Semantic search over past diff history.

    Args:
        query: Natural language query (e.g. "null check missing").
        index: The learned DiffMindIndex.
        k: Number of results to return.
        model: Pre-loaded SentenceTransformer model.
        file_path: Filter by file path (partial match).
        author: Filter by author (case-insensitive partial match).
        language: Filter by programming language.
        bugfix_only: Only return bugfix commits.
        after: Only return results after this date.
        before: Only return results before this date.

    Returns:
        List of SearchResult sorted by similarity.
    """
    if not index.hunks:
        return []

    # Load model if needed
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(index.model_name)

    # Encode query
    query_vec = model.encode([query])

    # Asymmetric scoring
    scores = index.quantizer.cosine_scores(query_vec, index.compressed)
    score_array = np.array(scores, dtype=np.float64).flatten()

    # Apply filters
    for i, hunk in enumerate(index.hunks):
        if file_path and file_path.lower() not in hunk.file_path.lower():
            score_array[i] = -np.inf
        if author and author.lower() not in hunk.author.lower():
            score_array[i] = -np.inf
        if language and language.lower() != hunk.language.lower():
            score_array[i] = -np.inf
        if bugfix_only and not hunk.is_bugfix:
            score_array[i] = -np.inf
        if after and hunk.timestamp.replace(tzinfo=None) < after:
            score_array[i] = -np.inf
        if before and hunk.timestamp.replace(tzinfo=None) > before:
            score_array[i] = -np.inf

    # Get top-k
    top_indices = np.argsort(score_array)[::-1][:k]
    results = []
    for i in top_indices:
        score = float(score_array[i])
        if score == -np.inf:
            break
        results.append(SearchResult(hunk=index.hunks[i], score=score))

    return results

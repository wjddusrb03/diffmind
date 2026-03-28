"""Review engine - compares current diff against past bug patterns."""

from __future__ import annotations

from typing import List, Optional

import numpy as np

from .models import DiffHunk, DiffMindIndex, ReviewWarning
from .parser import parse_current_diff


def classify_risk(score: float, past_hunk: DiffHunk) -> str:
    """Classify risk level based on similarity and whether past was bugfix."""
    if score >= 0.90 and past_hunk.is_bugfix:
        return "HIGH"
    elif score >= 0.80 and past_hunk.is_bugfix:
        return "MEDIUM"
    elif score >= 0.80:
        return "LOW"
    elif score >= 0.70 and past_hunk.is_bugfix:
        return "LOW"
    return "LOW"


def generate_reason(current: DiffHunk, past: DiffHunk, score: float) -> str:
    """Generate a human-readable warning reason."""
    if past.is_bugfix:
        msg = (
            f"This change is {score:.0%} similar to a bug fixed on "
            f"{past.time_str()} by {past.author}.\n"
            f"Commit: {past.short_hash()} - {past.commit_message}\n"
            f"File: {past.file_path}"
        )
        if past.pr_number:
            msg += f"\nPR: #{past.pr_number}"
        return msg
    else:
        return (
            f"Similar change was made on {past.time_str()} by {past.author}.\n"
            f"Commit: {past.short_hash()} - {past.commit_message}\n"
            f"File: {past.file_path}"
        )


def review(
    index: DiffMindIndex,
    repo_path: str = ".",
    staged: bool = False,
    threshold: float = 0.75,
    model=None,
    top_k: int = 3,
    hunks: Optional[List[DiffHunk]] = None,
) -> List[ReviewWarning]:
    """Review current diff against learned bug patterns.

    Args:
        index: The learned DiffMindIndex.
        repo_path: Path to git repository.
        staged: If True, only review staged changes.
        threshold: Minimum similarity to report.
        model: Pre-loaded SentenceTransformer model.
        top_k: Max warnings per hunk.
        hunks: Pre-parsed hunks (overrides repo_path parsing).

    Returns:
        List of ReviewWarning sorted by similarity (highest first).
    """
    # 1. Get current diff hunks
    if hunks is None:
        current_hunks = parse_current_diff(repo_path, staged=staged)
    else:
        current_hunks = hunks

    if not current_hunks:
        return []

    # 2. Load model if needed
    if model is None:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(index.model_name)

    # 3. Compare each hunk against the index
    warnings: List[ReviewWarning] = []

    for hunk in current_hunks:
        query_text = hunk.to_embedding_text()
        query_vec = model.encode([query_text])

        # Asymmetric scoring via TurboQuant (no decompression)
        scores = index.quantizer.cosine_scores(query_vec, index.compressed)
        score_array = np.array(scores).flatten()

        # Get top-k above threshold
        top_indices = np.argsort(score_array)[::-1]

        count = 0
        for i in top_indices:
            if count >= top_k:
                break

            score = float(score_array[i])
            if score < threshold:
                break

            past_hunk = index.hunks[i]

            # Skip self-match (same commit)
            if past_hunk.commit_hash == hunk.commit_hash:
                continue

            # Skip if same file + same content (exact duplicate)
            if (past_hunk.file_path == hunk.file_path
                    and past_hunk.new_code == hunk.new_code
                    and past_hunk.old_code == hunk.old_code):
                continue

            risk = classify_risk(score, past_hunk)
            reason = generate_reason(hunk, past_hunk, score)

            warnings.append(ReviewWarning(
                current_hunk=hunk,
                similar_hunk=past_hunk,
                similarity=score,
                risk_level=risk,
                reason=reason,
            ))
            count += 1

    # Sort by similarity descending
    warnings.sort(key=lambda w: w.similarity, reverse=True)
    return warnings

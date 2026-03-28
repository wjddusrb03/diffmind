"""Display formatting for DiffMind output."""

from __future__ import annotations

import json
from typing import List

from .models import DiffMindIndex, ReviewWarning
from .searcher import SearchResult


def _separator(char: str = "-", width: int = 60) -> str:
    return char * width


def display_review_report(warnings: List[ReviewWarning],
                          total_hunks: int, as_json: bool = False) -> str:
    """Format review results for terminal output."""
    if as_json:
        return _review_as_json(warnings, total_hunks)

    lines = []
    lines.append(_separator("="))
    lines.append("  DiffMind Review Report")
    lines.append(f"  Analyzed: {total_hunks} hunks")
    lines.append(f"  Warnings: {len(warnings)} found")
    lines.append(_separator("="))
    lines.append("")

    if not warnings:
        lines.append("[OK] No similar bug patterns found.")
        return "\n".join(lines)

    for w in warnings:
        risk_mark = {"HIGH": "[!!!]", "MEDIUM": "[!!]", "LOW": "[!]"}.get(
            w.risk_level, "[!]"
        )
        lines.append(f"{risk_mark} {w.risk_level} RISK ({w.similarity:.0%} similar)")
        lines.append(f"  Current: {w.current_hunk.file_path}")

        # Show current code change
        if w.current_hunk.old_code.strip():
            for ol in w.current_hunk.old_code.split("\n")[:5]:
                lines.append(f"    - {ol}")
        if w.current_hunk.new_code.strip():
            for nl in w.current_hunk.new_code.split("\n")[:5]:
                lines.append(f"    + {nl}")

        lines.append("")
        lines.append(f"  Past: {w.similar_hunk.file_path}")
        lines.append(f"  {w.reason}")
        lines.append("")
        lines.append(_separator("-"))
        lines.append("")

    # Summary
    warned_ids = set(id(w.current_hunk) for w in warnings)
    passed = total_hunks - len(warned_ids)
    if passed > 0:
        lines.append(f"[OK] {passed} hunks passed - no similar bug patterns found")

    return "\n".join(lines)


def _review_as_json(warnings: List[ReviewWarning], total_hunks: int) -> str:
    data = {
        "total_hunks": total_hunks,
        "warning_count": len(warnings),
        "warnings": [
            {
                "risk_level": w.risk_level,
                "similarity": round(w.similarity, 3),
                "current_file": w.current_hunk.file_path,
                "past_file": w.similar_hunk.file_path,
                "past_commit": w.similar_hunk.short_hash(),
                "past_message": w.similar_hunk.commit_message,
                "past_date": w.similar_hunk.time_str(),
                "past_author": w.similar_hunk.author,
                "is_bugfix": w.similar_hunk.is_bugfix,
                "reason": w.reason,
            }
            for w in warnings
        ],
    }
    return json.dumps(data, indent=2, ensure_ascii=False)


def display_search_results(results: List[SearchResult]) -> str:
    """Format search results."""
    if not results:
        return "No results found."

    lines = []
    for i, r in enumerate(results, 1):
        h = r.hunk
        bugfix_mark = " [BUGFIX]" if h.is_bugfix else ""
        lines.append(f"{i}. [{r.score:.2f}] {h.file_path}{bugfix_mark}")
        lines.append(f"   Commit: {h.short_hash()} ({h.time_str()}) by {h.author}")
        lines.append(f"   Message: {h.commit_message}")
        if h.old_code.strip():
            first_old = h.old_code.split("\n")[0][:80]
            lines.append(f"   - {first_old}")
        if h.new_code.strip():
            first_new = h.new_code.split("\n")[0][:80]
            lines.append(f"   + {first_new}")
        lines.append("")

    return "\n".join(lines)


def display_stats(index: DiffMindIndex) -> str:
    """Format index statistics."""
    lines = []
    lines.append(_separator("="))
    lines.append("  DiffMind Index Statistics")
    lines.append(_separator("="))
    lines.append("")
    lines.append(f"  Total commits analyzed: {index.total_commits}")
    lines.append(f"  Bugfix commits: {index.bugfix_commits}")
    lines.append(f"  Total diff hunks: {len(index.hunks)}")
    lines.append(f"  Files tracked: {index.files_tracked}")
    lines.append(f"  Languages: {', '.join(index.languages) if index.languages else 'N/A'}")
    lines.append(f"  Model: {index.model_name}")
    lines.append(f"  Embedding dim: {index.embedding_dim}")
    lines.append(f"  Memory: {index.raw_memory_bytes:,} -> {index.compressed_memory_bytes:,} bytes")

    if index.raw_memory_bytes > 0:
        ratio = index.compressed_memory_bytes / index.raw_memory_bytes
        lines.append(f"  Compression: {ratio:.0%}")

    lines.append(f"  Learn time: {index.learn_time:.1f}s")
    lines.append("")

    # Top bugfix files
    bugfix_hunks = [h for h in index.hunks if h.is_bugfix]
    if bugfix_hunks:
        file_counts = {}
        for h in bugfix_hunks:
            file_counts[h.file_path] = file_counts.get(h.file_path, 0) + 1

        sorted_files = sorted(file_counts.items(), key=lambda x: x[1], reverse=True)
        lines.append("  Top bugfix files:")
        for fp, count in sorted_files[:10]:
            lines.append(f"    {count:3d} bugs  {fp}")
        lines.append("")

    # Top authors
    author_counts = {}
    for h in index.hunks:
        author_counts[h.author] = author_counts.get(h.author, 0) + 1

    sorted_authors = sorted(author_counts.items(), key=lambda x: x[1], reverse=True)
    lines.append("  Top contributors:")
    for author, count in sorted_authors[:10]:
        lines.append(f"    {count:3d} hunks  {author}")

    return "\n".join(lines)

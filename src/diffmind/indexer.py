"""Index builder for DiffMind - learns from git history."""

from __future__ import annotations

import sys
import time
from typing import Optional

import numpy as np

from .models import DiffMindIndex
from .parser import get_head_commit, parse_git_log

DEFAULT_MODEL = "all-MiniLM-L6-v2"


def learn(
    repo_path: str = ".",
    model_name: str = DEFAULT_MODEL,
    bits: int = 3,
    since: Optional[str] = None,
    until: Optional[str] = None,
    branch: str = "HEAD",
    bugfix_only: bool = False,
    since_commit: Optional[str] = None,
) -> DiffMindIndex:
    """Learn from git history and build a compressed index.

    Args:
        repo_path: Path to git repository.
        model_name: Sentence-transformer model name.
        bits: TurboQuant compression bits (2, 3, or 4).
        since: Only learn from commits after this date (e.g. "2024-01-01").
        until: Only learn from commits before this date.
        branch: Git branch to analyze.
        bugfix_only: If True, only index bugfix commits.
        since_commit: Only learn from commits after this hash.

    Returns:
        DiffMindIndex with compressed embeddings.
    """
    t0 = time.time()

    # 1. Parse git log
    print("Parsing git history...")
    hunks, total_commits, bugfix_commits = parse_git_log(
        repo_path, since=since, until=until, branch=branch,
        since_commit=since_commit,
    )

    if not hunks:
        raise RuntimeError(
            "No diff hunks found. Make sure this is a git repository "
            "with commit history."
        )

    # Filter bugfix-only
    if bugfix_only:
        hunks = [h for h in hunks if h.is_bugfix]
        if not hunks:
            raise RuntimeError(
                "No bugfix commits found. Try without --bugfix-only."
            )

    print(f"  Found {total_commits} commits ({bugfix_commits} bugfixes)")
    print(f"  Extracted {len(hunks)} diff hunks")

    # 2. Load embedding model
    print(f"Loading embedding model ({model_name})...")
    try:
        from sentence_transformers import SentenceTransformer
        model = SentenceTransformer(model_name)
    except Exception as e:
        raise RuntimeError(
            f"Failed to load model '{model_name}': {e}\n"
            f"Try: pip install sentence-transformers"
        )

    # 3. Generate embeddings
    texts = [h.to_embedding_text() for h in hunks]
    print(f"Computing embeddings for {len(texts)} hunks...")
    embeddings = model.encode(texts, show_progress_bar=True)
    embedding_dim = embeddings.shape[1]
    raw_bytes = embeddings.nbytes

    # 4. Compress with TurboQuant
    print("Compressing with TurboQuant...")
    try:
        from langchain_turboquant import TurboQuantizer
    except ImportError:
        raise RuntimeError(
            "langchain-turboquant not found. "
            "Try: pip install langchain-turboquant"
        )

    quantizer = TurboQuantizer(bits=bits)
    compressed = quantizer.fit_transform(embeddings)
    compressed_bytes = sys.getsizeof(compressed)

    # 5. Gather metadata
    all_files = set(h.file_path for h in hunks)
    all_langs = sorted(set(h.language for h in hunks if h.language != "unknown"))
    head_hash = ""
    try:
        head_hash = get_head_commit(repo_path)
    except Exception:
        pass

    elapsed = time.time() - t0
    print(f"Learned in {elapsed:.1f}s")
    print(f"  Memory: {raw_bytes:,} bytes -> {compressed_bytes:,} bytes "
          f"({compressed_bytes / max(raw_bytes, 1):.0%})")

    return DiffMindIndex(
        hunks=hunks,
        compressed=compressed,
        quantizer=quantizer,
        model_name=model_name,
        embedding_dim=embedding_dim,
        total_commits=total_commits,
        bugfix_commits=bugfix_commits,
        files_tracked=len(all_files),
        languages=all_langs,
        raw_memory_bytes=raw_bytes,
        compressed_memory_bytes=compressed_bytes,
        learn_time=elapsed,
        last_learned_commit=head_hash,
    )


def incremental_learn(
    index: DiffMindIndex,
    repo_path: str = ".",
    model_name: Optional[str] = None,
) -> DiffMindIndex:
    """Learn only new commits since last index build.

    Args:
        index: Existing DiffMindIndex.
        repo_path: Path to git repository.
        model_name: Override model (default: use same as index).

    Returns:
        Updated DiffMindIndex.
    """
    if not index.last_learned_commit:
        raise RuntimeError(
            "No last_learned_commit in index. Run full 'learn' first."
        )

    model_name = model_name or index.model_name

    # 1. Parse only new commits
    print(f"Checking for new commits since {index.last_learned_commit[:7]}...")
    new_hunks, new_total, new_bugfix = parse_git_log(
        repo_path, since_commit=index.last_learned_commit
    )

    if not new_hunks:
        print("No new commits since last learn.")
        return index

    print(f"  Found {new_total} new commits ({new_bugfix} bugfixes)")
    print(f"  Extracted {len(new_hunks)} new diff hunks")

    # 2. Embed new hunks
    from sentence_transformers import SentenceTransformer
    model = SentenceTransformer(model_name)
    new_texts = [h.to_embedding_text() for h in new_hunks]
    new_embeddings = model.encode(new_texts, show_progress_bar=True)

    # 3. Reconstruct old embeddings and combine
    old_embeddings = index.quantizer.inverse_transform(index.compressed)
    all_embeddings = np.vstack([old_embeddings, new_embeddings])

    # 4. Re-compress
    from langchain_turboquant import TurboQuantizer
    bits = getattr(index.quantizer, "bits", 3)
    quantizer = TurboQuantizer(bits=bits)
    compressed = quantizer.fit_transform(all_embeddings)

    # 5. Update index
    all_hunks = index.hunks + new_hunks
    all_files = set(h.file_path for h in all_hunks)
    all_langs = sorted(set(h.language for h in all_hunks if h.language != "unknown"))
    head_hash = get_head_commit(repo_path)

    index.hunks = all_hunks
    index.compressed = compressed
    index.quantizer = quantizer
    index.total_commits += new_total
    index.bugfix_commits += new_bugfix
    index.files_tracked = len(all_files)
    index.languages = all_langs
    index.raw_memory_bytes = all_embeddings.nbytes
    index.compressed_memory_bytes = sys.getsizeof(compressed)
    index.last_learned_commit = head_hash

    print(f"  Index updated: {len(all_hunks)} total hunks")
    return index

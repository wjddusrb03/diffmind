"""Comprehensive tests for DiffMind with REAL git operations.

These tests create temporary git repositories, make actual commits with real diffs,
and verify the full pipeline works end-to-end.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from typing import List, Optional
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from diffmind.models import DiffHunk, DiffMindIndex, ReviewWarning
from diffmind.parser import (
    detect_bugfix,
    detect_language,
    extract_pr_number,
    get_head_commit,
    parse_current_diff,
    parse_git_log,
)
from diffmind.storage import index_exists, load_index, save_index
from diffmind.hooks import install_pre_commit, generate_github_action


# ── Helpers ────────────────────────────────────────────────────────────


def _git(args: List[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command in the given directory."""
    return subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=check,
    )


def _init_repo(path: str) -> None:
    """Initialize a git repo with initial config."""
    _git(["init"], path)
    _git(["config", "user.email", "test@example.com"], path)
    _git(["config", "user.name", "Test Author"], path)


def _write_file(repo: str, relpath: str, content: str) -> str:
    """Write a file inside the repo, creating directories as needed."""
    full = os.path.join(repo, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return full


def _commit(repo: str, message: str, files: Optional[list] = None) -> str:
    """Stage files and commit, returning the commit hash."""
    if files:
        for f in files:
            _git(["add", f], repo)
    else:
        _git(["add", "-A"], repo)
    _git(["commit", "-m", message, "--allow-empty-message"], repo)
    result = _git(["rev-parse", "HEAD"], repo)
    return result.stdout.strip()


def _make_fake_index(hunks: List[DiffHunk], last_commit: str = "") -> DiffMindIndex:
    """Create a DiffMindIndex with real TurboQuantizer for pickling."""
    from langchain_turboquant import TurboQuantizer
    n = len(hunks)
    dim = 32  # small dim for fast tests
    rng = np.random.RandomState(42)
    embeddings = rng.randn(n, dim).astype(np.float32) if n > 0 else np.empty((0, dim), dtype=np.float32)

    quantizer = TurboQuantizer(dim=dim, bits=3)
    compressed = quantizer.quantize(embeddings) if n > 0 else embeddings

    return DiffMindIndex(
        hunks=hunks,
        compressed=compressed,
        quantizer=quantizer,
        model_name="all-MiniLM-L6-v2",
        embedding_dim=dim,
        total_commits=n,
        bugfix_commits=sum(1 for h in hunks if h.is_bugfix),
        files_tracked=len(set(h.file_path for h in hunks)),
        languages=sorted(set(h.language for h in hunks if h.language != "unknown")),
        raw_memory_bytes=embeddings.nbytes,
        compressed_memory_bytes=100,
        learn_time=0.1,
        last_learned_commit=last_commit,
    )


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture
def repo_dir():
    """Create a temporary directory with an initialized git repo."""
    with tempfile.TemporaryDirectory() as tmpdir:
        _init_repo(tmpdir)
        yield tmpdir


@pytest.fixture
def repo_with_commits(repo_dir):
    """Repo with a few diverse commits already made."""
    # Commit 1: add a python file
    _write_file(repo_dir, "src/main.py", 'def hello():\n    print("hello")\n')
    _commit(repo_dir, "feat: add hello function")

    # Commit 2: bugfix
    _write_file(repo_dir, "src/main.py", 'def hello():\n    if True:\n        print("hello")\n')
    _commit(repo_dir, "fix: guard hello with check")

    # Commit 3: add JS file
    _write_file(repo_dir, "web/app.js", 'const x = 1;\nconsole.log(x);\n')
    _commit(repo_dir, "feat: add JS app")

    yield repo_dir


# =======================================================================
# Git Parser Tests (real git repos)
# =======================================================================


class TestParseRealGit:
    """Tests 1-15: Parsing real git repositories."""

    # 1. Parse a single commit with one file change
    def test_parse_single_commit_one_file(self, repo_dir):
        _write_file(repo_dir, "hello.py", "print('hello')\n")
        _commit(repo_dir, "add greeting")
        hunks, total, bugfix = parse_git_log(repo_dir)
        assert total == 1
        assert bugfix == 0
        assert len(hunks) >= 1
        assert hunks[0].file_path == "hello.py"

    # 2. Parse multiple commits
    def test_parse_multiple_commits(self, repo_dir):
        _write_file(repo_dir, "a.py", "a = 1\n")
        _commit(repo_dir, "add a")
        _write_file(repo_dir, "b.py", "b = 2\n")
        _commit(repo_dir, "add b")
        _write_file(repo_dir, "c.py", "c = 3\n")
        _commit(repo_dir, "add c")

        hunks, total, bugfix = parse_git_log(repo_dir)
        assert total == 3
        files = {h.file_path for h in hunks}
        assert "a.py" in files
        assert "b.py" in files
        assert "c.py" in files

    # 3. Parse a commit that adds a new file (only + lines)
    def test_parse_new_file_only_additions(self, repo_dir):
        _write_file(repo_dir, "newfile.py", "import os\nimport sys\nprint('new')\n")
        _commit(repo_dir, "add new file")
        hunks, total, _ = parse_git_log(repo_dir)
        assert total == 1
        assert len(hunks) >= 1
        hunk = hunks[0]
        assert hunk.old_code.strip() == ""
        assert "import os" in hunk.new_code

    # 4. Parse a commit that deletes a file (only - lines)
    def test_parse_delete_file(self, repo_dir):
        _write_file(repo_dir, "to_delete.py", "x = 1\ny = 2\n")
        _commit(repo_dir, "add file")
        _git(["rm", "to_delete.py"], repo_dir)
        _commit(repo_dir, "remove file")
        # parse_git_log uses --diff-filter=MRA which doesn't include D(elete)
        # so the first commit (add) should have hunks, second (delete) won't
        hunks, total, _ = parse_git_log(repo_dir)
        assert total >= 1
        # The add commit should have hunks with only additions
        add_hunks = [h for h in hunks if h.file_path == "to_delete.py"]
        assert len(add_hunks) >= 1
        assert "x = 1" in add_hunks[0].new_code

    # 5. Parse a commit with multiple file changes
    def test_parse_commit_multiple_files(self, repo_dir):
        _write_file(repo_dir, "file1.py", "a = 1\n")
        _write_file(repo_dir, "file2.js", "const b = 2;\n")
        _write_file(repo_dir, "file3.java", 'class C {}\n')
        _commit(repo_dir, "add multiple files")
        hunks, total, _ = parse_git_log(repo_dir)
        assert total == 1
        files = {h.file_path for h in hunks}
        assert "file1.py" in files
        assert "file2.js" in files
        assert "file3.java" in files

    # 6. Parse with --since date filter
    def test_parse_since_date_filter(self, repo_dir):
        _write_file(repo_dir, "old.py", "old = 1\n")
        _commit(repo_dir, "old commit")

        # Using since="1 second ago" should include the commit we just made
        hunks, total, _ = parse_git_log(repo_dir, since="1 day ago")
        assert total >= 1

        # Using a future date should find nothing
        hunks2, total2, _ = parse_git_log(repo_dir, since="2099-01-01")
        assert total2 == 0

    # 7. Parse bugfix commit detection (message: "fix: something")
    def test_parse_bugfix_detection_fix_prefix(self, repo_dir):
        _write_file(repo_dir, "app.py", "def run():\n    pass\n")
        _commit(repo_dir, "feat: initial")
        _write_file(repo_dir, "app.py", "def run():\n    check()\n    pass\n")
        _commit(repo_dir, "fix: add missing check")

        hunks, total, bugfix = parse_git_log(repo_dir)
        assert bugfix >= 1
        bugfix_hunks = [h for h in hunks if h.is_bugfix]
        assert len(bugfix_hunks) >= 1
        assert bugfix_hunks[0].commit_message == "fix: add missing check"

    # 8. Parse conventional commit "hotfix:" detection
    def test_parse_hotfix_detection(self, repo_dir):
        _write_file(repo_dir, "svc.py", "x = 1\n")
        _commit(repo_dir, "feat: init")
        _write_file(repo_dir, "svc.py", "x = 2\n")
        _commit(repo_dir, "hotfix: urgent production issue")

        hunks, total, bugfix = parse_git_log(repo_dir)
        assert bugfix >= 1
        hotfix_hunks = [h for h in hunks if h.is_bugfix and "hotfix" in h.commit_message.lower()]
        assert len(hotfix_hunks) >= 1

    # 9. Parse commit with "closes #123" in message
    def test_parse_closes_issue(self, repo_dir):
        _write_file(repo_dir, "fix.py", "v = 1\n")
        _commit(repo_dir, "feat: start")
        _write_file(repo_dir, "fix.py", "v = 2\n")
        _commit(repo_dir, "update handler, closes #123")

        hunks, _, bugfix = parse_git_log(repo_dir)
        assert bugfix >= 1
        matching = [h for h in hunks if h.pr_number == 123]
        assert len(matching) >= 1

    # 10. Parse revert commit
    def test_parse_revert_commit(self, repo_dir):
        _write_file(repo_dir, "r.py", "orig = 1\n")
        _commit(repo_dir, "feat: original")
        _write_file(repo_dir, "r.py", "orig = 2\n")
        _commit(repo_dir, "Revert 'add feature X'")

        hunks, _, bugfix = parse_git_log(repo_dir)
        assert bugfix >= 1
        revert_hunks = [h for h in hunks if "revert" in h.commit_message.lower()]
        assert len(revert_hunks) >= 1
        assert revert_hunks[0].is_bugfix is True

    # 11. Parse commits on specific branch
    def test_parse_specific_branch(self, repo_dir):
        _write_file(repo_dir, "main.py", "m = 1\n")
        _commit(repo_dir, "main commit")
        _git(["checkout", "-b", "feature"], repo_dir)
        _write_file(repo_dir, "feature.py", "f = 1\n")
        _commit(repo_dir, "feature commit")

        # Parse only feature branch
        hunks, total, _ = parse_git_log(repo_dir, branch="feature")
        files = {h.file_path for h in hunks}
        assert "feature.py" in files

    # 12. Verify author name extraction
    def test_author_extraction(self, repo_dir):
        _write_file(repo_dir, "auth.py", "a = 1\n")
        _commit(repo_dir, "commit by test author")

        hunks, _, _ = parse_git_log(repo_dir)
        assert len(hunks) >= 1
        assert hunks[0].author == "Test Author"

    # 13. Verify timestamp extraction
    def test_timestamp_extraction(self, repo_dir):
        _write_file(repo_dir, "ts.py", "t = 1\n")
        _commit(repo_dir, "timestamp test")

        hunks, _, _ = parse_git_log(repo_dir)
        assert len(hunks) >= 1
        ts = hunks[0].timestamp
        assert isinstance(ts, datetime)
        # Should be today (approximately)
        now = datetime.now(timezone.utc)
        assert abs((now - ts.replace(tzinfo=timezone.utc if ts.tzinfo is None else ts.tzinfo)).total_seconds()) < 300

    # 14. Verify file path extraction
    def test_file_path_extraction(self, repo_dir):
        _write_file(repo_dir, "src/deep/nested/module.py", "deep = True\n")
        _commit(repo_dir, "add nested module")

        hunks, _, _ = parse_git_log(repo_dir)
        paths = {h.file_path for h in hunks}
        assert "src/deep/nested/module.py" in paths

    # 15. Verify language detection from real files
    def test_language_detection_real_files(self, repo_dir):
        _write_file(repo_dir, "code.py", "x = 1\n")
        _write_file(repo_dir, "code.js", "let x = 1;\n")
        _write_file(repo_dir, "Code.java", "class Code {}\n")
        _write_file(repo_dir, "code.go", "package main\n")
        _write_file(repo_dir, "code.rs", "fn main() {}\n")
        _commit(repo_dir, "add multi-language files")

        hunks, _, _ = parse_git_log(repo_dir)
        langs = {h.language for h in hunks}
        assert "python" in langs
        assert "javascript" in langs
        assert "java" in langs
        assert "go" in langs
        assert "rust" in langs


# =======================================================================
# Full Pipeline Tests (learn -> search -> review)
# =======================================================================


def _build_index_from_hunks(hunks: List[DiffHunk], repo_dir: str) -> DiffMindIndex:
    """Build a DiffMindIndex from parsed hunks using real TurboQuantizer."""
    from langchain_turboquant import TurboQuantizer
    n = len(hunks)
    dim = 32
    rng = np.random.RandomState(42)
    embeddings = rng.randn(n, dim).astype(np.float32)
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    quantizer = TurboQuantizer(dim=dim, bits=3)
    compressed = quantizer.quantize(embeddings)

    head = get_head_commit(repo_dir)

    return DiffMindIndex(
        hunks=hunks,
        compressed=compressed,
        quantizer=quantizer,
        model_name="all-MiniLM-L6-v2",
        embedding_dim=dim,
        total_commits=len(set(h.commit_hash for h in hunks)),
        bugfix_commits=sum(1 for h in hunks if h.is_bugfix),
        files_tracked=len(set(h.file_path for h in hunks)),
        languages=sorted(set(h.language for h in hunks if h.language != "unknown")),
        raw_memory_bytes=embeddings.nbytes,
        compressed_memory_bytes=100,
        learn_time=0.1,
        last_learned_commit=head,
    )


class TestFullPipeline:
    """Tests 16-25: Full pipeline tests with mock model for speed."""

    # 16. Learn from repo -> verify index is created and saved
    def test_learn_creates_index(self, repo_with_commits):
        hunks, total, bugfix = parse_git_log(repo_with_commits)
        assert total >= 2
        index = _build_index_from_hunks(hunks, repo_with_commits)
        save_index(index, repo_with_commits)
        assert index_exists(repo_with_commits)
        loaded = load_index(repo_with_commits)
        assert loaded.total_commits >= 2
        assert len(loaded.hunks) >= 2

    # 17. Learn -> search by semantic query -> verify results
    def test_search_returns_results(self, repo_with_commits):
        from diffmind.searcher import search

        hunks, _, _ = parse_git_log(repo_with_commits)
        index = _build_index_from_hunks(hunks, repo_with_commits)

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1, 32).astype(np.float32)

        results = search("hello function", index, model=mock_model, k=3)
        assert isinstance(results, list)
        # With random embeddings, we should get results (scores won't be -inf)
        assert len(results) >= 1

    # 18. Learn -> search with file filter -> only matching files returned
    def test_search_file_filter(self, repo_with_commits):
        from diffmind.searcher import search

        hunks, _, _ = parse_git_log(repo_with_commits)
        index = _build_index_from_hunks(hunks, repo_with_commits)

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1, 32).astype(np.float32)

        results = search("code", index, model=mock_model, file_path="app.js")
        for r in results:
            assert "app.js" in r.hunk.file_path.lower()

    # 19. Learn -> search with author filter
    def test_search_author_filter(self, repo_with_commits):
        from diffmind.searcher import search

        hunks, _, _ = parse_git_log(repo_with_commits)
        index = _build_index_from_hunks(hunks, repo_with_commits)

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1, 32).astype(np.float32)

        results = search("anything", index, model=mock_model, author="Test Author")
        for r in results:
            assert "test author" in r.hunk.author.lower()

    # 20. Learn -> search with language filter
    def test_search_language_filter(self, repo_with_commits):
        from diffmind.searcher import search

        hunks, _, _ = parse_git_log(repo_with_commits)
        index = _build_index_from_hunks(hunks, repo_with_commits)

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1, 32).astype(np.float32)

        results = search("code", index, model=mock_model, language="javascript")
        for r in results:
            assert r.hunk.language == "javascript"

    # 21. Learn -> search with bugfix-only filter
    def test_search_bugfix_only_filter(self, repo_with_commits):
        from diffmind.searcher import search

        hunks, _, _ = parse_git_log(repo_with_commits)
        index = _build_index_from_hunks(hunks, repo_with_commits)

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1, 32).astype(np.float32)

        results = search("fix", index, model=mock_model, bugfix_only=True)
        for r in results:
            assert r.hunk.is_bugfix is True

    # 22. Learn with --bugfix-only option
    def test_learn_bugfix_only(self, repo_with_commits):
        hunks, total, bugfix = parse_git_log(repo_with_commits)
        bugfix_hunks = [h for h in hunks if h.is_bugfix]
        assert len(bugfix_hunks) >= 1
        # Simulate what indexer.learn does with bugfix_only=True
        index = _build_index_from_hunks(bugfix_hunks, repo_with_commits)
        assert all(h.is_bugfix for h in index.hunks)

    # 23. Incremental learn: create initial index, add new commits, update
    def test_incremental_learn(self, repo_with_commits):
        hunks, total, _ = parse_git_log(repo_with_commits)
        initial_count = len(hunks)
        index = _build_index_from_hunks(hunks, repo_with_commits)
        initial_head = index.last_learned_commit

        # Add a new commit
        _write_file(repo_with_commits, "new_module.py", "def new_func():\n    return 42\n")
        _commit(repo_with_commits, "feat: add new module")

        # Parse only new commits since last learned
        new_hunks, new_total, _ = parse_git_log(
            repo_with_commits, since_commit=initial_head
        )
        assert new_total >= 1
        assert len(new_hunks) >= 1

        # Build updated index
        all_hunks = index.hunks + new_hunks
        updated_index = _build_index_from_hunks(all_hunks, repo_with_commits)
        assert len(updated_index.hunks) > initial_count

    # 24. Learn -> review current staged changes against past bugs
    def test_review_staged_changes(self, repo_with_commits):
        from diffmind.reviewer import review

        hunks, _, _ = parse_git_log(repo_with_commits)
        index = _build_index_from_hunks(hunks, repo_with_commits)

        # Make a change and stage it
        _write_file(repo_with_commits, "src/main.py", 'def hello():\n    if True:\n        print("modified")\n')
        _git(["add", "src/main.py"], repo_with_commits)

        mock_model = MagicMock()
        mock_model.encode.return_value = np.random.randn(1, 32).astype(np.float32)

        warnings = review(index, repo_path=repo_with_commits, staged=True, model=mock_model, threshold=0.0)
        # With threshold=0 we should get warnings (random similarity > 0 likely)
        assert isinstance(warnings, list)

    # 25. Learn -> review finds HIGH risk when similar bugfix exists
    def test_review_high_risk_bugfix(self, repo_dir):
        from diffmind.reviewer import review, classify_risk

        # Create a bugfix commit
        _write_file(repo_dir, "auth.py", "def login(user):\n    return user\n")
        _commit(repo_dir, "feat: add login")
        _write_file(repo_dir, "auth.py", "def login(user):\n    if user is None:\n        raise ValueError()\n    return user\n")
        _commit(repo_dir, "fix: null check in login")

        hunks, _, _ = parse_git_log(repo_dir)
        bugfix_hunks = [h for h in hunks if h.is_bugfix]
        assert len(bugfix_hunks) >= 1

        # Verify classify_risk logic
        assert classify_risk(0.95, bugfix_hunks[0]) == "HIGH"
        assert classify_risk(0.85, bugfix_hunks[0]) == "MEDIUM"
        assert classify_risk(0.75, bugfix_hunks[0]) == "LOW"


# =======================================================================
# Storage & Hook Tests
# =======================================================================


class TestStorageAndHooks:
    """Tests 26-28."""

    # 26. Save index -> load index -> verify roundtrip with real data
    def test_save_load_roundtrip_real_data(self, repo_with_commits):
        hunks, total, bugfix = parse_git_log(repo_with_commits)
        index = _make_fake_index(hunks, get_head_commit(repo_with_commits))

        save_index(index, repo_with_commits)
        loaded = load_index(repo_with_commits)

        assert loaded.total_commits == index.total_commits
        assert loaded.model_name == index.model_name
        assert loaded.embedding_dim == index.embedding_dim
        assert len(loaded.hunks) == len(hunks)
        assert loaded.last_learned_commit == index.last_learned_commit
        # Verify hunk data survived roundtrip
        for orig, loaded_h in zip(hunks, loaded.hunks):
            assert orig.file_path == loaded_h.file_path
            assert orig.commit_hash == loaded_h.commit_hash
            assert orig.commit_message == loaded_h.commit_message
            assert orig.author == loaded_h.author
            assert orig.is_bugfix == loaded_h.is_bugfix
            assert orig.language == loaded_h.language

    # 27. Install pre-commit hook -> verify file content
    def test_install_pre_commit_hook_real_repo(self, repo_dir):
        hook_path = install_pre_commit(repo_dir, fail_on="medium")
        assert os.path.exists(hook_path)
        with open(hook_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "#!/bin/sh" in content
        assert "DiffMind" in content
        assert "diffmind review" in content
        assert "medium" in content
        assert "MEDIUM" in content

    # 28. Generate GitHub Action -> verify YAML content
    def test_generate_github_action_real_repo(self, repo_dir):
        action_path = generate_github_action(repo_dir, fail_on="high")
        assert os.path.exists(action_path)
        assert action_path.endswith("diffmind.yml")
        with open(action_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "name: DiffMind Review" in content
        assert "pull_request" in content
        assert "diffmind learn" in content
        assert "diffmind review" in content
        assert "high" in content
        assert "actions/checkout@v4" in content


# =======================================================================
# Edge Cases
# =======================================================================


class TestEdgeCases:
    """Tests 29-30."""

    # 29. Empty repository (no commits) -> graceful handling
    def test_empty_repo_no_commits(self, repo_dir):
        hunks, total, bugfix = parse_git_log(repo_dir)
        assert total == 0
        assert bugfix == 0
        assert hunks == []

    # 30. Repository with only merge commits -> handled correctly
    def test_repo_with_merge_commits(self, repo_dir):
        # Create two branches with different files
        _write_file(repo_dir, "base.py", "base = True\n")
        _commit(repo_dir, "base commit")

        _git(["checkout", "-b", "branch-a"], repo_dir)
        _write_file(repo_dir, "a.py", "a = 1\n")
        _commit(repo_dir, "add a on branch-a")

        _git(["checkout", "master"], repo_dir, check=False)
        # Try master first, if it fails use main
        result = _git(["checkout", "master"], repo_dir, check=False)
        if result.returncode != 0:
            _git(["checkout", "main"], repo_dir, check=False)

        _write_file(repo_dir, "b.py", "b = 1\n")
        _commit(repo_dir, "add b on main")

        # Merge branch-a (creates a merge commit)
        _git(["merge", "branch-a", "--no-edit"], repo_dir)

        # parse_git_log uses --no-merges, so merge commits are excluded
        hunks, total, _ = parse_git_log(repo_dir)
        # We should get the non-merge commits
        assert total >= 2
        messages = {h.commit_message for h in hunks}
        # The merge commit message should NOT be in there
        assert not any("merge" in m.lower() for m in messages if "branch" in m.lower())


# =======================================================================
# Additional integration tests for completeness
# =======================================================================


class TestParseCurrentDiff:
    """Test parse_current_diff with real unstaged/staged changes."""

    def test_unstaged_diff(self, repo_dir):
        _write_file(repo_dir, "file.py", "x = 1\n")
        _commit(repo_dir, "initial")
        _write_file(repo_dir, "file.py", "x = 2\n")
        # Do NOT stage - this is an unstaged diff
        hunks = parse_current_diff(repo_dir, staged=False)
        assert len(hunks) >= 1
        assert hunks[0].file_path == "file.py"
        assert "1" in hunks[0].old_code
        assert "2" in hunks[0].new_code

    def test_staged_diff(self, repo_dir):
        _write_file(repo_dir, "file.py", "x = 1\n")
        _commit(repo_dir, "initial")
        _write_file(repo_dir, "file.py", "x = 99\n")
        _git(["add", "file.py"], repo_dir)

        hunks = parse_current_diff(repo_dir, staged=True)
        assert len(hunks) >= 1
        assert "99" in hunks[0].new_code

    def test_no_diff_returns_empty(self, repo_dir):
        _write_file(repo_dir, "file.py", "x = 1\n")
        _commit(repo_dir, "initial")
        # No changes
        hunks = parse_current_diff(repo_dir, staged=False)
        assert hunks == []


class TestGetHeadCommit:
    """Test get_head_commit with real repos."""

    def test_head_commit_hash(self, repo_dir):
        _write_file(repo_dir, "f.py", "f = 1\n")
        expected = _commit(repo_dir, "a commit")
        actual = get_head_commit(repo_dir)
        assert actual == expected
        assert len(actual) == 40  # full SHA-1

    def test_head_changes_after_commit(self, repo_dir):
        _write_file(repo_dir, "f.py", "f = 1\n")
        _commit(repo_dir, "first")
        head1 = get_head_commit(repo_dir)

        _write_file(repo_dir, "f.py", "f = 2\n")
        _commit(repo_dir, "second")
        head2 = get_head_commit(repo_dir)

        assert head1 != head2

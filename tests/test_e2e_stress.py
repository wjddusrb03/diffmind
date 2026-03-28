"""End-to-end stress tests for DiffMind using REAL git repositories.

Creates large temporary git repos with 20+ commits across multiple languages,
then exercises the full pipeline: parse -> index -> search -> review -> display.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import datetime, timezone, timedelta
from typing import List, Optional
from unittest.mock import MagicMock

import numpy as np
import pytest

from diffmind.models import DiffHunk, DiffMindIndex, ReviewWarning
from diffmind.parser import (
    detect_bugfix,
    detect_language,
    parse_git_log,
    get_head_commit,
)
from diffmind.searcher import search, SearchResult
from diffmind.reviewer import review, classify_risk
from diffmind.storage import save_index, load_index, index_exists, get_index_path
from diffmind.display import (
    display_review_report,
    display_search_results,
    display_stats,
)


# ── Helpers ────────────────────────────────────────────────────────────


def _git(args: List[str], cwd: str, check: bool = True) -> subprocess.CompletedProcess:
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
    _git(["init"], path)
    _git(["config", "user.email", "stress@test.com"], path)
    _git(["config", "user.name", "Stress Tester"], path)


def _write_file(repo: str, relpath: str, content: str) -> str:
    full = os.path.join(repo, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(content)
    return full


def _commit(repo: str, message: str) -> str:
    _git(["add", "-A"], repo)
    _git(["commit", "-m", message, "--allow-empty-message"], repo)
    result = _git(["rev-parse", "HEAD"], repo)
    return result.stdout.strip()


def create_large_repo(tmpdir: str) -> str:
    """Build a realistic git repo with 20+ commits across many languages."""
    _init_repo(tmpdir)

    # --- Feature commits (10+) ---
    _write_file(tmpdir, "src/main.py",
                "def main():\n    print('hello world')\n\nif __name__ == '__main__':\n    main()\n")
    _commit(tmpdir, "feat: initial Python project setup")

    _write_file(tmpdir, "src/utils.py",
                "def add(a, b):\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n")
    _commit(tmpdir, "feat: add math utility functions")

    _write_file(tmpdir, "web/app.js",
                "const express = require('express');\nconst app = express();\napp.get('/', (req, res) => res.send('OK'));\n")
    _commit(tmpdir, "feat: add Express.js web server")

    _write_file(tmpdir, "web/index.ts",
                "interface User {\n  id: number;\n  name: string;\n}\n\nfunction greet(user: User): string {\n  return `Hello ${user.name}`;\n}\n")
    _commit(tmpdir, "feat: add TypeScript user interface")

    _write_file(tmpdir, "api/Handler.java",
                "public class Handler {\n    public String handle(String input) {\n        return input.toUpperCase();\n    }\n}\n")
    _commit(tmpdir, "feat: add Java request handler")

    _write_file(tmpdir, "svc/server.go",
                "package main\n\nimport \"fmt\"\n\nfunc main() {\n    fmt.Println(\"server starting\")\n}\n")
    _commit(tmpdir, "feat: add Go service entry point")

    _write_file(tmpdir, "src/config.py",
                "import os\n\nDEBUG = os.getenv('DEBUG', 'false') == 'true'\nPORT = int(os.getenv('PORT', '8080'))\n")
    _commit(tmpdir, "feat: add configuration module")

    _write_file(tmpdir, "web/styles.css", "body { margin: 0; padding: 0; font-family: sans-serif; }\n")
    _commit(tmpdir, "feat: add base stylesheet")

    _write_file(tmpdir, "src/database.py",
                "class Database:\n    def __init__(self, url):\n        self.url = url\n        self.conn = None\n\n    def connect(self):\n        pass\n")
    _commit(tmpdir, "feat: add database connection class")

    _write_file(tmpdir, "src/auth.py",
                "def authenticate(token):\n    if not token:\n        return False\n    return len(token) > 10\n")
    _commit(tmpdir, "feat: add authentication module")

    # --- Bugfix commits (5+) ---
    _write_file(tmpdir, "src/utils.py",
                "def add(a, b):\n    if a is None or b is None:\n        raise ValueError('args cannot be None')\n    return a + b\n\ndef subtract(a, b):\n    return a - b\n")
    _commit(tmpdir, "fix: add null check to add() function")

    _write_file(tmpdir, "src/auth.py",
                "def authenticate(token):\n    if token is None:\n        return False\n    if not isinstance(token, str):\n        return False\n    return len(token) > 10\n")
    _commit(tmpdir, "bugfix: handle non-string tokens in auth")

    _write_file(tmpdir, "api/Handler.java",
                "public class Handler {\n    public String handle(String input) {\n        if (input == null) return \"\";\n        return input.toUpperCase();\n    }\n}\n")
    _commit(tmpdir, "hotfix: null pointer exception in Handler")

    _write_file(tmpdir, "svc/server.go",
                "package main\n\nimport (\n    \"fmt\"\n    \"log\"\n)\n\nfunc main() {\n    log.Println(\"server starting\")\n    fmt.Println(\"ready\")\n}\n")
    _commit(tmpdir, "fix: use log.Println for proper logging, closes #42")

    _write_file(tmpdir, "src/database.py",
                "class Database:\n    def __init__(self, url):\n        if not url:\n            raise ValueError('Database URL required')\n        self.url = url\n        self.conn = None\n\n    def connect(self):\n        pass\n\n    def disconnect(self):\n        self.conn = None\n")
    _commit(tmpdir, "fix: validate database URL on init")

    # --- Revert commits (2+) ---
    _write_file(tmpdir, "web/app.js",
                "const express = require('express');\nconst app = express();\napp.get('/', (req, res) => res.send('OK'));\n// Reverted experimental route\n")
    _commit(tmpdir, "Revert 'feat: add experimental API route'")

    _write_file(tmpdir, "src/config.py",
                "import os\n\nDEBUG = os.getenv('DEBUG', 'false') == 'true'\nPORT = int(os.getenv('PORT', '8080'))\nMAX_RETRIES = 3\n")
    _commit(tmpdir, "Revert 'remove retry config'")

    # --- Unicode / Korean message commits ---
    _write_file(tmpdir, "src/i18n.py",
                "MESSAGES = {\n    'ko': '안녕하세요',\n    'en': 'Hello',\n    'ja': 'こんにちは',\n}\n")
    _commit(tmpdir, "feat: 다국어 메시지 지원 추가")

    _write_file(tmpdir, "src/i18n.py",
                "MESSAGES = {\n    'ko': '안녕하세요',\n    'en': 'Hello',\n    'ja': 'こんにちは',\n    'zh': '你好',\n}\n")
    _commit(tmpdir, "fix: 중국어 번역 버그 수정")

    # --- Special chars in commit message ---
    _write_file(tmpdir, "src/parser_mod.py",
                "def parse(text):\n    return text.split('\\n')\n")
    _commit(tmpdir, "feat: add parser for \"quoted\" strings & <tags>")

    # --- Extra feature commits to reach 20+ ---
    _write_file(tmpdir, "tests/test_utils.py",
                "def test_add():\n    from src.utils import add\n    assert add(1, 2) == 3\n")
    _commit(tmpdir, "test: add unit tests for utils")

    _write_file(tmpdir, "docs/README.md", "# Project\nDocumentation here.\n")
    _commit(tmpdir, "docs: add project readme")

    return tmpdir


def _build_index(hunks: List[DiffHunk], repo_path: str, seed: int = 42) -> DiffMindIndex:
    """Build a DiffMindIndex from hunks using real TurboQuantizer + random embeddings."""
    from langchain_turboquant import TurboQuantizer

    n = len(hunks)
    dim = 32
    rng = np.random.RandomState(seed)
    embeddings = rng.randn(n, dim).astype(np.float32)
    # Normalize
    norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    embeddings = embeddings / norms

    quantizer = TurboQuantizer(dim=dim, bits=3)
    compressed = quantizer.quantize(embeddings)

    head = ""
    try:
        head = get_head_commit(repo_path)
    except Exception:
        pass

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


def _mock_model(seed: int = 99) -> MagicMock:
    """Return a mock SentenceTransformer that returns random 32-d embeddings."""
    rng = np.random.RandomState(seed)
    m = MagicMock()
    def _encode(texts, **kwargs):
        count = len(texts) if hasattr(texts, '__len__') else 1
        vecs = rng.randn(count, 32).astype(np.float32)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return vecs / norms
    m.encode.side_effect = _encode
    return m


# ── Fixtures ───────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def large_repo():
    """Module-scoped large repo to avoid recreating 20+ commits per test."""
    with tempfile.TemporaryDirectory() as tmpdir:
        create_large_repo(tmpdir)
        yield tmpdir


@pytest.fixture(scope="module")
def parsed_data(large_repo):
    """Module-scoped parsed hunks from the large repo."""
    hunks, total, bugfix = parse_git_log(large_repo)
    return hunks, total, bugfix


@pytest.fixture(scope="module")
def large_index(parsed_data, large_repo):
    """Module-scoped index built from the large repo."""
    hunks, _, _ = parsed_data
    return _build_index(hunks, large_repo)


# =======================================================================
# Large Repo Tests (10 tests)
# =======================================================================


class TestLargeRepoParsing:
    """Tests 1-10: parsing a 20+ commit repository."""

    # 1. Parse 20+ commits -> correct total_commits count
    def test_total_commits_count(self, parsed_data):
        _, total, _ = parsed_data
        assert total >= 20, f"Expected >= 20 commits, got {total}"

    # 2. Parse 20+ commits -> correct bugfix_commits count
    def test_bugfix_commits_count(self, parsed_data):
        hunks, _, bugfix = parsed_data
        # We created 5 fix commits + 2 reverts + 1 Korean fix = 8 bugfix commits
        assert bugfix >= 5, f"Expected >= 5 bugfix commits, got {bugfix}"

    # 3. Parse -> all hunks have non-empty file_path
    def test_all_hunks_have_file_path(self, parsed_data):
        hunks, _, _ = parsed_data
        for h in hunks:
            assert h.file_path, f"Hunk has empty file_path: {h.commit_message}"
            assert len(h.file_path) > 0

    # 4. Parse -> all hunks have valid timestamp
    def test_all_hunks_have_valid_timestamp(self, parsed_data):
        hunks, _, _ = parsed_data
        for h in hunks:
            assert h.timestamp is not None, f"Hunk has None timestamp: {h.commit_message}"
            assert h.timestamp.year > 2000, f"Hunk has year <= 2000: {h.timestamp}"

    # 5. Parse -> bugfix hunks correctly detected
    def test_bugfix_hunks_detected(self, parsed_data):
        hunks, _, _ = parsed_data
        bugfix_hunks = [h for h in hunks if h.is_bugfix]
        assert len(bugfix_hunks) >= 5
        # Check that known bugfix messages are flagged
        bugfix_messages = [h.commit_message for h in bugfix_hunks]
        msg_text = " ".join(bugfix_messages).lower()
        assert "fix" in msg_text or "bug" in msg_text or "hotfix" in msg_text or "revert" in msg_text

    # 6. Parse -> language detection correct for all file types
    def test_language_detection_all_types(self, parsed_data):
        hunks, _, _ = parsed_data
        langs_found = set(h.language for h in hunks)
        assert "python" in langs_found, f"Missing python in {langs_found}"
        assert "javascript" in langs_found, f"Missing javascript in {langs_found}"
        assert "typescript" in langs_found, f"Missing typescript in {langs_found}"
        assert "java" in langs_found, f"Missing java in {langs_found}"
        assert "go" in langs_found, f"Missing go in {langs_found}"

    # 7. Parse -> author name extracted for every hunk
    def test_author_extracted_for_all_hunks(self, parsed_data):
        hunks, _, _ = parsed_data
        for h in hunks:
            assert h.author, f"Hunk missing author: {h.commit_message}"
            assert h.author == "Stress Tester"

    # 8. Parse with since date -> filters correctly
    def test_parse_since_date_filters(self, large_repo):
        # All commits are very recent, so since "1 hour ago" should get them all
        hunks_recent, total_recent, _ = parse_git_log(large_repo, since="1 hour ago")
        assert total_recent >= 20

        # A future date should yield nothing
        hunks_future, total_future, _ = parse_git_log(large_repo, since="2099-01-01")
        assert total_future == 0
        assert len(hunks_future) == 0

    # 9. Parse with since_commit -> only newer commits parsed
    def test_parse_since_commit(self, large_repo):
        # Get all hunks first
        all_hunks, all_total, _ = parse_git_log(large_repo)
        assert all_total >= 20

        # Get the commit hash of roughly the 10th commit (using git log)
        result = _git(["log", "--format=%H", "--reverse"], large_repo)
        commit_hashes = result.stdout.strip().split("\n")
        mid_hash = commit_hashes[len(commit_hashes) // 2]

        # Parse only commits after the midpoint
        later_hunks, later_total, _ = parse_git_log(large_repo, since_commit=mid_hash)
        assert later_total < all_total, "since_commit should reduce total commits"
        assert later_total > 0, "Should have some commits after midpoint"

    # 10. Verify commit hashes are valid 40-char hex strings
    def test_commit_hashes_valid_hex(self, parsed_data):
        hunks, _, _ = parsed_data
        hex_pattern = re.compile(r"^[0-9a-f]{40}$")
        seen_hashes = set()
        for h in hunks:
            seen_hashes.add(h.commit_hash)
        for ch in seen_hashes:
            assert hex_pattern.match(ch), f"Invalid commit hash: {ch}"


# =======================================================================
# Save/Load Stress Tests (5 tests)
# =======================================================================


class TestSaveLoadStress:
    """Tests 11-15: save/load index stress."""

    # 11. Save 20+ hunk index -> load -> all hunks preserved
    def test_save_load_all_hunks_preserved(self, large_index, parsed_data):
        hunks, _, _ = parsed_data
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _write_file(tmpdir, "x.py", "x=1\n")
            _commit(tmpdir, "init")
            save_index(large_index, tmpdir)
            loaded = load_index(tmpdir)
            assert len(loaded.hunks) == len(hunks)
            for orig, ld in zip(large_index.hunks, loaded.hunks):
                assert orig.file_path == ld.file_path
                assert orig.commit_hash == ld.commit_hash
                assert orig.commit_message == ld.commit_message
                assert orig.is_bugfix == ld.is_bugfix

    # 12. Save -> load -> search still works on loaded index
    def test_search_works_on_loaded_index(self, large_index, parsed_data):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _write_file(tmpdir, "x.py", "x=1\n")
            _commit(tmpdir, "init")
            save_index(large_index, tmpdir)
            loaded = load_index(tmpdir)
            mock = _mock_model(seed=77)
            results = search("null check", loaded, model=mock, k=3)
            assert isinstance(results, list)
            # With random embeddings we should get some results
            assert len(results) >= 1

    # 13. Index file size is reasonable (< 1MB for 20 hunks with dim=32)
    def test_index_file_size_reasonable(self, large_index):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _write_file(tmpdir, "x.py", "x=1\n")
            _commit(tmpdir, "init")
            save_index(large_index, tmpdir)
            path = get_index_path(tmpdir)
            size = os.path.getsize(path)
            assert size < 1_000_000, f"Index file too large: {size} bytes"
            assert size > 0, "Index file is empty"

    # 14. Save multiple times -> last save wins (overwrite)
    def test_save_overwrite(self, parsed_data, large_repo):
        hunks, _, _ = parsed_data
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _write_file(tmpdir, "x.py", "x=1\n")
            _commit(tmpdir, "init")

            # First save with all hunks
            idx1 = _build_index(hunks, large_repo, seed=10)
            save_index(idx1, tmpdir)

            # Second save with only 3 hunks
            idx2 = _build_index(hunks[:3], large_repo, seed=20)
            save_index(idx2, tmpdir)

            loaded = load_index(tmpdir)
            assert len(loaded.hunks) == 3, "Last save should overwrite"

    # 15. Load index from different working directory (absolute path)
    def test_load_from_absolute_path(self, large_index):
        with tempfile.TemporaryDirectory() as tmpdir:
            _init_repo(tmpdir)
            _write_file(tmpdir, "x.py", "x=1\n")
            _commit(tmpdir, "init")
            save_index(large_index, tmpdir)

            # Load using the absolute path from a different cwd
            original_cwd = os.getcwd()
            try:
                os.chdir(tempfile.gettempdir())
                abs_path = os.path.abspath(tmpdir)
                loaded = load_index(abs_path)
                assert len(loaded.hunks) == len(large_index.hunks)
            finally:
                os.chdir(original_cwd)


# =======================================================================
# Search Filter Combinations (10 tests)
# =======================================================================


class TestSearchFilterCombinations:
    """Tests 16-25: search with various filter combinations."""

    # 16. file_path + language filter -> intersection
    def test_file_path_and_language_filter(self, large_index):
        mock = _mock_model(seed=1)
        results = search("code", large_index, model=mock, k=50,
                         file_path="main.py", language="python")
        for r in results:
            assert "main.py" in r.hunk.file_path.lower()
            assert r.hunk.language == "python"

    # 17. author + bugfix_only -> intersection
    def test_author_and_bugfix_only(self, large_index):
        mock = _mock_model(seed=2)
        results = search("fix", large_index, model=mock, k=50,
                         author="Stress", bugfix_only=True)
        for r in results:
            assert "stress" in r.hunk.author.lower()
            assert r.hunk.is_bugfix is True

    # 18. after + before date range -> correct range
    def test_date_range_filter(self, large_index):
        mock = _mock_model(seed=3)
        now = datetime.now()
        one_hour_ago = now - timedelta(hours=1)
        one_hour_later = now + timedelta(hours=1)
        results = search("code", large_index, model=mock, k=50,
                         after=one_hour_ago, before=one_hour_later)
        for r in results:
            ts = r.hunk.timestamp.replace(tzinfo=None)
            assert ts >= one_hour_ago
            assert ts <= one_hour_later

    # 19. after date in future -> no results
    def test_after_future_date(self, large_index):
        mock = _mock_model(seed=4)
        future = datetime(2099, 1, 1)
        results = search("code", large_index, model=mock, k=50, after=future)
        assert len(results) == 0

    # 20. before date in past -> no results
    def test_before_past_date(self, large_index):
        mock = _mock_model(seed=5)
        past = datetime(2000, 1, 1)
        results = search("code", large_index, model=mock, k=50, before=past)
        assert len(results) == 0

    # 21. All filters combined -> correct intersection
    def test_all_filters_combined(self, large_index):
        mock = _mock_model(seed=6)
        now = datetime.now()
        results = search(
            "fix", large_index, model=mock, k=50,
            file_path="utils.py",
            author="Stress",
            language="python",
            bugfix_only=True,
            after=now - timedelta(hours=1),
            before=now + timedelta(hours=1),
        )
        for r in results:
            assert "utils.py" in r.hunk.file_path.lower()
            assert "stress" in r.hunk.author.lower()
            assert r.hunk.language == "python"
            assert r.hunk.is_bugfix is True

    # 22. Search with k > total hunks -> returns all hunks (that have finite scores)
    def test_k_greater_than_total(self, large_index):
        mock = _mock_model(seed=7)
        n_hunks = len(large_index.hunks)
        results = search("code", large_index, model=mock, k=n_hunks + 100)
        # Should return at most n_hunks results
        assert len(results) <= n_hunks

    # 23. Search with k=0 -> returns empty
    def test_k_zero_returns_empty(self, large_index):
        mock = _mock_model(seed=8)
        results = search("code", large_index, model=mock, k=0)
        assert len(results) == 0

    # 24. Search with k=1 -> returns exactly 1
    def test_k_one_returns_one(self, large_index):
        mock = _mock_model(seed=9)
        results = search("code", large_index, model=mock, k=1)
        assert len(results) == 1

    # 25. Non-matching author filter -> returns empty
    def test_nonmatching_author(self, large_index):
        mock = _mock_model(seed=10)
        results = search("code", large_index, model=mock, k=50,
                         author="NoSuchAuthor_XYZ")
        assert len(results) == 0


# =======================================================================
# Review Stress Tests (5 tests)
# =======================================================================


class TestReviewStress:
    """Tests 26-30: review engine stress."""

    def _make_staged_hunks(self, n: int) -> List[DiffHunk]:
        """Create n fake staged hunks for review."""
        hunks = []
        for i in range(n):
            hunks.append(DiffHunk(
                commit_hash="WORKING",
                file_path=f"src/file{i}.py",
                language="python",
                old_code=f"old_line_{i} = {i}",
                new_code=f"new_line_{i} = {i + 1}",
                context=f"# context for file {i}",
                commit_message="(current changes)",
                author="(you)",
                timestamp=datetime.now(timezone.utc),
                is_bugfix=False,
            ))
        return hunks

    # 26. Review with 5 staged hunks simultaneously -> each gets independent warnings
    def test_review_five_staged_hunks(self, large_index):
        staged = self._make_staged_hunks(5)
        mock = _mock_model(seed=50)
        warnings = review(large_index, threshold=0.0, model=mock, hunks=staged, top_k=1)
        assert isinstance(warnings, list)
        # With threshold=0.0 and random embeddings, we should get warnings
        # Each of the 5 hunks can produce up to top_k=1 warning
        warned_files = set(w.current_hunk.file_path for w in warnings)
        assert len(warned_files) >= 1

    # 27. Review with threshold=1.0 -> no warnings (impossible to reach)
    def test_review_threshold_one_no_warnings(self, large_index):
        staged = self._make_staged_hunks(3)
        mock = _mock_model(seed=51)
        warnings = review(large_index, threshold=1.0, model=mock, hunks=staged)
        # Cosine similarity rarely equals exactly 1.0 with random vectors
        assert len(warnings) == 0

    # 28. Review with threshold=0.0 -> warnings for everything
    def test_review_threshold_zero_warnings_for_all(self, large_index):
        staged = self._make_staged_hunks(2)
        mock = _mock_model(seed=52)
        warnings = review(large_index, threshold=0.0, model=mock, hunks=staged, top_k=3)
        assert len(warnings) > 0

    # 29. Review outputs valid JSON with --json flag (verify structure)
    def test_review_json_structure(self, large_index):
        staged = self._make_staged_hunks(2)
        mock = _mock_model(seed=53)
        warnings = review(large_index, threshold=0.0, model=mock, hunks=staged, top_k=1)
        json_str = display_review_report(warnings, total_hunks=2, as_json=True)
        data = json.loads(json_str)
        assert "total_hunks" in data
        assert "warning_count" in data
        assert "warnings" in data
        assert data["total_hunks"] == 2
        assert data["warning_count"] == len(warnings)
        for w in data["warnings"]:
            assert "risk_level" in w
            assert "similarity" in w
            assert "current_file" in w
            assert "past_file" in w
            assert "past_commit" in w
            assert "is_bugfix" in w

    # 30. Review with fail-on + no warnings -> exit code 0
    def test_review_no_warnings_exit_zero(self, large_index):
        staged = self._make_staged_hunks(1)
        mock = _mock_model(seed=54)
        warnings = review(large_index, threshold=1.0, model=mock, hunks=staged)
        assert len(warnings) == 0
        # Simulate CLI: no warnings means exit code 0
        exit_code = 1 if warnings else 0
        assert exit_code == 0


# =======================================================================
# Display Format Tests (5 tests)
# =======================================================================


class TestDisplayFormats:
    """Tests 31-35: display formatting."""

    def _make_warning(self, risk: str, similarity: float, is_bugfix: bool = True) -> ReviewWarning:
        now = datetime.now(timezone.utc)
        current = DiffHunk(
            commit_hash="WORKING", file_path="src/current.py", language="python",
            old_code="old = 1", new_code="new = 2", context="# ctx",
            commit_message="(current)", author="(you)", timestamp=now,
            is_bugfix=False,
        )
        past = DiffHunk(
            commit_hash="a" * 40, file_path="src/past.py", language="python",
            old_code="past_old = 1", new_code="past_new = 2", context="# past ctx",
            commit_message="fix: past bug" if is_bugfix else "feat: past feature",
            author="Past Author", timestamp=now - timedelta(days=30),
            is_bugfix=is_bugfix,
        )
        return ReviewWarning(
            current_hunk=current,
            similar_hunk=past,
            similarity=similarity,
            risk_level=risk,
            reason=f"Similar change ({similarity:.0%}) to past commit.",
        )

    # 31. display_review_report with 0 warnings -> contains "No similar"
    def test_display_zero_warnings(self):
        report = display_review_report([], total_hunks=5, as_json=False)
        assert "No similar" in report

    # 32. display_review_report with 3 warnings -> contains all risk levels
    def test_display_three_warnings_all_risks(self):
        warnings = [
            self._make_warning("HIGH", 0.95),
            self._make_warning("MEDIUM", 0.85),
            self._make_warning("LOW", 0.75),
        ]
        report = display_review_report(warnings, total_hunks=5, as_json=False)
        assert "HIGH" in report
        assert "MEDIUM" in report
        assert "LOW" in report
        assert "[!!!]" in report
        assert "[!!]" in report
        assert "[!]" in report

    # 33. display_search_results with 5 results -> numbered 1-5
    def test_display_search_results_numbered(self, parsed_data):
        hunks, _, _ = parsed_data
        results = [SearchResult(hunk=h, score=0.9 - i * 0.1) for i, h in enumerate(hunks[:5])]
        output = display_search_results(results)
        for i in range(1, 6):
            assert f"{i}." in output

    # 34. display_stats -> contains all expected fields
    def test_display_stats_all_fields(self, large_index):
        output = display_stats(large_index)
        assert "Total commits" in output or "commits" in output.lower()
        assert "Bugfix" in output or "bugfix" in output.lower()
        assert "Files tracked" in output or "files" in output.lower()
        assert "Languages" in output or "languages" in output.lower()
        assert "Model" in output or "model" in output.lower()
        assert "python" in output.lower()

    # 35. display_review_report JSON mode -> valid JSON with correct field names
    def test_display_json_mode_valid(self):
        warnings = [
            self._make_warning("HIGH", 0.92),
            self._make_warning("LOW", 0.78, is_bugfix=False),
        ]
        json_str = display_review_report(warnings, total_hunks=3, as_json=True)
        data = json.loads(json_str)
        assert data["total_hunks"] == 3
        assert data["warning_count"] == 2
        assert len(data["warnings"]) == 2
        w0 = data["warnings"][0]
        required_fields = ["risk_level", "similarity", "current_file", "past_file",
                           "past_commit", "past_message", "past_date", "past_author",
                           "is_bugfix", "reason"]
        for field in required_fields:
            assert field in w0, f"Missing field: {field}"

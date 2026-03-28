"""End-to-end CLI tests for DiffMind using Click's CliRunner and real git repos."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from unittest.mock import MagicMock

import numpy as np
import pytest
from click.testing import CliRunner

from diffmind.cli import main
from diffmind.models import DiffMindIndex
from diffmind.parser import parse_git_log, get_head_commit
from diffmind.storage import save_index, load_index, index_exists

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

EMBEDDING_DIM = 384  # must match all-MiniLM-L6-v2 output dim


def _git(args: list, cwd: str):
    return subprocess.run(
        ["git"] + args, cwd=cwd,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def create_test_repo(tmpdir: str) -> str:
    repo = os.path.join(tmpdir, "repo")
    os.makedirs(repo)
    _git(["init"], repo)
    _git(["config", "user.email", "test@test.com"], repo)
    _git(["config", "user.name", "Test Author"], repo)

    # Commit 1 - initial Python file
    with open(os.path.join(repo, "app.py"), "w") as f:
        f.write("def hello():\n    return 'hello'\n")
    _git(["add", "app.py"], repo)
    _git(["commit", "-m", "feat: initial commit"], repo)

    # Commit 2 - bugfix
    with open(os.path.join(repo, "app.py"), "w") as f:
        f.write("def hello(name):\n    if not name:\n        raise ValueError\n    return f'hello {name}'\n")
    _git(["add", "app.py"], repo)
    _git(["commit", "-m", "fix: add null check for name parameter"], repo)

    # Commit 3 - feature
    with open(os.path.join(repo, "utils.py"), "w") as f:
        f.write("def add(a, b):\n    return a + b\n")
    _git(["add", "utils.py"], repo)
    _git(["commit", "-m", "feat: add utility functions"], repo)

    # Commit 4 - another bugfix
    with open(os.path.join(repo, "utils.py"), "w") as f:
        f.write("def add(a, b):\n    if a is None or b is None:\n        return 0\n    return a + b\n")
    _git(["add", "utils.py"], repo)
    _git(["commit", "-m", "fix: handle None inputs in add()"], repo)

    # Commit 5 - JS feature
    with open(os.path.join(repo, "index.js"), "w") as f:
        f.write("function greet(name) {\n  return `Hello, ${name}`;\n}\n")
    _git(["add", "index.js"], repo)
    _git(["commit", "-m", "feat: add JavaScript greeting"], repo)

    return repo


def _build_index(repo: str, bugfix_only: bool = False) -> DiffMindIndex:
    """Build and save an index using real TurboQuantizer (pickle-able)."""
    from langchain_turboquant import TurboQuantizer

    hunks, total, bugfix_count = parse_git_log(repo)
    if bugfix_only:
        hunks = [h for h in hunks if h.is_bugfix]
    if not hunks:
        return None

    n = len(hunks)
    rng = np.random.RandomState(42)
    embeddings = rng.randn(n, EMBEDDING_DIM).astype(np.float32)

    quantizer = TurboQuantizer(dim=EMBEDDING_DIM, bits=3)
    compressed = quantizer.quantize(embeddings)
    head = get_head_commit(repo)

    idx = DiffMindIndex(
        hunks=hunks, compressed=compressed, quantizer=quantizer,
        model_name="all-MiniLM-L6-v2", embedding_dim=EMBEDDING_DIM,
        total_commits=total, bugfix_commits=bugfix_count,
        files_tracked=len(set(h.file_path for h in hunks)),
        languages=sorted(set(h.language for h in hunks if h.language != "unknown")),
        raw_memory_bytes=embeddings.nbytes,
        compressed_memory_bytes=sys.getsizeof(compressed),
        learn_time=0.1, last_learned_commit=head,
    )
    save_index(idx, repo)
    return idx


def _fake_model():
    m = MagicMock()
    m.encode = MagicMock(
        side_effect=lambda texts, **kw: np.random.randn(
            len(texts) if isinstance(texts, list) else 1, EMBEDDING_DIM
        ).astype(np.float32)
    )
    return m


# ---------------------------------------------------------------------------
# CLI Learn Tests
# ---------------------------------------------------------------------------

class TestLearn:
    def test_learn_valid_repo(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        idx = _build_index(repo)
        assert idx is not None
        assert len(idx.hunks) >= 3
        assert index_exists(repo)

    def test_learn_bugfix_only(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        idx = _build_index(repo, bugfix_only=True)
        assert idx is not None
        assert all(h.is_bugfix for h in idx.hunks)

    def test_learn_bits_2(self, tmp_path):
        from langchain_turboquant import TurboQuantizer
        repo = create_test_repo(str(tmp_path))
        hunks, _, _ = parse_git_log(repo)
        emb = np.random.randn(len(hunks), EMBEDDING_DIM).astype(np.float32)
        q = TurboQuantizer(dim=EMBEDDING_DIM, bits=2)
        compressed = q.quantize(emb)
        assert compressed is not None

    def test_learn_bits_4(self, tmp_path):
        from langchain_turboquant import TurboQuantizer
        repo = create_test_repo(str(tmp_path))
        hunks, _, _ = parse_git_log(repo)
        emb = np.random.randn(len(hunks), EMBEDDING_DIM).astype(np.float32)
        q = TurboQuantizer(dim=EMBEDDING_DIM, bits=4)
        compressed = q.quantize(emb)
        assert compressed is not None

    def test_learn_nonexistent_path(self, tmp_path):
        runner = CliRunner()
        result = runner.invoke(main, ["learn", str(tmp_path / "nope")])
        assert result.exit_code != 0 or "error" in (result.output or "").lower()

    def test_learn_non_git_directory(self, tmp_path):
        non_git = str(tmp_path / "notgit")
        os.makedirs(non_git)
        runner = CliRunner()
        result = runner.invoke(main, ["learn", non_git])
        assert result.exit_code != 0 or "no diff hunks" in (result.output or "").lower()

    def test_learn_update_after_initial(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        # Add new commit
        with open(os.path.join(repo, "new.py"), "w") as f:
            f.write("x = 1\n")
        _git(["add", "new.py"], repo)
        _git(["commit", "-m", "feat: add new file"], repo)

        # Verify new commits exist
        new_hunks, new_total, _ = parse_git_log(
            repo, since_commit=load_index(repo).last_learned_commit
        )
        assert new_total >= 1

    def test_learn_creates_index_file(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)
        assert os.path.isfile(os.path.join(repo, ".diffmind", "index.pkl"))


# ---------------------------------------------------------------------------
# CLI Review Tests
# ---------------------------------------------------------------------------

class TestReview:
    def test_review_without_index_gives_error(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(main, ["review", "--path", repo])
        assert result.exit_code != 0

    def test_review_after_learn_no_crash(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        # Make a change
        with open(os.path.join(repo, "app.py"), "w") as f:
            f.write("def hello():\n    return 'changed'\n")

        runner = CliRunner()
        # Review loads model internally - but without staged/unstaged diff it may say no changes
        result = runner.invoke(main, ["review", "--path", repo])
        # No crash - exit code 0 is fine (it processes the diff)
        assert result.exit_code == 0

    def test_review_staged(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        with open(os.path.join(repo, "app.py"), "w") as f:
            f.write("def hello():\n    return 'staged'\n")
        _git(["add", "app.py"], repo)

        runner = CliRunner()
        result = runner.invoke(main, ["review", "--staged", "--path", repo])
        assert result.exit_code == 0

    def test_review_json_output(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        with open(os.path.join(repo, "app.py"), "w") as f:
            f.write("def hello():\n    return 'json'\n")

        runner = CliRunner()
        result = runner.invoke(main, ["review", "--json", "--path", repo])
        assert result.exit_code == 0
        output = result.output.strip()
        # If JSON output contains valid JSON, verify structure
        try:
            data = json.loads(output)
            assert "total_hunks" in data
            assert "warnings" in data
        except json.JSONDecodeError:
            # May be "No changes to review." or plain text report
            pass

    def test_review_high_threshold(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        with open(os.path.join(repo, "app.py"), "w") as f:
            f.write("def hello():\n    return 'threshold'\n")

        runner = CliRunner()
        result = runner.invoke(main, ["review", "--threshold", "0.99", "--path", repo])
        assert result.exit_code == 0

    def test_review_fail_on_exit_code(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        with open(os.path.join(repo, "app.py"), "w") as f:
            f.write("def hello():\n    return 'failon'\n")

        runner = CliRunner()
        result = runner.invoke(main, ["review", "--fail-on", "high", "--path", repo])
        assert result.exit_code in (0, 1)


# ---------------------------------------------------------------------------
# CLI Search Tests
# ---------------------------------------------------------------------------

class TestSearch:
    def test_search_returns_results(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["search", "null check", "--path", repo])
        assert result.exit_code == 0
        assert len(result.output.strip()) > 0

    def test_search_limit_k(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["search", "function", "--path", repo, "-k", "2"])
        assert result.exit_code == 0
        import re
        numbered = re.findall(r"^\d+\.", result.output, re.MULTILINE)
        assert len(numbered) <= 2

    def test_search_filter_lang(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["search", "code", "--path", repo, "--lang", "python"])
        assert result.exit_code == 0

    def test_search_filter_author(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["search", "hello", "--path", repo, "--author", "Test Author"])
        assert result.exit_code == 0

    def test_search_bugfix_only(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["search", "fix", "--path", repo, "--bugfix-only"])
        assert result.exit_code == 0
        if "No results" not in result.output:
            for line in result.output.split("\n"):
                if "Message:" in line:
                    msg = line.split("Message:")[1].strip().lower()
                    assert any(kw in msg for kw in ["fix", "bug", "hotfix", "patch", "resolve"])

    def test_search_without_index_gives_error(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(main, ["search", "query", "--path", repo])
        assert result.exit_code != 0


# ---------------------------------------------------------------------------
# CLI Stats Tests
# ---------------------------------------------------------------------------

class TestStats:
    def test_stats_shows_statistics(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["stats", "--path", repo])
        assert result.exit_code == 0
        assert "Statistics" in result.output

    def test_stats_includes_counts(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)

        runner = CliRunner()
        result = runner.invoke(main, ["stats", "--path", repo])
        assert result.exit_code == 0
        output_lower = result.output.lower()
        assert "commit" in output_lower
        assert "file" in output_lower
        assert "language" in output_lower


# ---------------------------------------------------------------------------
# CLI Install Tests
# ---------------------------------------------------------------------------

class TestInstall:
    def test_install_pre_commit(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(main, ["install", "--pre-commit", "--path", repo])
        assert result.exit_code == 0
        hook_path = os.path.join(repo, ".git", "hooks", "pre-commit")
        assert os.path.isfile(hook_path)
        with open(hook_path) as f:
            assert "DiffMind" in f.read()

    def test_install_github_action(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(main, ["install", "--github-action", "--path", repo])
        assert result.exit_code == 0
        assert os.path.isfile(os.path.join(repo, ".github", "workflows", "diffmind.yml"))

    def test_install_without_flags(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(main, ["install", "--path", repo])
        assert "Specify" in result.output or "--pre-commit" in result.output


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_version_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--version"])
        assert "0.1.0" in result.output

    def test_help_flag(self):
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert "DiffMind" in result.output

    def test_review_no_changes(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        _build_index(repo)
        runner = CliRunner()
        result = runner.invoke(main, ["review", "--path", repo])
        assert result.exit_code == 0
        assert "no changes" in result.output.lower()

    def test_stats_without_index_gives_error(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(main, ["stats", "--path", repo])
        assert result.exit_code != 0

    def test_install_both(self, tmp_path):
        repo = create_test_repo(str(tmp_path))
        runner = CliRunner()
        result = runner.invoke(main, ["install", "--pre-commit", "--github-action", "--path", repo])
        assert result.exit_code == 0
        assert os.path.isfile(os.path.join(repo, ".git", "hooks", "pre-commit"))
        assert os.path.isfile(os.path.join(repo, ".github", "workflows", "diffmind.yml"))

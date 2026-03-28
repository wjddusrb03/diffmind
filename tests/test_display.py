"""Tests for DiffMind display formatting."""

import json
from datetime import datetime

from diffmind.display import (
    display_review_report,
    display_search_results,
    display_stats,
)
from diffmind.models import DiffHunk, DiffMindIndex, ReviewWarning
from diffmind.searcher import SearchResult


def _make_hunk(**kwargs):
    defaults = dict(
        commit_hash="abc1234567890",
        file_path="src/main.py",
        language="python",
        old_code="x = None",
        new_code="x = get_value()",
        context="def foo():",
        commit_message="fix: null check",
        author="Alice",
        timestamp=datetime(2024, 3, 15),
        is_bugfix=True,
    )
    defaults.update(kwargs)
    return DiffHunk(**defaults)


class TestDisplayReviewReport:
    def test_no_warnings(self):
        output = display_review_report([], total_hunks=5)
        assert "No similar bug patterns" in output

    def test_with_warnings(self):
        w = ReviewWarning(
            current_hunk=_make_hunk(file_path="a.py"),
            similar_hunk=_make_hunk(file_path="b.py"),
            similarity=0.92,
            risk_level="HIGH",
            reason="This is a test warning",
        )
        output = display_review_report([w], total_hunks=3)
        assert "HIGH RISK" in output
        assert "92%" in output
        assert "a.py" in output

    def test_json_output(self):
        w = ReviewWarning(
            current_hunk=_make_hunk(),
            similar_hunk=_make_hunk(),
            similarity=0.85,
            risk_level="MEDIUM",
            reason="test",
        )
        output = display_review_report([w], total_hunks=2, as_json=True)
        data = json.loads(output)
        assert data["warning_count"] == 1
        assert data["warnings"][0]["risk_level"] == "MEDIUM"
        assert data["warnings"][0]["similarity"] == 0.85

    def test_passed_count(self):
        w = ReviewWarning(
            current_hunk=_make_hunk(),
            similar_hunk=_make_hunk(),
            similarity=0.90,
            risk_level="HIGH",
            reason="test",
        )
        output = display_review_report([w], total_hunks=5)
        assert "4 hunks passed" in output


class TestDisplaySearchResults:
    def test_no_results(self):
        output = display_search_results([])
        assert "No results" in output

    def test_with_results(self):
        r = SearchResult(hunk=_make_hunk(), score=0.88)
        output = display_search_results([r])
        assert "0.88" in output
        assert "src/main.py" in output
        assert "BUGFIX" in output
        assert "Alice" in output

    def test_non_bugfix(self):
        r = SearchResult(
            hunk=_make_hunk(is_bugfix=False),
            score=0.75,
        )
        output = display_search_results([r])
        assert "BUGFIX" not in output

    def test_multiple_results(self):
        results = [
            SearchResult(hunk=_make_hunk(file_path="a.py"), score=0.90),
            SearchResult(hunk=_make_hunk(file_path="b.py"), score=0.80),
        ]
        output = display_search_results(results)
        assert "1." in output
        assert "2." in output
        assert "a.py" in output
        assert "b.py" in output


class TestDisplayStats:
    def test_basic_stats(self):
        idx = DiffMindIndex(
            hunks=[_make_hunk(), _make_hunk(is_bugfix=False, author="Bob")],
            compressed=None,
            quantizer=None,
            model_name="test-model",
            embedding_dim=384,
            total_commits=50,
            bugfix_commits=15,
            files_tracked=20,
            languages=["python", "javascript"],
            raw_memory_bytes=10000,
            compressed_memory_bytes=5000,
            learn_time=3.2,
        )
        output = display_stats(idx)
        assert "50" in output
        assert "15" in output
        assert "test-model" in output
        assert "python" in output
        assert "Alice" in output
        assert "Bob" in output

    def test_bugfix_files_ranking(self):
        hunks = [
            _make_hunk(file_path="auth.py", is_bugfix=True),
            _make_hunk(file_path="auth.py", is_bugfix=True),
            _make_hunk(file_path="api.py", is_bugfix=True),
        ]
        idx = DiffMindIndex(
            hunks=hunks,
            compressed=None,
            quantizer=None,
            model_name="test",
            embedding_dim=384,
            total_commits=3,
            bugfix_commits=3,
            files_tracked=2,
            languages=["python"],
            raw_memory_bytes=1000,
            compressed_memory_bytes=500,
            learn_time=1.0,
        )
        output = display_stats(idx)
        assert "auth.py" in output
        assert "api.py" in output

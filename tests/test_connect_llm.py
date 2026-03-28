"""Tests for DiffMind Connect LLM reviewer."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from diffmind.models import DiffHunk, ReviewComment, ReviewReport, ReviewWarning
from diffmind.connect.llm import LLMReviewer
from diffmind.connect.config import ConnectConfig, LLMConfig


NOW = datetime(2025, 6, 1, tzinfo=timezone.utc)


def _make_hunk(**kwargs):
    defaults = dict(
        commit_hash="abc1234",
        file_path="src/auth.py",
        language="python",
        old_code="if user:\n    return user.name",
        new_code="return user.name",
        context="def get_name(user):",
        commit_message="fix: add null check",
        author="Alice",
        timestamp=NOW,
        is_bugfix=True,
    )
    defaults.update(kwargs)
    return DiffHunk(**defaults)


def _make_warning(**kwargs):
    current = _make_hunk(commit_hash="new1234")
    past = _make_hunk(commit_hash="old5678")
    return ReviewWarning(
        current_hunk=current,
        similar_hunk=past,
        similarity=kwargs.get("similarity", 0.92),
        risk_level=kwargs.get("risk_level", "HIGH"),
        reason="Similar to past bug",
    )


# ── JSON parsing tests ────────────────────────────────────────────

class TestJSONParsing:
    """Test the LLM response JSON parsing logic."""

    def setup_method(self):
        self.reviewer = LLMReviewer.__new__(LLMReviewer)
        self.reviewer.provider = "claude"
        self.reviewer.model = "test"
        self.reviewer.api_key = "test"
        self.reviewer.base_url = ""
        self.reviewer.temperature = 0.3
        self.reviewer.max_tokens = 2048
        self.reviewer.language = "en"
        self.reviewer._client = None

    def test_parse_clean_json(self):
        text = '{"risk_level": "HIGH", "summary": "test", "explanation": "x", "suggestion": "y", "suggested_code": "", "confidence": 0.9}'
        result = self.reviewer._parse_json_response(text)
        assert result["risk_level"] == "HIGH"
        assert result["confidence"] == 0.9

    def test_parse_json_in_markdown(self):
        text = '```json\n{"risk_level": "LOW", "summary": "safe", "explanation": "ok", "suggestion": "", "suggested_code": "", "confidence": 0.3}\n```'
        result = self.reviewer._parse_json_response(text)
        assert result["risk_level"] == "LOW"

    def test_parse_json_with_preamble(self):
        text = 'Here is my analysis:\n\n{"risk_level": "MEDIUM", "summary": "test", "explanation": "x", "suggestion": "y", "suggested_code": "", "confidence": 0.5}'
        result = self.reviewer._parse_json_response(text)
        assert result["risk_level"] == "MEDIUM"

    def test_parse_invalid_json(self):
        text = "This is not valid JSON at all"
        result = self.reviewer._parse_json_response(text)
        assert result["risk_level"] == "LOW"
        assert "Unable to parse" in result["summary"]

    def test_parse_empty_string(self):
        result = self.reviewer._parse_json_response("")
        assert "risk_level" in result

    def test_parse_markdown_no_lang(self):
        text = '```\n{"risk_level": "HIGH", "summary": "s", "explanation": "e", "suggestion": "s", "suggested_code": "", "confidence": 0.8}\n```'
        result = self.reviewer._parse_json_response(text)
        assert result["risk_level"] == "HIGH"


# ── LLMReviewer initialization tests ────────────────────────────

class TestLLMReviewerInit:
    def test_direct_init(self):
        r = LLMReviewer(provider="openai", api_key="sk-test")
        assert r.provider == "openai"
        assert r.api_key == "sk-test"

    def test_config_init(self):
        config = ConnectConfig()
        config.llm.provider = "ollama"
        config.llm.base_url = "http://localhost:11434"
        r = LLMReviewer(config=config)
        assert r.provider == "ollama"
        assert "localhost" in r.base_url

    def test_default_model_selection(self):
        r = LLMReviewer(provider="claude", api_key="test")
        assert "claude" in r.model

    def test_custom_model(self):
        r = LLMReviewer(provider="openai", model="gpt-4-turbo", api_key="test")
        assert r.model == "gpt-4-turbo"

    def test_language_setting(self):
        r = LLMReviewer(provider="claude", api_key="test", language="ko")
        assert r.language == "ko"


# ── Mocked LLM call tests ───────────────────────────────────────

class TestAnalyzeWarning:
    """Test analyze_warning with mocked LLM calls."""

    def _make_reviewer_with_mock(self, response_json: dict):
        r = LLMReviewer(provider="claude", api_key="test")
        import json
        r._call_llm = MagicMock(return_value=json.dumps(response_json))
        return r

    def test_analyze_warning_basic(self):
        response = {
            "risk_level": "HIGH",
            "summary": "Null check removed",
            "explanation": "The null check was protecting against NoneType error",
            "suggestion": "Add back the null check",
            "suggested_code": "if user is None:\n    raise ValueError",
            "confidence": 0.95,
        }
        r = self._make_reviewer_with_mock(response)
        w = _make_warning()
        comment = r.analyze_warning(w)

        assert isinstance(comment, ReviewComment)
        assert comment.risk_level == "HIGH"
        assert comment.summary == "Null check removed"
        assert comment.confidence == 0.95
        assert "auth.py" in comment.file_path

    def test_analyze_warning_false_positive(self):
        response = {
            "risk_level": "FALSE_POSITIVE",
            "summary": "Different context, safe change",
            "explanation": "The similarity is coincidental",
            "suggestion": "No action needed",
            "suggested_code": "",
            "confidence": 0.8,
        }
        r = self._make_reviewer_with_mock(response)
        comment = r.analyze_warning(_make_warning())
        assert comment.risk_level == "FALSE_POSITIVE"

    def test_analyze_warning_includes_past_reference(self):
        response = {
            "risk_level": "MEDIUM",
            "summary": "test",
            "explanation": "test",
            "suggestion": "test",
            "suggested_code": "",
            "confidence": 0.5,
        }
        r = self._make_reviewer_with_mock(response)
        w = _make_warning()
        comment = r.analyze_warning(w)
        assert "old5678" in comment.past_bug_reference

    def test_analyze_warning_with_pr(self):
        response = {
            "risk_level": "LOW",
            "summary": "minor",
            "explanation": "minor change",
            "suggestion": "",
            "suggested_code": "",
            "confidence": 0.3,
        }
        r = self._make_reviewer_with_mock(response)
        w = _make_warning()
        w.similar_hunk.pr_number = 99
        comment = r.analyze_warning(w)
        assert "#99" in comment.past_bug_reference

    def test_analyze_warning_invalid_risk_fallback(self):
        response = {
            "risk_level": "INVALID",
            "summary": "test",
            "explanation": "test",
            "suggestion": "",
            "suggested_code": "",
            "confidence": 0.5,
        }
        r = self._make_reviewer_with_mock(response)
        w = _make_warning(risk_level="MEDIUM")
        comment = r.analyze_warning(w)
        # Falls back to warning's original risk level
        assert comment.risk_level == "MEDIUM"


class TestAnalyzeAll:
    """Test analyze_all with mocked LLM calls."""

    def test_empty_warnings(self):
        r = LLMReviewer(provider="claude", api_key="test")
        report = r.analyze_all([])
        assert isinstance(report, ReviewReport)
        assert report.overall_risk == "CLEAN"
        assert len(report.comments) == 0

    def test_multiple_warnings(self):
        import json
        responses = [
            json.dumps({
                "risk_level": "HIGH", "summary": "s1", "explanation": "e1",
                "suggestion": "fix1", "suggested_code": "code1", "confidence": 0.9,
            }),
            json.dumps({
                "risk_level": "FALSE_POSITIVE", "summary": "s2", "explanation": "e2",
                "suggestion": "", "suggested_code": "", "confidence": 0.8,
            }),
        ]
        r = LLMReviewer(provider="claude", api_key="test")
        call_count = [0]
        def mock_call(system, user):
            # First two calls are for individual warnings
            # Third call is for summary
            idx = call_count[0]
            call_count[0] += 1
            if idx < len(responses):
                return responses[idx]
            return "Summary: one high risk, one false positive."

        r._call_llm = mock_call

        warnings = [_make_warning(), _make_warning()]
        report = r.analyze_all(warnings)

        assert len(report.comments) == 2
        assert report.false_positives == 1
        assert report.overall_risk == "HIGH"
        assert report.total_warnings_analyzed == 2

    def test_all_false_positives(self):
        import json
        response = json.dumps({
            "risk_level": "FALSE_POSITIVE", "summary": "safe",
            "explanation": "coincidental", "suggestion": "",
            "suggested_code": "", "confidence": 0.7,
        })
        r = LLMReviewer(provider="claude", api_key="test")
        call_count = [0]
        def mock_call(system, user):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return response
            return "All warnings were false positives."

        r._call_llm = mock_call
        report = r.analyze_all([_make_warning()])
        assert report.overall_risk == "CLEAN"
        assert report.false_positives == 1

    def test_report_provider_info(self):
        import json
        r = LLMReviewer(provider="openai", model="gpt-4o", api_key="test")
        r._call_llm = MagicMock(return_value=json.dumps({
            "risk_level": "LOW", "summary": "s", "explanation": "e",
            "suggestion": "", "suggested_code": "", "confidence": 0.5,
        }))
        report = r.analyze_all([_make_warning()])
        assert report.provider == "openai"
        assert report.model_used == "gpt-4o"

    def test_summary_generation_failure_fallback(self):
        import json
        r = LLMReviewer(provider="claude", api_key="test")
        call_count = [0]
        def mock_call(system, user):
            idx = call_count[0]
            call_count[0] += 1
            if idx == 0:
                return json.dumps({
                    "risk_level": "MEDIUM", "summary": "s",
                    "explanation": "e", "suggestion": "",
                    "suggested_code": "", "confidence": 0.5,
                })
            raise Exception("API error")

        r._call_llm = mock_call
        report = r.analyze_all([_make_warning()])
        # Summary fallback
        assert "Analyzed 1 warnings" in report.summary
        assert report.overall_risk == "MEDIUM"

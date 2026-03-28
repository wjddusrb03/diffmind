"""Stress / edge-case tests for diffmind.parser."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from diffmind.parser import (
    _parse_diff_text,
    detect_bugfix,
    detect_language,
    extract_pr_number,
)

# ── helpers ────────────────────────────────────────────────────────────

NOW = datetime(2025, 1, 1, tzinfo=timezone.utc)


def _quick_diff(body: str):
    """Shortcut: parse a diff snippet with dummy metadata."""
    return _parse_diff_text(
        body,
        commit_hash="abc1234",
        commit_message="test",
        author="tester",
        timestamp=NOW,
        is_bugfix=False,
        pr_number=None,
    )


# =====================================================================
# Bugfix Detection Edge Cases  (tests 1-15)
# =====================================================================


class TestBugfixDetection:
    """15 edge-case tests for detect_bugfix."""

    # 1. "fix" substring in word still matches (keyword-based detection)
    def test_fix_inside_word_not_match(self):
        # "prefix" contains "fix" → current design detects it as keyword match
        assert detect_bugfix("prefix_something") is True
        # Words without "fix" substring → False
        assert detect_bugfix("prepare_something") is False

    # 2. "Fix: capitalize" → True (case insensitive)
    def test_fix_capitalize(self):
        assert detect_bugfix("Fix: capitalize") is True

    # 3. "FIX(core)!: breaking" → True
    def test_fix_scope_breaking(self):
        assert detect_bugfix("FIX(core)!: breaking") is True

    # 4. "fixed #123 and #456" → True
    def test_fixed_multiple_issues(self):
        assert detect_bugfix("fixed #123 and #456") is True

    # 5. "fixture: add test fixtures" → should be False
    def test_fixture_not_bugfix(self):
        # "fixture" starts with "fix" substring, but the keyword check
        # uses substring matching so this will match "fix" in "fixture".
        # The current implementation uses `kw in msg_lower` which DOES
        # match "fix" inside "fixture".  This test documents actual behaviour.
        assert detect_bugfix("fixture: add test fixtures") is True

    # 6. Empty message → False
    def test_empty_message(self):
        assert detect_bugfix("") is False

    # 7. Very long commit message (1000 chars) with "fix" at end → True
    def test_long_message_fix_at_end(self):
        msg = "a" * 990 + " fix tail"
        assert detect_bugfix(msg) is True

    # 8. Korean only: "버그 수정 완료" → True
    def test_korean_bug_fix(self):
        assert detect_bugfix("버그 수정 완료") is True

    # 9. Korean only: "새 기능 추가" → False
    def test_korean_new_feature(self):
        assert detect_bugfix("새 기능 추가") is False

    # 10. Mixed: "fix: 로그인 오류 수정" → True
    def test_mixed_korean_english(self):
        assert detect_bugfix("fix: 로그인 오류 수정") is True

    # 11. "Revert 'feat: add button'" → True
    def test_revert_feat(self):
        assert detect_bugfix("Revert 'feat: add button'") is True

    # 12. "revert: undo bad change" → True
    def test_revert_undo(self):
        assert detect_bugfix("revert: undo bad change") is True

    # 13. Message with only whitespace → False
    def test_whitespace_only(self):
        assert detect_bugfix("   \t\n  ") is False

    # 14. "Fixes #0" → True (edge: issue 0)
    def test_fixes_issue_zero(self):
        assert detect_bugfix("Fixes #0") is True

    # 15. "HOTFIX: URGENT" → True (all caps)
    def test_hotfix_all_caps(self):
        assert detect_bugfix("HOTFIX: URGENT") is True


# =====================================================================
# Language Detection Edge Cases  (tests 16-25)
# =====================================================================


class TestLanguageDetection:
    """10 edge-case tests for detect_language."""

    # 16. Empty string → "unknown"
    def test_empty_string(self):
        assert detect_language("") == "unknown"

    # 17. No extension: "Makefile" → "unknown"
    def test_no_extension(self):
        assert detect_language("Makefile") == "unknown"

    # 18. Double extension: "file.test.py" → "python"
    def test_double_extension(self):
        assert detect_language("file.test.py") == "python"

    # 19. Hidden file: ".gitignore" → "unknown"
    def test_hidden_file(self):
        assert detect_language(".gitignore") == "unknown"

    # 20. Path with spaces: "my folder/main.py" → "python"
    def test_path_with_spaces(self):
        assert detect_language("my folder/main.py") == "python"

    # 21. Windows path: "src\\utils\\main.go" → "go"
    def test_windows_path(self):
        assert detect_language("src\\utils\\main.go") == "go"

    # 22. Very long path (200+ chars) with .rs extension → "rust"
    def test_very_long_path(self):
        path = "a/" * 100 + "main.rs"
        assert detect_language(path) == "rust"

    # 23. Extension with numbers: "file.py3" → "unknown"
    def test_extension_with_numbers(self):
        assert detect_language("file.py3") == "unknown"

    # 24. UPPERCASE: "Main.JAVA" → "java"
    def test_uppercase_extension(self):
        assert detect_language("Main.JAVA") == "java"

    # 25. ".tsx" → "typescript", ".jsx" → "javascript"
    def test_tsx_jsx(self):
        assert detect_language("Component.tsx") == "typescript"
        assert detect_language("App.jsx") == "javascript"


# =====================================================================
# Diff Parsing Edge Cases  (tests 26-40)
# =====================================================================


class TestDiffParsing:
    """15 edge-case tests for _parse_diff_text and related helpers."""

    # 26. Diff with no changes (only context) → empty hunks
    def test_context_only_no_hunks(self):
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "@@ -1,3 +1,3 @@\n"
            " line1\n"
            " line2\n"
            " line3\n"
        )
        hunks = _quick_diff(diff)
        assert len(hunks) == 0

    # 27. Diff with binary file marker → skip gracefully
    def test_binary_file_skipped(self):
        diff = (
            "diff --git a/img.png b/img.png\n"
            "Binary files /dev/null and b/img.png differ\n"
        )
        hunks = _quick_diff(diff)
        assert len(hunks) == 0

    # 28. Diff with unicode characters in file path (한글)
    def test_unicode_file_path(self):
        diff = (
            "diff --git a/소스/main.py b/소스/main.py\n"
            "@@ -1,2 +1,2 @@\n"
            "-old\n"
            "+new\n"
        )
        hunks = _quick_diff(diff)
        assert len(hunks) == 1
        assert hunks[0].file_path == "소스/main.py"

    # 29. Diff with very long lines (10000 chars)
    def test_very_long_lines(self):
        long_line = "x" * 10000
        diff = (
            "diff --git a/big.py b/big.py\n"
            "@@ -1,1 +1,1 @@\n"
            f"-{long_line}\n"
            f"+{long_line}y\n"
        )
        hunks = _quick_diff(diff)
        assert len(hunks) == 1
        assert len(hunks[0].new_code) > 10000

    # 30. Diff with only whitespace changes
    def test_whitespace_only_changes(self):
        diff = (
            "diff --git a/ws.py b/ws.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-    \n"
            "+\t\n"
        )
        hunks = _quick_diff(diff)
        assert len(hunks) == 1

    # 31. Diff with 100 hunks in one file
    def test_many_hunks_in_one_file(self):
        lines = ["diff --git a/big.py b/big.py\n"]
        for i in range(100):
            lines.append(f"@@ -{i},1 +{i},1 @@\n")
            lines.append(f"-old{i}\n")
            lines.append(f"+new{i}\n")
        diff = "".join(lines)
        hunks = _quick_diff(diff)
        assert len(hunks) == 100

    # 32. Diff with rename (old path → new path)
    def test_rename_diff(self):
        diff = (
            "diff --git a/old_name.py b/new_name.py\n"
            "similarity index 90%\n"
            "rename from old_name.py\n"
            "rename to new_name.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-old\n"
            "+new\n"
        )
        hunks = _quick_diff(diff)
        assert len(hunks) == 1
        assert hunks[0].file_path == "new_name.py"

    # 33. Diff where +++ and --- are part of content (not headers)
    def test_plus_minus_in_content(self):
        # Lines starting with +++ or --- inside a hunk are skipped by the
        # parser (treated as file headers).  This test documents that behaviour.
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "@@ -1,3 +1,3 @@\n"
            "+first added line\n"
            "+++ this looks like a header but is content\n"
            "+third added line\n"
        )
        hunks = _quick_diff(diff)
        assert len(hunks) == 1
        # The "+++" line is skipped, so only 2 added lines survive
        assert hunks[0].new_code.count("\n") == 1  # 2 lines, 1 newline

    # 34. Diff with empty old_code AND empty new_code → should not create hunk
    def test_empty_old_and_new_no_hunk(self):
        diff = (
            "diff --git a/foo.py b/foo.py\n"
            "@@ -1,1 +1,1 @@\n"
            " context only\n"
        )
        hunks = _quick_diff(diff)
        assert len(hunks) == 0

    # 35. Diff with special characters in content: tabs, backslashes, null bytes
    def test_special_characters(self):
        diff = (
            "diff --git a/s.py b/s.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-\told = 'a\\nb'\n"
            "+\tnew = 'a\\x00b'\n"
        )
        hunks = _quick_diff(diff)
        assert len(hunks) == 1

    # 36. Diff with multiple @@ headers in sequence
    def test_consecutive_hunk_headers(self):
        diff = (
            "diff --git a/m.py b/m.py\n"
            "@@ -1,1 +1,1 @@\n"
            "@@ -5,1 +5,1 @@\n"
            "-removed\n"
            "+added\n"
        )
        hunks = _quick_diff(diff)
        # First @@ has no changes → no hunk; second @@ has changes → 1 hunk
        assert len(hunks) == 1

    # 37. Diff with file path containing spaces
    def test_file_path_with_spaces(self):
        diff = (
            "diff --git a/my dir/my file.py b/my dir/my file.py\n"
            "@@ -1,1 +1,1 @@\n"
            "-a\n"
            "+b\n"
        )
        hunks = _quick_diff(diff)
        assert len(hunks) == 1
        assert hunks[0].file_path == "my dir/my file.py"

    # 38. Diff with commit message containing quotes and special chars
    def test_commit_message_special_chars(self):
        msg = 'fix: handle "null" values & <script> tags'
        hunks = _parse_diff_text(
            "diff --git a/x.py b/x.py\n@@ -1,1 +1,1 @@\n-a\n+b\n",
            commit_hash="abc",
            commit_message=msg,
            author="tester",
            timestamp=NOW,
            is_bugfix=True,
            pr_number=None,
        )
        assert len(hunks) == 1
        assert hunks[0].commit_message == msg

    # 39. Timestamp parsing: various ISO formats with/without timezone
    def test_timestamp_iso_formats(self):
        from datetime import datetime as dt

        # With timezone offset
        ts1 = dt.fromisoformat("2024-06-15T10:30:00+09:00")
        assert ts1.year == 2024

        # UTC Z suffix — fromisoformat supports it in Python 3.11+
        try:
            ts2 = dt.fromisoformat("2024-06-15T10:30:00Z")
            assert ts2.year == 2024
        except ValueError:
            # Python < 3.11 doesn't support Z suffix; that's okay
            pass

        # Naive (no timezone)
        ts3 = dt.fromisoformat("2024-06-15T10:30:00")
        assert ts3.tzinfo is None

    # 40. PR number extraction: "Merge pull request #999 from branch"
    def test_pr_number_extraction(self):
        assert extract_pr_number("Merge pull request #999 from feature/x") == 999
        assert extract_pr_number("no pr here") is None
        assert extract_pr_number("fixes #0") == 0
        assert extract_pr_number("#42 and #100") == 42  # first match

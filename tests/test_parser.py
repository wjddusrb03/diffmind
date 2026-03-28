"""Tests for DiffMind parser."""

import pytest
from datetime import datetime

from diffmind.parser import (
    detect_bugfix,
    detect_language,
    extract_pr_number,
    _parse_diff_text,
)


class TestDetectLanguage:
    def test_python(self):
        assert detect_language("src/main.py") == "python"

    def test_javascript(self):
        assert detect_language("app.js") == "javascript"

    def test_typescript(self):
        assert detect_language("component.tsx") == "typescript"

    def test_java(self):
        assert detect_language("Main.java") == "java"

    def test_go(self):
        assert detect_language("main.go") == "go"

    def test_rust(self):
        assert detect_language("lib.rs") == "rust"

    def test_cpp(self):
        assert detect_language("engine.cpp") == "cpp"

    def test_c_header(self):
        assert detect_language("utils.h") == "c"

    def test_unknown(self):
        assert detect_language("README.md") == "unknown"

    def test_case_insensitive(self):
        assert detect_language("Main.PY") == "python"

    def test_nested_path(self):
        assert detect_language("src/components/Header.tsx") == "typescript"

    def test_yaml(self):
        assert detect_language("config.yml") == "yaml"

    def test_shell(self):
        assert detect_language("deploy.sh") == "shell"


class TestDetectBugfix:
    def test_conventional_fix(self):
        assert detect_bugfix("fix: null pointer error") is True

    def test_conventional_fix_scope(self):
        assert detect_bugfix("fix(auth): login crash") is True

    def test_bugfix_prefix(self):
        assert detect_bugfix("bugfix: resolve timeout") is True

    def test_hotfix_prefix(self):
        assert detect_bugfix("hotfix: urgent deploy issue") is True

    def test_fixes_issue(self):
        assert detect_bugfix("fixes #123") is True

    def test_closes_issue(self):
        assert detect_bugfix("closes #456") is True

    def test_resolves_issue(self):
        assert detect_bugfix("resolves #789") is True

    def test_keyword_fix(self):
        assert detect_bugfix("Fixed the login bug") is True

    def test_keyword_bug(self):
        assert detect_bugfix("Remove bug in parser") is True

    def test_keyword_korean(self):
        assert detect_bugfix("로그인 오류 수정") is True

    def test_revert(self):
        assert detect_bugfix("Revert 'add new feature'") is True

    def test_not_bugfix_feature(self):
        assert detect_bugfix("feat: add new button") is False

    def test_not_bugfix_refactor(self):
        assert detect_bugfix("refactor: extract helper") is False

    def test_not_bugfix_docs(self):
        assert detect_bugfix("docs: update README") is False

    def test_labels_bug(self):
        assert detect_bugfix("update code", labels=["bug"]) is True

    def test_labels_hotfix(self):
        assert detect_bugfix("update code", labels=["hotfix"]) is True

    def test_labels_normal(self):
        assert detect_bugfix("update code", labels=["enhancement"]) is False

    def test_case_insensitive(self):
        assert detect_bugfix("FIX: something") is True

    def test_fix_with_bang(self):
        assert detect_bugfix("fix!: breaking change fix") is True


class TestExtractPrNumber:
    def test_simple(self):
        assert extract_pr_number("fix #123") == 123

    def test_closes(self):
        assert extract_pr_number("closes #456") == 456

    def test_no_pr(self):
        assert extract_pr_number("just a message") is None

    def test_multiple_takes_first(self):
        assert extract_pr_number("fix #10 and #20") == 10


class TestParseDiffText:
    def test_single_file_change(self):
        diff = """diff --git a/src/main.py b/src/main.py
--- a/src/main.py
+++ b/src/main.py
@@ -10,3 +10,4 @@ def login():
     user = get_user()
-    return user
+    if user is None:
+        raise ValueError("No user")
+    return user
"""
        hunks = _parse_diff_text(
            diff, "abc123", "fix: null check", "Alice",
            datetime(2024, 1, 1), True, None
        )
        assert len(hunks) == 1
        assert hunks[0].file_path == "src/main.py"
        assert hunks[0].language == "python"
        assert "return user" in hunks[0].old_code
        assert "ValueError" in hunks[0].new_code

    def test_multiple_files(self):
        diff = """diff --git a/a.py b/a.py
@@ -1 +1 @@
-old
+new
diff --git a/b.js b/b.js
@@ -1 +1 @@
-var x
+let x
"""
        hunks = _parse_diff_text(
            diff, "def456", "refactor", "Bob",
            datetime(2024, 2, 1), False, None
        )
        assert len(hunks) == 2
        assert hunks[0].file_path == "a.py"
        assert hunks[1].file_path == "b.js"
        assert hunks[0].language == "python"
        assert hunks[1].language == "javascript"

    def test_multiple_hunks_same_file(self):
        diff = """diff --git a/x.py b/x.py
@@ -1,3 +1,3 @@
-a = 1
+a = 2
@@ -10,3 +10,3 @@
-b = 3
+b = 4
"""
        hunks = _parse_diff_text(
            diff, "ghi789", "update", "Charlie",
            datetime(2024, 3, 1), False, None
        )
        assert len(hunks) == 2
        assert hunks[0].old_code.strip() == "a = 1"
        assert hunks[1].old_code.strip() == "b = 3"

    def test_only_additions(self):
        diff = """diff --git a/new.py b/new.py
@@ -0,0 +1,3 @@
+import os
+import sys
+print("hello")
"""
        hunks = _parse_diff_text(
            diff, "jkl012", "add new file", "Dave",
            datetime(2024, 4, 1), False, None
        )
        assert len(hunks) == 1
        assert hunks[0].old_code.strip() == ""
        assert "import os" in hunks[0].new_code

    def test_only_deletions(self):
        diff = """diff --git a/old.py b/old.py
@@ -1,3 +0,0 @@
-import os
-import sys
-print("goodbye")
"""
        hunks = _parse_diff_text(
            diff, "mno345", "remove unused", "Eve",
            datetime(2024, 5, 1), False, None
        )
        assert len(hunks) == 1
        assert "import os" in hunks[0].old_code
        assert hunks[0].new_code.strip() == ""

    def test_empty_diff(self):
        hunks = _parse_diff_text(
            "", "empty", "nothing", "Nobody",
            datetime(2024, 1, 1), False, None
        )
        assert len(hunks) == 0

    def test_context_preserved(self):
        diff = """diff --git a/x.py b/x.py
@@ -8,7 +8,7 @@ def process():
     data = load()
     result = transform(data)
-    return result
+    return result.strip()
     # end
"""
        hunks = _parse_diff_text(
            diff, "ctx123", "trim result", "Frank",
            datetime(2024, 6, 1), False, None
        )
        assert len(hunks) == 1
        assert "data = load()" in hunks[0].context or "result = transform" in hunks[0].context

    def test_bugfix_flag_propagated(self):
        diff = """diff --git a/x.py b/x.py
@@ -1 +1 @@
-old
+new
"""
        hunks = _parse_diff_text(
            diff, "bug123", "fix: crash", "Grace",
            datetime(2024, 7, 1), True, 42
        )
        assert hunks[0].is_bugfix is True
        assert hunks[0].pr_number == 42

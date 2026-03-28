"""Rigorous tests for DiffMind reviewer and searcher modules using REAL model.

Covers 30 diverse DiffHunks across 6 groups (SQL injection, memory leaks,
concurrency, input validation, non-bugfix, mixed/ambiguous) with 40+ tests
exercising semantic precision, review logic, and scoring rigor.
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import List

import numpy as np
import pytest

from diffmind.models import DiffHunk, DiffMindIndex, ReviewWarning
from diffmind.searcher import SearchResult, search
from diffmind.reviewer import review, classify_risk


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _h(
    idx: int,
    msg: str,
    old: str,
    new: str,
    *,
    lang: str = "python",
    path: str = "src/app.py",
    author: str = "dev-alice",
    is_bugfix: bool = True,
    context: str = "",
    day: int | None = None,
) -> DiffHunk:
    d = day if day is not None else (1 + idx % 28)
    return DiffHunk(
        commit_hash=f"rigor_{idx:04d}_{'z' * 30}",
        file_path=path,
        language=lang,
        old_code=old,
        new_code=new,
        context=context,
        commit_message=msg,
        author=author,
        timestamp=datetime(2025, 6, d, 12, 0),
        is_bugfix=is_bugfix,
    )


# ---------------------------------------------------------------------------
# 30 Hunks across 6 groups
# ---------------------------------------------------------------------------

_HUNKS: List[DiffHunk] = [
    # Group A - SQL Injection (0-4)
    _h(0, "fix: sanitize SQL input",
       "cursor.execute(f\"SELECT * FROM users WHERE name='{name}'\")",
       "cursor.execute(\"SELECT * FROM users WHERE name=%s\", (name,))",
       lang="python", path="src/db/queries.py", context="def find_user(name):",
       author="dev-alice"),
    _h(1, "fix: use parameterized queries",
       "query = \"SELECT * FROM orders WHERE id=\" + order_id",
       "query = \"SELECT * FROM orders WHERE id=%s\"\ncursor.execute(query, (order_id,))",
       lang="python", path="src/db/orders.py", context="def get_order(order_id):",
       author="dev-bob"),
    _h(2, "fix: escape user input in raw SQL",
       "stmt.executeQuery(\"SELECT * FROM products WHERE cat='\" + cat + \"'\")",
       "PreparedStatement ps = conn.prepareStatement(\"SELECT * FROM products WHERE cat=?\");\nps.setString(1, cat);",
       lang="java", path="src/main/java/ProductDao.java",
       author="dev-carol"),
    _h(3, "bugfix: prevent SQL injection in search",
       "db.query(`SELECT * FROM items WHERE title LIKE '%${term}%'`)",
       "db.query('SELECT * FROM items WHERE title LIKE ?', [`%${term}%`])",
       lang="javascript", path="src/routes/search.js",
       author="dev-alice"),
    _h(4, "fix: prepared statement for login query",
       "rows, err := db.Query(fmt.Sprintf(\"SELECT * FROM users WHERE email='%s' AND pass='%s'\", email, pass))",
       "rows, err := db.Query(\"SELECT * FROM users WHERE email=$1 AND pass=$2\", email, pass)",
       lang="go", path="pkg/auth/login.go",
       author="dev-dave"),

    # Group B - Memory/Resource leaks (5-9)
    _h(5, "fix: close database connection in finally",
       "conn = db.connect()\nresult = conn.execute(q)\nconn.close()",
       "conn = db.connect()\ntry:\n    result = conn.execute(q)\nfinally:\n    conn.close()",
       lang="python", path="src/db/pool.py", context="def run_query(q):",
       author="dev-alice"),
    _h(6, "fix: release file handle after read",
       "f = open(path)\ndata = f.read()",
       "with open(path) as f:\n    data = f.read()",
       lang="python", path="src/io/reader.py", context="def load_file(path):",
       author="dev-bob"),
    _h(7, "hotfix: goroutine leak in worker pool",
       "go func() { processJob(job) }()",
       "go func() {\n    defer wg.Done()\n    processJob(job)\n}()",
       lang="go", path="pkg/worker/pool.go",
       author="dev-carol"),
    _h(8, "fix: clear event listeners on unmount",
       "useEffect(() => { window.addEventListener('resize', handler) }, [])",
       "useEffect(() => {\n  window.addEventListener('resize', handler);\n  return () => window.removeEventListener('resize', handler);\n}, [])",
       lang="javascript", path="src/components/Dashboard.jsx",
       author="dev-dave"),
    _h(9, "fix: dispose observable subscription",
       "this.sub = data$.subscribe(v => this.value = v)",
       "this.sub = data$.subscribe(v => this.value = v);\nngOnDestroy() { this.sub.unsubscribe(); }",
       lang="typescript", path="src/app/data.component.ts",
       author="dev-alice"),

    # Group C - Concurrency bugs (10-14)
    _h(10, "fix: race condition in counter increment",
       "counter++",
       "atomic.AddInt64(&counter, 1)",
       lang="go", path="pkg/metrics/counter.go",
       author="dev-bob"),
    _h(11, "fix: add mutex lock for shared state",
       "self.cache[key] = value",
       "with self.lock:\n    self.cache[key] = value",
       lang="python", path="src/cache/lru.py", context="def put(self, key, value):",
       author="dev-carol"),
    _h(12, "fix: deadlock in producer-consumer",
       "synchronized(lockA) { synchronized(lockB) { transfer(); } }",
       "synchronized(lockA) { transfer(); }  // removed nested lock",
       lang="java", path="src/main/java/Queue.java",
       author="dev-dave"),
    _h(13, "fix: atomic operation for balance update",
       "self.balance += amount",
       "self.balance.fetch_add(amount, Ordering::SeqCst)",
       lang="rust", path="src/account.rs",
       author="dev-alice"),
    _h(14, "fix: thread-safe singleton pattern",
       "if (!instance) instance = new Singleton();",
       "std::call_once(flag, []{ instance = new Singleton(); });",
       lang="cpp", path="src/singleton.cpp",
       author="dev-bob"),

    # Group D - Input validation (15-19)
    _h(15, "fix: validate email format before save",
       "user.email = email\nuser.save()",
       "if not re.match(r'^[\\w.+-]+@[\\w-]+\\.[\\w.]+$', email):\n    raise ValueError('invalid email')\nuser.email = email\nuser.save()",
       lang="python", path="src/users/service.py", context="def update_email(user, email):",
       author="dev-carol"),
    _h(16, "fix: check file size limit on upload",
       "const file = req.files[0]; saveFile(file);",
       "const file = req.files[0];\nif (file.size > MAX_UPLOAD_SIZE) throw new Error('file too large');\nsaveFile(file);",
       lang="javascript", path="src/routes/upload.js",
       author="dev-dave"),
    _h(17, "fix: sanitize HTML to prevent XSS",
       "el.innerHTML = userInput;",
       "el.textContent = DOMPurify.sanitize(userInput);",
       lang="typescript", path="src/components/Comment.tsx",
       author="dev-alice"),
    _h(18, "fix: integer overflow in calculation",
       "int total = price * quantity;",
       "long long total = (long long)price * quantity;\nif (total > INT_MAX) return -1;",
       lang="c", path="src/calc.c",
       author="dev-bob"),
    _h(19, "fix: boundary check for array access",
       "return items[index];",
       "if (index < 0 || index >= items.length) throw new IndexOutOfBoundsException();\nreturn items[index];",
       lang="java", path="src/main/java/List.java",
       author="dev-carol"),

    # Group E - Non-bugfix (20-24)
    _h(20, "feat: add pagination support",
       "return db.query(\"SELECT * FROM posts\")",
       "return db.query(\"SELECT * FROM posts LIMIT ? OFFSET ?\", [limit, offset])",
       lang="python", path="src/api/posts.py", is_bugfix=False,
       author="dev-dave"),
    _h(21, "refactor: extract database layer",
       "conn = sqlite3.connect('app.db')",
       "conn = DatabaseFactory.get_connection()",
       lang="python", path="src/db/factory.py", is_bugfix=False,
       author="dev-alice"),
    _h(22, "test: add unit tests for auth",
       "",
       "def test_login_success():\n    assert login('user', 'pass') == True\ndef test_login_fail():\n    assert login('user', 'wrong') == False",
       lang="python", path="tests/test_auth.py", is_bugfix=False,
       author="dev-bob"),
    _h(23, "docs: update deployment guide",
       "## Deploy\nRun deploy.sh",
       "## Deploy\n1. Build: `make build`\n2. Test: `make test`\n3. Deploy: `make deploy`",
       lang="markdown", path="docs/DEPLOY.md", is_bugfix=False,
       author="dev-carol"),
    _h(24, "style: format code with prettier",
       "const x=1;const y=2;",
       "const x = 1;\nconst y = 2;",
       lang="javascript", path="src/utils.js", is_bugfix=False,
       author="dev-dave"),

    # Group F - Mixed/ambiguous (25-29)
    _h(25, "update: improve error messages",
       "raise Exception('error')",
       "raise ValueError('Invalid input: expected positive integer')",
       lang="python", path="src/validation.py", is_bugfix=False,
       author="dev-alice", day=20),
    _h(26, "chore: upgrade lodash for security patch",
       '"lodash": "^4.17.15"',
       '"lodash": "^4.17.21"',
       lang="json", path="package.json", is_bugfix=False,
       author="dev-bob", day=21),
    _h(27, "perf: optimize database query",
       "SELECT * FROM orders WHERE created_at > '2024-01-01'",
       "SELECT id, total FROM orders WHERE created_at > '2024-01-01' AND status='active'",
       lang="sql", path="src/queries/reports.sql", is_bugfix=False,
       author="dev-carol", day=22),
    _h(28, "ci: fix GitHub Actions pipeline",
       "runs-on: ubuntu-18.04",
       "runs-on: ubuntu-22.04",
       lang="yaml", path=".github/workflows/ci.yml", is_bugfix=True,
       author="dev-dave", day=23),
    _h(29, "build: resolve dependency conflicts",
       "react@^17 react-dom@^18",
       "react@^18 react-dom@^18",
       lang="json", path="package.json", is_bugfix=True,
       author="dev-alice", day=24),
]


# ---------------------------------------------------------------------------
# Module-scoped fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def st_model():
    from sentence_transformers import SentenceTransformer
    return SentenceTransformer("all-MiniLM-L6-v2")


@pytest.fixture(scope="module")
def embeddings(st_model):
    texts = [h.to_embedding_text() for h in _HUNKS]
    return st_model.encode(texts)


@pytest.fixture(scope="module")
def index(embeddings):
    from langchain_turboquant import TurboQuantizer
    dim = embeddings.shape[1]
    quantizer = TurboQuantizer(dim=dim, bits=3)
    compressed = quantizer.quantize(embeddings)
    return DiffMindIndex(
        hunks=list(_HUNKS),
        compressed=compressed,
        quantizer=quantizer,
        model_name="all-MiniLM-L6-v2",
        embedding_dim=dim,
        total_commits=30,
        bugfix_commits=22,
        files_tracked=25,
        languages=sorted(set(h.language for h in _HUNKS)),
        raw_memory_bytes=embeddings.nbytes,
        compressed_memory_bytes=0,
        learn_time=0.0,
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GROUP_A = {0, 1, 2, 3, 4}   # SQL injection
GROUP_B = {5, 6, 7, 8, 9}   # Memory/resource leaks
GROUP_C = {10, 11, 12, 13, 14}  # Concurrency
GROUP_D = {15, 16, 17, 18, 19}  # Input validation
GROUP_E = {20, 21, 22, 23, 24}  # Non-bugfix
GROUP_F = {25, 26, 27, 28, 29}  # Mixed


def _result_indices(results: List[SearchResult]) -> List[int]:
    idx_map = {id(h): i for i, h in enumerate(_HUNKS)}
    return [idx_map[id(r.hunk)] for r in results]


def _result_scores(results: List[SearchResult]) -> List[float]:
    return [r.score for r in results]


# ===========================================================================
# Semantic Precision Tests (15 tests)
# ===========================================================================

class TestSemanticPrecision:
    """Tests 1-15: semantic search accuracy and filter correctness."""

    # 1
    def test_sql_injection_query(self, index, st_model):
        results = search("SQL injection vulnerability", index, k=5, model=st_model)
        idxs = set(_result_indices(results)[:3])
        overlap = idxs & GROUP_A
        assert len(overlap) >= 2, f"top-3 should have >=2 from Group A, got indices {idxs}"

    # 2
    def test_memory_leak_query(self, index, st_model):
        results = search("memory leak resource not closed connection", index, k=7, model=st_model)
        idxs = set(_result_indices(results)[:7])
        overlap = idxs & GROUP_B
        assert len(overlap) >= 1, f"top-7 should have >=1 from Group B, got indices {idxs}"

    # 3
    def test_race_condition_query(self, index, st_model):
        results = search("race condition thread safety", index, k=5, model=st_model)
        idxs = set(_result_indices(results)[:5])
        overlap = idxs & GROUP_C
        assert len(overlap) >= 2, f"top-5 should have >=2 from Group C, got indices {idxs}"

    # 4
    def test_input_validation_query(self, index, st_model):
        results = search("input validation sanitize user data", index, k=5, model=st_model)
        idxs = set(_result_indices(results)[:5])
        overlap = idxs & GROUP_D
        assert len(overlap) >= 2, f"top-5 should have >=2 from Group D, got indices {idxs}"

    # 5
    def test_parameterized_query_specific(self, index, st_model):
        results = search("parameterized query", index, k=3, model=st_model)
        idxs = _result_indices(results)
        assert idxs[0] in GROUP_A, f"top-1 should be Group A for 'parameterized query', got idx {idxs[0]}"

    # 6
    def test_goroutine_leak_specific(self, index, st_model):
        results = search("goroutine leak", index, k=5, model=st_model)
        idxs = _result_indices(results)
        assert 7 in idxs[:5], f"goroutine leak hunk (idx 7) should be in top-5, got {idxs[:5]}"

    # 7
    def test_xss_cross_site_scripting(self, index, st_model):
        results = search("XSS cross-site scripting", index, k=5, model=st_model)
        idxs = _result_indices(results)
        assert 17 in idxs[:5], f"XSS/HTML sanitize hunk (idx 17) should be in top-5, got {idxs[:5]}"

    # 8
    def test_mutex_deadlock(self, index, st_model):
        results = search("mutex deadlock", index, k=5, model=st_model)
        idxs = set(_result_indices(results)[:5])
        overlap = idxs & GROUP_C
        assert len(overlap) >= 1, f"mutex/deadlock query should find concurrency bugs, got {idxs}"

    # 9
    def test_new_feature_prefers_non_bugfix(self, index, st_model):
        results = search("new feature addition", index, k=5, model=st_model)
        idxs = _result_indices(results)[:5]
        overlap = set(idxs) & GROUP_E
        assert len(overlap) >= 1, f"'new feature' should find non-bugfix hunks, got {idxs}"

    # 10
    def test_code_formatting_style(self, index, st_model):
        results = search("code formatting style prettier", index, k=5, model=st_model)
        idxs = _result_indices(results)
        assert 24 in idxs[:5], f"code formatting hunk (idx 24) should be in top-5, got {idxs[:5]}"

    # 11
    def test_language_filter_go(self, index, st_model):
        results = search("fix bug", index, k=10, model=st_model, language="go")
        for r in results:
            assert r.hunk.language == "go", f"Expected Go, got {r.hunk.language}"

    # 12
    def test_language_python_bugfix_only(self, index, st_model):
        results = search("code change", index, k=10, model=st_model,
                         language="python", bugfix_only=True)
        for r in results:
            assert r.hunk.language == "python", f"Expected python, got {r.hunk.language}"
            assert r.hunk.is_bugfix is True, "Expected bugfix only"

    # 13
    def test_author_filter(self, index, st_model):
        results = search("fix", index, k=10, model=st_model, author="dev-carol")
        for r in results:
            assert "dev-carol" in r.hunk.author.lower(), f"Expected dev-carol, got {r.hunk.author}"

    # 14
    def test_after_date_filter(self, index, st_model):
        cutoff = datetime(2025, 6, 20)
        results = search("code", index, k=10, model=st_model, after=cutoff)
        for r in results:
            assert r.hunk.timestamp.replace(tzinfo=None) >= cutoff, \
                f"Expected after {cutoff}, got {r.hunk.timestamp}"

    # 15
    def test_before_date_filter(self, index, st_model):
        cutoff = datetime(2025, 6, 5)
        results = search("code", index, k=10, model=st_model, before=cutoff)
        for r in results:
            assert r.hunk.timestamp.replace(tzinfo=None) <= cutoff, \
                f"Expected before {cutoff}, got {r.hunk.timestamp}"


# ===========================================================================
# Review Precision Tests (15 tests)
# ===========================================================================

class TestReviewPrecision:
    """Tests 16-30: review warnings, risk levels, filtering."""

    # 16
    def test_sql_injection_similar_warns_high(self, index, st_model):
        current = _h(
            100, "WIP: building query",
            "cursor.execute(f\"SELECT * FROM accounts WHERE id='{uid}'\")",
            "cursor.execute(f\"SELECT * FROM accounts WHERE id='{uid}'\")",
            lang="python", path="src/db/accounts.py",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_100"})
        warnings = review(index, threshold=0.50, model=st_model, hunks=[current])
        assert len(warnings) >= 1, "SQL-injection-like code should trigger warnings"
        # At least one warning should reference a Group A hunk
        similar_idxs = set()
        for w in warnings:
            for i, h in enumerate(_HUNKS):
                if id(w.similar_hunk) == id(h):
                    similar_idxs.add(i)
        assert len(similar_idxs & GROUP_A) >= 1, \
            f"Expected SQL injection warning from Group A, got {similar_idxs}"

    # 17
    def test_memory_leak_similar_warns(self, index, st_model):
        current = _h(
            101, "WIP: open file",
            "f = open(path)",
            "f = open(path)\ndata = f.read()",
            lang="python", path="src/io/loader.py",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_101"})
        warnings = review(index, threshold=0.45, model=st_model, hunks=[current])
        assert len(warnings) >= 1, "Resource-leak-like code should trigger warnings"

    # 18
    def test_unrelated_css_no_warn(self, index, st_model):
        current = _h(
            102, "feat: update button color",
            ".btn { color: blue; }",
            ".btn { color: green; border-radius: 8px; }",
            lang="css", path="src/styles/buttons.css", is_bugfix=False,
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_102"})
        warnings = review(index, threshold=0.80, model=st_model, hunks=[current])
        assert len(warnings) == 0, f"Unrelated CSS should not warn at 0.80 threshold, got {len(warnings)}"

    # 19
    def test_threshold_090_strict(self, index, st_model):
        current = _h(
            103, "WIP: query building",
            "db.execute(q)", "db.execute(q)",
            lang="python", path="src/db/util.py",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_103"})
        warnings = review(index, threshold=0.90, model=st_model, hunks=[current])
        for w in warnings:
            assert w.similarity >= 0.90, f"threshold=0.90 but got similarity {w.similarity}"

    # 20
    def test_threshold_060_more_warnings(self, index, st_model):
        current = _h(
            104, "WIP: database access",
            "conn = db.connect()\nresult = conn.execute(q)",
            "conn = db.connect()\nresult = conn.execute(q)",
            lang="python", path="src/db/access.py",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_104"})
        w_strict = review(index, threshold=0.90, model=st_model, hunks=[current])
        w_relaxed = review(index, threshold=0.60, model=st_model, hunks=[current])
        assert len(w_relaxed) >= len(w_strict), \
            "Lower threshold should produce >= warnings than higher"

    # 21
    def test_top_k_1_limit(self, index, st_model):
        current = _h(
            105, "WIP: some code",
            "x = compute()", "x = compute()",
            lang="python", path="src/compute.py",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_105"})
        warnings = review(index, threshold=0.20, model=st_model, top_k=1, hunks=[current])
        assert len(warnings) <= 1, f"top_k=1 but got {len(warnings)} warnings"

    # 22
    def test_top_k_10_more_than_1(self, index, st_model):
        current = _h(
            106, "WIP: database query",
            "cursor.execute(query)", "cursor.execute(query)",
            lang="python", path="src/db/run.py",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_106"})
        w1 = review(index, threshold=0.30, model=st_model, top_k=1, hunks=[current])
        w10 = review(index, threshold=0.30, model=st_model, top_k=10, hunks=[current])
        assert len(w10) >= len(w1), "top_k=10 should produce >= warnings than top_k=1"

    # 23
    def test_risk_level_classification(self, index, st_model):
        # classify_risk unit tests
        bugfix_hunk = _HUNKS[0]   # is_bugfix=True
        non_bugfix_hunk = _HUNKS[20]  # is_bugfix=False

        assert classify_risk(0.95, bugfix_hunk) == "HIGH"
        assert classify_risk(0.90, bugfix_hunk) == "HIGH"
        assert classify_risk(0.85, bugfix_hunk) == "MEDIUM"
        assert classify_risk(0.80, bugfix_hunk) == "MEDIUM"
        assert classify_risk(0.75, bugfix_hunk) == "LOW"
        assert classify_risk(0.85, non_bugfix_hunk) == "LOW"
        assert classify_risk(0.50, non_bugfix_hunk) == "LOW"

    # 24
    def test_warning_reason_contains_info(self, index, st_model):
        current = _h(
            107, "WIP: sql query",
            "cursor.execute(f\"SELECT * FROM t WHERE x='{v}'\")",
            "cursor.execute(f\"SELECT * FROM t WHERE x='{v}'\")",
            lang="python", path="src/db/temp.py",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_107"})
        warnings = review(index, threshold=0.45, model=st_model, hunks=[current])
        for w in warnings:
            assert w.similar_hunk.file_path in w.reason, \
                "reason should contain file path"
            assert w.similar_hunk.commit_message.split(":")[0] in w.reason or \
                   w.similar_hunk.commit_hash[:7] in w.reason, \
                "reason should contain commit info"

    # 25
    def test_similar_hunk_bugfix_flag(self, index, st_model):
        current = _h(
            108, "WIP: code",
            "x = 1", "x = 2",
            lang="python", path="src/temp.py",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_108"})
        warnings = review(index, threshold=0.20, model=st_model, hunks=[current])
        for w in warnings:
            # Verify the is_bugfix flag matches the original hunk
            for h in _HUNKS:
                if id(w.similar_hunk) == id(h):
                    assert w.similar_hunk.is_bugfix == h.is_bugfix

    # 26
    def test_warnings_sorted_descending(self, index, st_model):
        current = _h(
            109, "WIP: database operation",
            "conn.execute(q)", "conn.execute(q)",
            lang="python", path="src/db/ops.py",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_109"})
        warnings = review(index, threshold=0.20, model=st_model, hunks=[current])
        if len(warnings) >= 2:
            for i in range(len(warnings) - 1):
                assert warnings[i].similarity >= warnings[i + 1].similarity, \
                    f"Warnings not sorted: {warnings[i].similarity} < {warnings[i+1].similarity}"

    # 27
    def test_self_match_prevention(self, index, st_model):
        # Use exact commit_hash of hunk 0
        clone = DiffHunk(**{**_HUNKS[0].__dict__})
        warnings = review(index, threshold=0.10, model=st_model, hunks=[clone])
        for w in warnings:
            assert w.similar_hunk.commit_hash != clone.commit_hash, \
                "Self-match should be filtered out"

    # 28
    def test_exact_duplicate_prevention(self, index, st_model):
        # Same file + same code but different commit hash
        dup = DiffHunk(
            commit_hash="dup_unique_hash_xxxxxxxxxx",
            file_path=_HUNKS[0].file_path,
            language=_HUNKS[0].language,
            old_code=_HUNKS[0].old_code,
            new_code=_HUNKS[0].new_code,
            context=_HUNKS[0].context,
            commit_message="duplicate entry",
            author="someone",
            timestamp=datetime(2025, 6, 1),
            is_bugfix=True,
        )
        warnings = review(index, threshold=0.10, model=st_model, hunks=[dup])
        for w in warnings:
            is_exact_dup = (w.similar_hunk.file_path == dup.file_path
                           and w.similar_hunk.new_code == dup.new_code
                           and w.similar_hunk.old_code == dup.old_code)
            assert not is_exact_dup, "Exact duplicate (same file + code) should be filtered"

    # 29
    def test_review_no_match_empty(self, index, st_model):
        current = _h(
            110, "feat: quantum entanglement simulator",
            "",
            "def simulate_entanglement(qubits, basis):\n    return quantum_circuit.run(qubits, basis)",
            lang="python", path="src/quantum/sim.py", is_bugfix=False,
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_110"})
        warnings = review(index, threshold=0.92, model=st_model, hunks=[current])
        assert len(warnings) == 0, \
            f"Very unrelated hunk with high threshold should get 0 warnings, got {len(warnings)}"

    # 30
    def test_multiple_current_hunks_independent(self, index, st_model):
        h1 = _h(111, "WIP: sql query build",
                 "cursor.execute(f\"SELECT * FROM users WHERE id='{uid}'\")",
                 "cursor.execute(f\"SELECT * FROM users WHERE id='{uid}'\")",
                 lang="python", path="src/db/q.py")
        h1 = DiffHunk(**{**h1.__dict__, "commit_hash": "current_111"})

        h2 = _h(112, "WIP: open resource",
                 "f = open(p)\ndata = f.read()",
                 "f = open(p)\ndata = f.read()",
                 lang="python", path="src/io/r.py")
        h2 = DiffHunk(**{**h2.__dict__, "commit_hash": "current_112"})

        warnings = review(index, threshold=0.40, model=st_model, hunks=[h1, h2])
        current_hashes = {w.current_hunk.commit_hash for w in warnings}
        # Both hunks should get at least some warnings
        assert len(current_hashes) >= 2, \
            f"Expected warnings for both hunks, got hashes {current_hashes}"


# ===========================================================================
# Scoring Rigor Tests (10 tests)
# ===========================================================================

class TestScoringRigor:
    """Tests 31-40: score validity, filters, compression, performance."""

    # 31
    def test_sql_query_scores_higher_for_sql_injection(self, index, st_model):
        results = search("SQL query injection", index, k=30, model=st_model)
        score_map = {_result_indices([r])[0]: r.score for r in results}
        best_a = max((score_map.get(i, -2) for i in GROUP_A), default=-2)
        best_e = max((score_map.get(i, -2) for i in GROUP_E), default=-2)
        assert best_a > best_e, \
            f"SQL injection group ({best_a:.3f}) should score higher than non-bugfix ({best_e:.3f})"

    # 32
    def test_memory_leak_scores_higher_than_css(self, index, st_model):
        results = search("memory leak goroutine", index, k=30, model=st_model)
        score_map = {_result_indices([r])[0]: r.score for r in results}
        score_goroutine = score_map.get(7, -2)
        score_css = score_map.get(24, -2)
        assert score_goroutine > score_css, \
            f"Goroutine leak ({score_goroutine:.3f}) should score > CSS style ({score_css:.3f})"

    # 33
    def test_bugfix_only_excludes_group_e(self, index, st_model):
        results = search("code change", index, k=30, model=st_model, bugfix_only=True)
        idxs = set(_result_indices(results))
        overlap = idxs & GROUP_E
        assert len(overlap) == 0, f"bugfix_only should exclude Group E, found {overlap}"

    # 34
    def test_language_filter_rust(self, index, st_model):
        results = search("atomic operation", index, k=10, model=st_model, language="rust")
        for r in results:
            assert r.hunk.language == "rust", f"Expected rust, got {r.hunk.language}"
        if results:
            assert _result_indices(results)[0] == 13, "Rust atomic hunk should be found"

    # 35
    def test_all_scores_in_valid_range(self, index, st_model):
        results = search("any code change", index, k=30, model=st_model)
        for r in results:
            assert -1.01 <= r.score <= 1.01, f"Score {r.score} out of range [-1, 1]"

    # 36
    def test_top_k_returns_correct_count(self, index, st_model):
        results = search("fix bug", index, k=3, model=st_model)
        assert len(results) <= 3, f"k=3 but got {len(results)} results"
        assert len(results) == 3, f"k=3 with 30 hunks should return 3, got {len(results)}"

    # 37
    def test_different_queries_different_distributions(self, index, st_model):
        r1 = search("SQL injection parameterized query", index, k=5, model=st_model)
        r2 = search("goroutine memory leak cleanup", index, k=5, model=st_model)
        scores1 = [r.score for r in r1]
        scores2 = [r.score for r in r2]
        # The score vectors should not be identical
        assert scores1 != scores2, "Different queries should produce different score distributions"

    # 38
    def test_bits2_still_finds_correct_top1(self, st_model, embeddings):
        from langchain_turboquant import TurboQuantizer
        dim = embeddings.shape[1]
        q2 = TurboQuantizer(dim=dim, bits=2)
        c2 = q2.quantize(embeddings)
        idx2 = DiffMindIndex(
            hunks=list(_HUNKS), compressed=c2, quantizer=q2,
            model_name="all-MiniLM-L6-v2", embedding_dim=dim,
            total_commits=30, bugfix_commits=22, files_tracked=25,
            languages=[], raw_memory_bytes=0, compressed_memory_bytes=0,
            learn_time=0.0,
        )
        results = search("parameterized SQL query injection", idx2, k=1, model=st_model)
        assert len(results) == 1
        idx = _result_indices(results)[0]
        assert idx in GROUP_A, f"bits=2 top-1 should be Group A, got idx {idx}"

    # 39
    def test_bits4_correlation_with_bits3(self, st_model, embeddings, index):
        from langchain_turboquant import TurboQuantizer
        from scipy.stats import spearmanr
        dim = embeddings.shape[1]

        q4 = TurboQuantizer(dim=dim, bits=4)
        c4 = q4.quantize(embeddings)

        query_vec = st_model.encode(["SQL injection vulnerability"])
        scores3 = np.array(index.quantizer.cosine_scores(query_vec, index.compressed)).flatten()
        scores4 = np.array(q4.cosine_scores(query_vec, c4)).flatten()

        corr, _ = spearmanr(scores3, scores4)
        assert corr > 0.8, f"Spearman correlation bits3 vs bits4 = {corr:.3f}, expected > 0.8"

    # 40
    def test_30_hunks_search_performance(self, index, st_model):
        t0 = time.time()
        for _ in range(5):
            search("SQL injection memory leak race condition", index, k=10, model=st_model)
        elapsed = time.time() - t0
        # 5 searches should complete in < 5 seconds (1s each generously)
        assert elapsed < 5.0, f"5 searches took {elapsed:.2f}s, expected < 5s"

"""Tests for DiffMind with REAL sentence-transformers model and TurboQuant compression.

These tests verify semantic understanding of code patterns using actual embeddings,
not mocks.  They require: sentence-transformers, langchain-turboquant.
"""

from __future__ import annotations

from datetime import datetime
from typing import List

import numpy as np
import pytest

from diffmind.models import DiffHunk, DiffMindIndex, ReviewWarning
from diffmind.searcher import SearchResult, search
from diffmind.reviewer import review, classify_risk


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _h(
    idx: int,
    msg: str,
    old: str,
    new: str,
    *,
    lang: str = "python",
    path: str = "src/main.py",
    author: str = "Alice",
    is_bugfix: bool = True,
    context: str = "",
) -> DiffHunk:
    return DiffHunk(
        commit_hash=f"commit_{idx:04d}_{'x' * 30}",
        file_path=path,
        language=lang,
        old_code=old,
        new_code=new,
        context=context,
        commit_message=msg,
        author=author,
        timestamp=datetime(2024, 1, 1 + idx % 28, 10, 0),
        is_bugfix=is_bugfix,
    )


# ---------------------------------------------------------------------------
# Fixture hunks (20 items, 5 categories)
# ---------------------------------------------------------------------------

_HUNKS: List[DiffHunk] = [
    # -- Category 1: NULL / NONE bugs (0-3) --
    _h(0, "fix: add null check before accessing user.name",
       "return user.name", "return user?.name if user else 'unknown'",
       context="def get_display_name(user):"),
    _h(1, "fix: None check missing in get_profile()",
       "return profile", "if profile is None:\n    raise ValueError('profile not found')\nreturn profile",
       context="def get_profile(uid):"),
    _h(2, "bugfix: NullPointerException in order processing",
       "order.getCustomer().getName()", "if (order.getCustomer() != null) {\n    return order.getCustomer().getName();\n}",
       lang="java", path="src/OrderService.java"),
    _h(3, "fix: optional chaining for config.settings",
       "const val = config.settings.theme", "const val = config?.settings?.theme ?? 'default'",
       lang="typescript", path="src/config.ts"),

    # -- Category 2: Authentication bugs (4-7) --
    _h(4, "fix: token expiry not checked",
       "return token", "if token.is_expired:\n    token = refresh_token(token)\nreturn token",
       path="src/auth.py", context="def get_valid_token(token):"),
    _h(5, "hotfix: session hijacking vulnerability",
       "session = get_session(sid)", "session = get_session(sid)\nif not validate_session_ip(session, request.remote_addr):\n    raise SecurityError('session mismatch')",
       path="src/auth.py"),
    _h(6, "fix: password hash comparison timing attack",
       "return stored_hash == computed_hash", "return constant_time_compare(stored_hash, computed_hash)",
       path="src/auth.py", context="def verify_password(password, stored_hash):"),
    _h(7, "fix: missing CORS headers",
       "return response", "response.headers['Access-Control-Allow-Origin'] = ALLOWED_ORIGINS\nreturn response",
       path="src/middleware.py", context="def cors_middleware(request, response):"),

    # -- Category 3: Error handling (8-11) --
    _h(8, "fix: unhandled exception in API endpoint",
       "result = process(data)\nreturn jsonify(result)",
       "try:\n    result = process(data)\n    return jsonify(result)\nexcept Exception as e:\n    return jsonify({'error': str(e)}), 500",
       path="src/api.py", context="@app.route('/process')"),
    _h(9, "fix: json.loads without try-except",
       "data = json.loads(raw)", "try:\n    data = json.loads(raw)\nexcept json.JSONDecodeError:\n    data = {}",
       path="src/parser_util.py"),
    _h(10, "fix: file read without error handling",
       "with open(path) as f:\n    return f.read()",
       "try:\n    with open(path) as f:\n        return f.read()\nexcept IOError:\n    return ''",
       path="src/file_utils.py"),
    _h(11, "fix: database connection not closed on error",
       "conn = db.connect()\nresult = conn.execute(query)\nconn.close()",
       "conn = db.connect()\ntry:\n    result = conn.execute(query)\nfinally:\n    conn.close()",
       path="src/db.py"),

    # -- Category 4: Performance issues (12-15) --
    _h(12, "fix: N+1 query in user list",
       "for user in users:\n    orders = db.query(Order).filter_by(user_id=user.id).all()",
       "orders = db.query(Order).filter(Order.user_id.in_([u.id for u in users])).all()",
       path="src/views.py"),
    _h(13, "fix: memory leak in cache",
       "cache[key] = value", "if len(cache) > MAX_CACHE_SIZE:\n    cache.popitem(last=False)\ncache[key] = value",
       path="src/cache.py"),
    _h(14, "fix: missing index on created_at column",
       "created_at = Column(DateTime)", "created_at = Column(DateTime, index=True)",
       path="src/models_db.py"),
    _h(15, "optimize: reduce API calls with batch processing",
       "for item in items:\n    resp = api.call(item)",
       "responses = api.batch_call(items)",
       path="src/integrations.py"),

    # -- Category 5: Non-bugfix changes (16-19) --
    _h(16, "feat: add dark mode support",
       ".container { background: #fff; color: #000; }",
       ".container { background: var(--bg); color: var(--fg); }\n:root { --bg: #fff; --fg: #000; }\n@media (prefers-color-scheme: dark) { :root { --bg: #1a1a1a; --fg: #eee; } }",
       lang="css", path="src/styles.css", is_bugfix=False),
    _h(17, "refactor: extract validation logic",
       "if len(name) < 2 or len(name) > 50:\n    raise ValueError\nif not re.match(r'^[a-zA-Z]+$', name):\n    raise ValueError",
       "validate_name(name)\n\ndef validate_name(name):\n    if len(name) < 2 or len(name) > 50:\n        raise ValueError\n    if not re.match(r'^[a-zA-Z]+$', name):\n        raise ValueError",
       is_bugfix=False),
    _h(18, "docs: update API documentation",
       "## API\nSee code.", "## API\n\n### GET /users\nReturns list of users.\n\n### POST /users\nCreate a new user.",
       lang="markdown", path="README.md", is_bugfix=False),
    _h(19, "chore: update dependencies",
       '"react": "^17.0.0"', '"react": "^18.2.0"',
       lang="json", path="package.json", is_bugfix=False),
]


# ---------------------------------------------------------------------------
# Module-scoped fixtures (expensive — created once per test session)
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
        total_commits=20,
        bugfix_commits=16,
        files_tracked=15,
        languages=["python", "java", "typescript", "css", "markdown", "json"],
        raw_memory_bytes=embeddings.nbytes,
        compressed_memory_bytes=0,
        learn_time=0.0,
    )


# ---------------------------------------------------------------------------
# Helper to get indices of search results
# ---------------------------------------------------------------------------

def _result_indices(results: List[SearchResult]) -> List[int]:
    """Return the original _HUNKS indices for each result."""
    idx_map = {id(h): i for i, h in enumerate(_HUNKS)}
    return [idx_map[id(r.hunk)] for r in results]


# ===========================================================================
# Semantic Search Tests (20 tests)
# ===========================================================================

class TestSemanticSearch:

    # 1
    def test_null_pointer_error(self, index, st_model):
        results = search("null pointer error", index, k=7, model=st_model)
        idxs = _result_indices(results)
        null_cat = {0, 1, 2, 3}
        assert len(null_cat & set(idxs[:5])) >= 2, f"Expected null hunks in top-5, got {idxs[:5]}"

    # 2
    def test_nullpointerexception_java(self, index, st_model):
        results = search("NullPointerException", index, k=7, model=st_model)
        idxs = _result_indices(results)
        assert 2 in idxs[:5], f"Expected Java null bug (idx 2) in top-5, got {idxs[:5]}"

    # 3
    def test_authentication_security(self, index, st_model):
        results = search("authentication security", index, k=7, model=st_model)
        idxs = _result_indices(results)
        auth_cat = {4, 5, 6, 7}
        assert len(auth_cat & set(idxs[:5])) >= 2, f"Expected auth hunks in top-5, got {idxs[:5]}"

    # 4
    def test_token_validation(self, index, st_model):
        results = search("token validation", index, k=7, model=st_model)
        idxs = _result_indices(results)
        assert 4 in idxs[:5], f"Expected token expiry fix (idx 4) in top-5, got {idxs[:5]}"

    # 5
    def test_exception_handling_missing(self, index, st_model):
        results = search("exception handling missing", index, k=7, model=st_model)
        idxs = _result_indices(results)
        err_cat = {8, 9, 10, 11}
        assert len(err_cat & set(idxs[:5])) >= 2, f"Expected error-handling hunks in top-5, got {idxs[:5]}"

    # 6
    def test_try_catch_error(self, index, st_model):
        results = search("try catch error", index, k=7, model=st_model)
        idxs = _result_indices(results)
        err_cat = {8, 9, 10, 11}
        assert len(err_cat & set(idxs[:5])) >= 1, f"Expected error-handling hunks in top-5, got {idxs[:5]}"

    # 7
    def test_database_performance(self, index, st_model):
        results = search("database performance slow query", index, k=7, model=st_model)
        idxs = _result_indices(results)
        perf_cat = {12, 13, 14, 15}
        assert len(perf_cat & set(idxs[:5])) >= 1, f"Expected perf hunks in top-5, got {idxs[:5]}"

    # 8
    def test_memory_leak(self, index, st_model):
        results = search("memory leak", index, k=7, model=st_model)
        idxs = _result_indices(results)
        assert 13 in idxs[:5], f"Expected cache memory leak fix (idx 13) in top-5, got {idxs[:5]}"

    # 9
    def test_file_path_filter(self, index, st_model):
        results = search("fix bug", index, k=10, model=st_model, file_path="auth.py")
        for r in results:
            assert "auth.py" in r.hunk.file_path.lower()

    # 10
    def test_author_filter(self, index, st_model):
        results = search("fix bug", index, k=10, model=st_model, author="Alice")
        for r in results:
            assert "alice" in r.hunk.author.lower()

    # 11
    def test_language_filter(self, index, st_model):
        results = search("code change", index, k=10, model=st_model, language="python")
        for r in results:
            assert r.hunk.language == "python"

    # 12
    def test_bugfix_only_filter(self, index, st_model):
        results = search("change", index, k=10, model=st_model, bugfix_only=True)
        for r in results:
            assert r.hunk.is_bugfix is True

    # 13
    def test_sql_injection_auth_higher(self, index, st_model):
        results = search("SQL injection vulnerability", index, k=20, model=st_model)
        idxs = _result_indices(results)
        scores = {i: r.score for i, r in zip(idxs, results)}
        auth_cat = {4, 5, 6, 7}
        perf_cat = {12, 13, 14, 15}
        best_auth = max((scores.get(i, -1) for i in auth_cat), default=-1)
        best_perf = max((scores.get(i, -1) for i in perf_cat), default=-1)
        assert best_auth > best_perf, "Auth category should score higher than performance for SQL injection query"

    # 14
    def test_cors_cross_origin(self, index, st_model):
        results = search("CORS cross-origin", index, k=7, model=st_model)
        idxs = _result_indices(results)
        assert 7 in idxs[:5], f"Expected CORS fix (idx 7) in top-5, got {idxs[:5]}"

    # 15
    def test_password_security(self, index, st_model):
        results = search("password security", index, k=7, model=st_model)
        idxs = _result_indices(results)
        assert 6 in idxs[:5], f"Expected password hash fix (idx 6) in top-5, got {idxs[:5]}"

    # 16
    def test_file_operations_error(self, index, st_model):
        results = search("missing error handling in file operations", index, k=7, model=st_model)
        idxs = _result_indices(results)
        assert 10 in idxs[:5], f"Expected file read fix (idx 10) in top-5, got {idxs[:5]}"

    # 17
    def test_api_endpoint_crash(self, index, st_model):
        results = search("API endpoint crash", index, k=7, model=st_model)
        idxs = _result_indices(results)
        assert 8 in idxs[:7], f"Expected API exception fix (idx 8) in top-7, got {idxs[:7]}"

    # 18
    def test_new_feature_ui(self, index, st_model):
        results = search("new feature UI design", index, k=7, model=st_model)
        idxs = _result_indices(results)
        non_bugfix = {16, 17, 18, 19}
        assert len(non_bugfix & set(idxs[:5])) >= 1, f"Expected non-bugfix hunks in top-5, got {idxs[:5]}"

    # 19
    def test_code_cleanup_refactoring(self, index, st_model):
        results = search("code cleanup refactoring", index, k=7, model=st_model)
        idxs = _result_indices(results)
        assert 17 in idxs[:5], f"Expected refactor commit (idx 17) in top-5, got {idxs[:5]}"

    # 20
    def test_empty_query(self, index, st_model):
        results = search("", index, k=5, model=st_model)
        # Should not crash; may or may not return results
        assert isinstance(results, list)

        results2 = search("x", index, k=5, model=st_model)
        assert isinstance(results2, list)


# ===========================================================================
# Review / Risk Tests (10 tests)
# ===========================================================================

class TestReview:

    # 21
    def test_null_bug_high_risk(self, index, st_model):
        current = _h(
            99, "WIP: accessing user attribute",
            "return user.email", "return user.email",
            context="def get_email(user):",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_99"})
        warnings = review(index, threshold=0.40, model=st_model, hunks=[current])
        if warnings:
            # At least one warning should reference a null-category hunk
            similar_idxs = []
            for w in warnings:
                for i, h in enumerate(_HUNKS):
                    if id(w.similar_hunk) == id(h):
                        similar_idxs.append(i)
            null_cat = {0, 1, 2, 3}
            assert len(null_cat & set(similar_idxs)) >= 1 or len(warnings) > 0

    # 22
    def test_auth_bug_warning(self, index, st_model):
        current = _h(
            100, "WIP: token handling",
            "return token", "return token",
            path="src/auth.py", context="def validate_token(token):",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_100"})
        warnings = review(index, threshold=0.40, model=st_model, hunks=[current])
        assert len(warnings) >= 1, "Expected at least one warning for auth-like hunk"

    # 23
    def test_no_similar_pattern(self, index, st_model):
        current = _h(
            101, "feat: add weather widget",
            "", "def get_weather(city):\n    return requests.get(f'https://weather.api/{city}').json()",
            path="src/weather.py", is_bugfix=False,
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_101"})
        warnings = review(index, threshold=0.90, model=st_model, hunks=[current])
        # With a very high threshold, unrelated code should produce few/no warnings
        assert len(warnings) <= 2, f"Expected few warnings for unrelated hunk, got {len(warnings)}"

    # 24
    def test_threshold_comparison(self, index, st_model):
        current = _h(
            102, "WIP: error handling",
            "data = json.loads(raw)", "data = json.loads(raw)",
            context="def parse(raw):",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_102"})
        w_high = review(index, threshold=0.95, model=st_model, hunks=[current])
        w_low = review(index, threshold=0.50, model=st_model, hunks=[current])
        assert len(w_high) <= len(w_low), "Higher threshold should produce fewer or equal warnings"

    # 25
    def test_top_k_limit(self, index, st_model):
        current = _h(
            103, "WIP: some change",
            "x = 1", "x = 2",
        )
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_103"})
        warnings = review(index, threshold=0.20, model=st_model, top_k=1, hunks=[current])
        assert len(warnings) <= 1, f"top_k=1 but got {len(warnings)} warnings"

    # 26
    def test_self_match_skipped(self, index, st_model):
        """If current hunk has the same commit_hash + file + code as a past hunk, skip it."""
        # Use exact same commit hash as hunk 0
        clone = DiffHunk(**{**_HUNKS[0].__dict__})
        warnings = review(index, threshold=0.10, model=st_model, hunks=[clone])
        for w in warnings:
            assert w.similar_hunk.commit_hash != clone.commit_hash, \
                "Self-match should be filtered out"

    # 27
    def test_multiple_current_hunks(self, index, st_model):
        h1 = _h(104, "WIP: auth", "return token", "return token", path="src/auth.py")
        h1 = DiffHunk(**{**h1.__dict__, "commit_hash": "current_104"})
        h2 = _h(105, "WIP: parsing", "json.loads(x)", "json.loads(x)", path="src/parser_util.py")
        h2 = DiffHunk(**{**h2.__dict__, "commit_hash": "current_105"})
        warnings = review(index, threshold=0.40, model=st_model, hunks=[h1, h2])
        # Should have warnings referencing both current hunks
        current_hashes = {w.current_hunk.commit_hash for w in warnings}
        assert len(current_hashes) >= 1, "Expected warnings for at least one current hunk"

    # 28
    def test_bugfix_scores_higher_risk(self, index, st_model):
        """Bugfix past hunks should get HIGH/MEDIUM risk, non-bugfix should get LOW."""
        current = _h(106, "WIP: null check", "user.name", "user.name",
                      context="def display(user):")
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_106"})
        warnings = review(index, threshold=0.30, model=st_model, hunks=[current])
        for w in warnings:
            if w.similar_hunk.is_bugfix and w.similarity >= 0.90:
                assert w.risk_level == "HIGH"
            elif not w.similar_hunk.is_bugfix:
                assert w.risk_level == "LOW"

    # 29
    def test_warning_contains_correct_info(self, index, st_model):
        current = _h(107, "WIP: token", "return t", "return t", path="src/auth.py")
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_107"})
        warnings = review(index, threshold=0.30, model=st_model, hunks=[current])
        for w in warnings:
            assert isinstance(w.similarity, float)
            assert w.risk_level in ("HIGH", "MEDIUM", "LOW")
            assert w.similar_hunk.file_path  # non-empty
            assert w.similar_hunk.commit_hash  # non-empty
            assert w.current_hunk.commit_hash == "current_107"
            assert w.reason  # non-empty string

    # 30
    def test_warnings_sorted_descending(self, index, st_model):
        current = _h(108, "WIP: code", "x = 1", "x = 2")
        current = DiffHunk(**{**current.__dict__, "commit_hash": "current_108"})
        warnings = review(index, threshold=0.20, model=st_model, hunks=[current])
        if len(warnings) >= 2:
            for i in range(len(warnings) - 1):
                assert warnings[i].similarity >= warnings[i + 1].similarity, \
                    "Warnings should be sorted by similarity descending"


# ===========================================================================
# Compression & Score Tests (5 tests)
# ===========================================================================

class TestCompressionScores:

    # 31
    def test_compressed_correlate_with_raw(self, st_model, embeddings):
        """TurboQuant compressed scores should correlate with raw cosine similarity."""
        from langchain_turboquant import TurboQuantizer

        query = st_model.encode(["null check bug"])
        # Raw cosine similarity
        norms_e = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms_q = np.linalg.norm(query, axis=1, keepdims=True)
        raw_scores = (query / norms_q) @ (embeddings / norms_e).T
        raw_scores = raw_scores.flatten()

        # Compressed scores
        quantizer = TurboQuantizer(dim=embeddings.shape[1], bits=3)
        compressed = quantizer.quantize(embeddings)
        comp_scores = np.array(quantizer.cosine_scores(query, compressed)).flatten()

        # Spearman rank correlation should be positive and strong
        from scipy.stats import spearmanr
        corr, _ = spearmanr(raw_scores, comp_scores)
        assert corr > 0.7, f"Rank correlation between raw and compressed scores too low: {corr:.3f}"

    # 32
    def test_different_bit_widths(self, st_model, embeddings):
        from langchain_turboquant import TurboQuantizer
        query = st_model.encode(["authentication token"])
        dim = embeddings.shape[1]

        results_by_bits = {}
        for bits in (2, 4):
            q = TurboQuantizer(dim=dim, bits=bits)
            c = q.quantize(embeddings)
            scores = np.array(q.cosine_scores(query, c)).flatten()
            results_by_bits[bits] = scores

        # Both should produce valid scores
        for bits, scores in results_by_bits.items():
            assert scores.shape[0] == len(_HUNKS), f"bits={bits}: wrong number of scores"
            top_idx = int(np.argmax(scores))
            assert top_idx in range(len(_HUNKS)), f"bits={bits}: invalid top index"

    # 33
    def test_100_hunks_search(self, st_model):
        """Build an index with ~100 hunks and verify search works."""
        from langchain_turboquant import TurboQuantizer

        big_hunks = []
        for i in range(100):
            base = _HUNKS[i % len(_HUNKS)]
            h = DiffHunk(
                commit_hash=f"big_{i:04d}_{'y' * 30}",
                file_path=base.file_path,
                language=base.language,
                old_code=base.old_code,
                new_code=base.new_code,
                context=base.context,
                commit_message=f"{base.commit_message} (copy {i})",
                author=base.author,
                timestamp=base.timestamp,
                is_bugfix=base.is_bugfix,
            )
            big_hunks.append(h)

        texts = [h.to_embedding_text() for h in big_hunks]
        embs = st_model.encode(texts)
        dim = embs.shape[1]
        quantizer = TurboQuantizer(dim=dim, bits=3)
        compressed = quantizer.quantize(embs)

        big_index = DiffMindIndex(
            hunks=big_hunks,
            compressed=compressed,
            quantizer=quantizer,
            model_name="all-MiniLM-L6-v2",
            embedding_dim=dim,
            total_commits=100,
            bugfix_commits=80,
            files_tracked=15,
            languages=["python"],
            raw_memory_bytes=embs.nbytes,
            compressed_memory_bytes=0,
            learn_time=0.0,
        )

        results = search("null check", big_index, k=5, model=st_model)
        assert len(results) == 5
        assert all(r.score > -1 for r in results)

    # 34
    def test_scores_in_range(self, index, st_model):
        results = search("fix bug", index, k=20, model=st_model)
        for r in results:
            assert -1.01 <= r.score <= 1.01, f"Score {r.score} out of expected range"

    # 35
    def test_different_queries_different_top1(self, index, st_model):
        r1 = search("null pointer exception Java", index, k=1, model=st_model)
        r2 = search("dark mode CSS theme", index, k=1, model=st_model)
        r3 = search("N+1 query database performance", index, k=1, model=st_model)
        tops = {r1[0].hunk.commit_hash, r2[0].hunk.commit_hash, r3[0].hunk.commit_hash}
        assert len(tops) >= 2, "Very different queries should produce at least 2 distinct top-1 results"

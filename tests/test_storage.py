"""Tests for DiffMind storage."""

import os
import tempfile
import pytest

from diffmind.models import DiffMindIndex
from diffmind.storage import (
    get_index_path,
    get_storage_path,
    index_exists,
    load_index,
    save_index,
)


def _make_index():
    return DiffMindIndex(
        hunks=[],
        compressed=None,
        quantizer=None,
        model_name="test",
        embedding_dim=384,
        total_commits=10,
        bugfix_commits=3,
        files_tracked=5,
        languages=["python"],
        raw_memory_bytes=1000,
        compressed_memory_bytes=500,
        learn_time=1.0,
        last_learned_commit="abc123",
    )


class TestStorage:
    def test_storage_path(self):
        path = get_storage_path("/tmp/repo")
        assert ".diffmind" in path

    def test_index_path(self):
        path = get_index_path("/tmp/repo")
        assert "index.pkl" in path

    def test_save_load_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            idx = _make_index()
            save_index(idx, tmpdir)
            loaded = load_index(tmpdir)
            assert loaded.total_commits == 10
            assert loaded.model_name == "test"
            assert loaded.last_learned_commit == "abc123"

    def test_index_exists_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            assert index_exists(tmpdir) is False

    def test_index_exists_true(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            save_index(_make_index(), tmpdir)
            assert index_exists(tmpdir) is True

    def test_load_nonexistent_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError):
                load_index(tmpdir)

    def test_creates_directory(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            repo_path = os.path.join(tmpdir, "new_repo")
            os.makedirs(repo_path)
            save_index(_make_index(), repo_path)
            assert os.path.exists(get_index_path(repo_path))

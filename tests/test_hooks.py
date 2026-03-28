"""Tests for DiffMind hooks."""

import os
import tempfile

import pytest

from diffmind.hooks import generate_github_action, install_pre_commit


class TestPreCommitHook:
    def test_install_creates_hook(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create .git/hooks directory
            git_dir = os.path.join(tmpdir, ".git")
            os.makedirs(git_dir)

            path = install_pre_commit(tmpdir)
            assert os.path.exists(path)
            with open(path, "r") as f:
                content = f.read()
            assert "DiffMind" in content
            assert "diffmind review" in content

    def test_install_default_fail_on_high(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".git"))
            path = install_pre_commit(tmpdir, fail_on="high")
            with open(path, "r") as f:
                content = f.read()
            assert "high" in content

    def test_install_fail_on_medium(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".git"))
            path = install_pre_commit(tmpdir, fail_on="medium")
            with open(path, "r") as f:
                content = f.read()
            assert "medium" in content

    def test_install_no_git_dir_raises(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.raises(FileNotFoundError):
                install_pre_commit(tmpdir)

    def test_backup_existing_hook(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hooks_dir = os.path.join(tmpdir, ".git", "hooks")
            os.makedirs(hooks_dir)
            existing = os.path.join(hooks_dir, "pre-commit")
            with open(existing, "w") as f:
                f.write("#!/bin/sh\necho existing")

            install_pre_commit(tmpdir)
            assert os.path.exists(existing + ".backup")

    def test_no_backup_if_already_diffmind(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            hooks_dir = os.path.join(tmpdir, ".git", "hooks")
            os.makedirs(hooks_dir)
            existing = os.path.join(hooks_dir, "pre-commit")
            with open(existing, "w") as f:
                f.write("#!/bin/sh\n# DiffMind hook\ndiffmind review")

            install_pre_commit(tmpdir)
            assert not os.path.exists(existing + ".backup")


class TestGitHubAction:
    def test_generates_workflow(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_github_action(tmpdir)
            assert os.path.exists(path)
            assert "diffmind.yml" in path
            with open(path, "r") as f:
                content = f.read()
            assert "DiffMind" in content
            assert "diffmind learn" in content
            assert "diffmind review" in content

    def test_fail_on_option(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = generate_github_action(tmpdir, fail_on="medium")
            with open(path, "r") as f:
                content = f.read()
            assert "medium" in content

    def test_creates_directories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            generate_github_action(tmpdir)
            assert os.path.isdir(os.path.join(tmpdir, ".github", "workflows"))

"""Save and load DiffMindIndex."""

from __future__ import annotations

import os
import pickle
from typing import Optional

from .models import DiffMindIndex

DEFAULT_DIR = ".diffmind"
INDEX_FILE = "index.pkl"


def get_storage_path(repo_path: str = ".") -> str:
    """Get the storage directory path."""
    return os.path.join(os.path.abspath(repo_path), DEFAULT_DIR)


def get_index_path(repo_path: str = ".") -> str:
    """Get the index file path."""
    return os.path.join(get_storage_path(repo_path), INDEX_FILE)


def save_index(index: DiffMindIndex, repo_path: str = ".") -> str:
    """Save index to disk. Returns the file path."""
    storage_dir = get_storage_path(repo_path)
    os.makedirs(storage_dir, exist_ok=True)

    path = os.path.join(storage_dir, INDEX_FILE)
    with open(path, "wb") as f:
        pickle.dump(index, f)

    return path


def load_index(repo_path: str = ".") -> DiffMindIndex:
    """Load index from disk."""
    path = get_index_path(repo_path)
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"No DiffMind index found at {path}.\n"
            f"Run 'diffmind learn' first."
        )

    with open(path, "rb") as f:
        index = pickle.load(f)

    if not isinstance(index, DiffMindIndex):
        raise ValueError(f"Invalid index file: {path}")

    return index


def index_exists(repo_path: str = ".") -> bool:
    """Check if an index exists."""
    return os.path.exists(get_index_path(repo_path))

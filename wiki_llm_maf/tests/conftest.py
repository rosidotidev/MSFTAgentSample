"""Shared fixtures for wiki_llm_maf tests."""

import os
import shutil

import pytest


FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


@pytest.fixture
def wiki_root(tmp_path):
    """Copy the committed fixtures to a tmp directory and set WIKI_ROOT_DIR.

    Each test gets an isolated copy — mutations don't affect other tests.
    """
    dest = tmp_path / "wiki_data"
    shutil.copytree(FIXTURES_DIR, dest)
    os.environ["WIKI_ROOT_DIR"] = str(dest)
    yield dest
    del os.environ["WIKI_ROOT_DIR"]


@pytest.fixture
def e2e_wiki_root(tmp_path):
    """An empty wiki with only a raw source — for E2E ingest tests.

    Creates the minimal directory structure needed for a full ingest cycle.
    """
    dest = tmp_path / "wiki_e2e"
    dest.mkdir()

    # Directories
    (dest / "raw").mkdir()
    (dest / "wiki").mkdir()
    (dest / "wiki" / "sources").mkdir()
    (dest / "wiki" / "entities").mkdir()
    (dest / "wiki" / "concepts").mkdir()
    (dest / "wiki" / "synthesis").mkdir()
    (dest / "questions_pending").mkdir()
    (dest / "questions_approved").mkdir()
    (dest / "lint_pending").mkdir()
    (dest / "lint_approved").mkdir()

    # Empty index and log
    (dest / "wiki" / "index.md").write_text(
        "---\ntitle: Wiki Index\ntype: index\n---\n\n# Wiki Index\n",
        encoding="utf-8",
    )
    (dest / "wiki" / "log.md").write_text("# Wiki Log\n", encoding="utf-8")

    # A small raw source for ingestion
    (dest / "raw" / "test-python-decorators.md").write_text(
        "# Python Decorators\n\n"
        "A decorator in Python is a function that takes another function as an argument "
        "and extends its behavior without explicitly modifying it.\n\n"
        "## Key Points\n\n"
        "- Decorators use the `@` syntax sugar.\n"
        "- Common built-in decorators: `@staticmethod`, `@classmethod`, `@property`.\n"
        "- Decorators can be stacked: multiple decorators applied to the same function.\n"
        "- `functools.wraps` preserves the original function's metadata.\n\n"
        "## Example\n\n"
        "```python\n"
        "import functools\n\n"
        "def my_decorator(func):\n"
        "    @functools.wraps(func)\n"
        "    def wrapper(*args, **kwargs):\n"
        "        print('Before call')\n"
        "        result = func(*args, **kwargs)\n"
        "        print('After call')\n"
        "        return result\n"
        "    return wrapper\n\n"
        "@my_decorator\n"
        "def greet(name):\n"
        "    return f'Hello, {name}!'\n"
        "```\n",
        encoding="utf-8",
    )

    os.environ["WIKI_ROOT_DIR"] = str(dest)
    yield dest
    del os.environ["WIKI_ROOT_DIR"]

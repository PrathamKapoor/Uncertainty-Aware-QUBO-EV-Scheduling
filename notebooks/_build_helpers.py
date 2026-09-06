"""Helper to programmatically build .ipynb files for the research notebooks.

This is a one-time build script; it is not part of the research pipeline. After
running it, the resulting .ipynb files should be opened, executed, and saved
through Jupyter (or nbconvert --execute) so that the outputs reflect the real
run.

Usage:
    python notebooks/_build_helpers.py
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict, Any


def md(source: str) -> Dict[str, Any]:
    """Build a Markdown cell."""
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def code(source: str) -> Dict[str, Any]:
    """Build a code cell with cleared outputs and no execution count."""
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


def notebook(cells: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Wrap a cell list as a Jupyter notebook (nbformat 4)."""
    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3",
                "language": "python",
                "name": "python3",
            },
            "language_info": {
                "name": "python",
                "version": "3.13",
                "mimetype": "text/x-python",
                "file_extension": ".py",
            },
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def write(path: Path, nb: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(nb, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"wrote {path}")

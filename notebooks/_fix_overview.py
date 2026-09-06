"""Add Why / Method / Implementation sections to the overview notebook.

The overview doesn't have its own why/method/implementation in the
literal sense (it describes the other notebooks). Add thin pointer
sections that reference notebooks 01-12.
"""
from __future__ import annotations

import json
from pathlib import Path

NB = Path(__file__).resolve().parent.parent / "notebooks"


def as_lines(s: str) -> list:
    if not s.endswith("\n"):
        s = s + "\n"
    return s.splitlines(keepends=True)


def md(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": as_lines(source),
    }


def main() -> None:
    path = NB / "00_overview.ipynb"
    nb = json.loads(path.read_text(encoding="utf-8"))
    cells = list(nb["cells"])

    # Find the `## Research question` cell and insert three pointer
    # sections after it.
    insert_at = 0
    for i, c in enumerate(cells):
        if c["cell_type"] == "markdown":
            text = "".join(c.get("source", [])) if isinstance(c.get("source"), list) else c.get("source", "")
            if "## Research question" in text or text.strip().startswith("## Research question"):
                insert_at = i + 1
                break

    extra = [
        md(
            "## Why this test exists\n"
            "\n"
            "The other 12 notebooks in this set each investigate one specific "
            "test. This overview exists to give the reader a single entry "
            "point that explains the research question, the hypothesis, and "
            "the reading order. For the actual scientific motivation, see "
            "notebooks 01-12 individually.\n"
        ),
        md(
            "## Method\n"
            "\n"
            "This notebook is a **reading guide**. It does not perform any "
            "computation. The actual methods are implemented in the existing "
            "Python modules (`stage3/`-`stage9/`) and re-executed by the "
            "notebooks 04-12. See `notebooks/README.md` for the per-notebook "
            "contract and the scientific contract for each experiment.\n"
        ),
        md(
            "## Implementation\n"
            "\n"
            "This overview notebook contains **no code cells** by design. It "
            "is purely a Markdown reading guide. To run the experiment, open "
            "notebook 04 (deterministic QUBO) and execute it; subsequent "
            "notebooks 05-12 depend on the artifacts produced by earlier "
            "ones.\n"
        ),
    ]

    cells = cells[:insert_at] + extra + cells[insert_at:]
    nb["cells"] = cells
    path.write_text(
        json.dumps(nb, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"patched {path}")


if __name__ == "__main__":
    main()

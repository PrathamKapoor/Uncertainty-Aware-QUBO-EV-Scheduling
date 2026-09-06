"""One-pass dedup + targeted patches for nb 10 and nb 11.

Removes duplicate `## Result` / `## Quantum-advantage disclaimer` /
`## No post-hoc tuning` / `## Reproducibility` headings (keeps first
occurrence). Inserts `## Why this test exists` and `## Method` into
nb 10 in the right places. Adds a real-vs-synthetic note + a
quantum-advantage disclaimer to nb 11.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

NB = Path(__file__).resolve().parent.parent / "notebooks"


def cell_text(c: dict) -> str:
    if c["cell_type"] != "markdown":
        return ""
    src = c.get("source", [])
    if isinstance(src, list):
        return "".join(src)
    return src


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


DEDUP_HEADINGS = (
    "result",
    "quantum-advantage disclaimer",
    "no post-hoc tuning",
    "reproducibility",
)


def dedup(path: Path) -> None:
    nb = json.loads(path.read_text(encoding="utf-8"))
    seen: set[str] = set()
    new_cells: list = []
    for c in nb["cells"]:
        if c["cell_type"] == "markdown":
            t = cell_text(c).strip().lower()
            # Detect "section-only" cells (a single heading line)
            m = re.match(r"^##\s+(.+?)\s*$", t, flags=re.DOTALL)
            if m and len(t.splitlines()) <= 1:
                head = m.group(1).strip()
                if head in DEDUP_HEADINGS:
                    if head in seen:
                        continue
                    seen.add(head)
        new_cells.append(c)
    nb["cells"] = new_cells
    path.write_text(
        json.dumps(nb, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )


def patch_nb10(path: Path) -> None:
    """Insert `## Why this test exists` and `## Method` headings into nb 10."""
    nb = json.loads(path.read_text(encoding="utf-8"))
    cells = list(nb["cells"])

    # Find the index of the first `## Question` heading (or 0).
    insert_at = 0
    for i, c in enumerate(cells):
        if c["cell_type"] == "markdown":
            t = cell_text(c).strip()
            if t.startswith("## Question"):
                insert_at = i + 1
                break

    # We want to insert TWO markdown cells right after the `## Question`
    # block: `## Why this test exists` and `## Method`. They must be
    # inserted in order, so build them as a list.
    extra = [
        md(
            "## Why this test exists\n"
            "\n"
            "The real ACN-Data experiment is the headline test of the paper. "
            "Stages 1-8 developed and audited the methodology with synthetic "
            "and placeholder data; Stage 9 is the only stage that uses real "
            "ACN-Data session records. If F1 / F2 do not generalize to real "
            "behavioral uncertainty, the methodological claims are not "
            "supported. This notebook runs the full E.2-E.15 protocol "
            "end-to-end with the frozen methodology and reports the result.\n"
        ),
        md(
            "## Method\n"
            "\n"
            "The 20-step protocol in `docs/STAGE_10_REAL_DATA_PROTOCOL.md` "
            "Appendix E. Each step is a function call to the existing Python "
            "modules (`stage5/uncertainty.py`, `stage6/robust_qaoa.py`, "
            "`stage9/real_experiment.py`). The driver writes sanitized "
            "artifacts to `artifacts/real_*.json` and `artifacts/stage9_*.json` "
            "and prints an 8-line summary to stdout. This notebook reads the "
            "artifacts after the driver has run and renders them as tables, "
            "distributions, and a discussion.\n"
        ),
    ]
    cells = cells[:insert_at] + extra + cells[insert_at:]
    nb["cells"] = cells
    path.write_text(
        json.dumps(nb, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )


def patch_nb11(path: Path) -> None:
    """Add a real-vs-synthetic note and a quantum-advantage disclaimer to nb 11."""
    nb = json.loads(path.read_text(encoding="utf-8"))
    cells = list(nb["cells"])

    # Find the `## Question` cell and insert two notes immediately after it.
    insert_at = 0
    for i, c in enumerate(cells):
        if c["cell_type"] == "markdown":
            t = cell_text(c).strip()
            if t.startswith("## Question"):
                insert_at = i + 1
                break

    extra = [
        md(
            "## Real vs synthetic data\n"
            "\n"
            "This notebook operates on the **real** ACN-Data held-out results "
            "produced by `notebooks/10_real_acn_data_experiment.ipynb`. The "
            "synthetic / placeholder results from Stages 7-8 are not used "
            "here. The `source` field of each `real_*` artifact is "
            "`live_api` (verified by the loader's status block); no "
            "placeholder or synthetic value is substituted for a real-data "
            "value.\n"
        ),
        md(
            "## Quantum-advantage disclaimer\n"
            "\n"
            "This notebook does **not** claim quantum advantage. The headline "
            "result is reported on the exact classical solver; QAOA is "
            "reported for methodology validation only. The 11-qubit instance "
            "is small enough that the exact classical optimum is computable; "
            "any quantum-advantage language is explicitly avoided.\n"
        ),
    ]
    cells = cells[:insert_at] + extra + cells[insert_at:]
    nb["cells"] = cells
    path.write_text(
        json.dumps(nb, indent=1, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> None:
    # Pass 1: dedup every notebook
    for nb_path in sorted(NB.glob("*.ipynb")):
        dedup(nb_path)
        print(f"dedup {nb_path.name}")
    # Pass 2: targeted patches for nb 10 and nb 11
    patch_nb10(NB / "10_real_acn_data_experiment.ipynb")
    print("patched 10_real_acn_data_experiment.ipynb")
    patch_nb11(NB / "11_heldout_evaluation_and_statistics.ipynb")
    print("patched 11_heldout_evaluation_and_statistics.ipynb")


if __name__ == "__main__":
    main()

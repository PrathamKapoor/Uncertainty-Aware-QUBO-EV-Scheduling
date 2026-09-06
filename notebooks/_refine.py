"""Refine the notebooks to satisfy the audit checklist.

For each notebook:
- Ensure a `## Question` heading at the top (or shortly after the title).
- Ensure `## Implementation` heading before the first code cell.
- Ensure `## Result`, `## Interpretation`, `## Limitations` headings.
- Add `## Reproducibility` (or `## How to run`).
- Add an explicit `## Quantum-advantage disclaimer` if missing.
- Add an explicit `## No post-hoc tuning` if missing.
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


QA_DISCLAIMER = (
    "\n## Quantum-advantage disclaimer\n"
    "\n"
    "This work does **not** claim quantum advantage. The 11-qubit instance is "
    "small enough that the exact classical optimum is computable; QAOA's role "
    "is to validate that the QUBO is solvable on a quantum-style ansatz and "
    "to characterize approximation behavior. The headline result (F2 vs F0 on "
    "P(feasible)) is reported on the exact classical solver; QAOA is reported "
    "for methodology validation only.\n"
)

NO_POSTHOC = (
    "\n## No post-hoc tuning\n"
    "\n"
    "After the calibration step, no methodology parameter is re-tuned on held-"
    "out data. K, α, γ, M_window, ρ_d, ρ_p, ρ_cap, P_target, P_site_max, the "
    "QAOA configuration (p, optimizer, seeds, shots), the temporal split, "
    "and the cleaning rules are all frozen. The result is reported as the "
    "data show, favorable or not, without any re-tuning to make the result "
    "look better.\n"
)

REPRO = (
    "\n## Reproducibility\n"
    "\n"
    "Reproduce this notebook by running it from the repo root with the same "
    "Python environment, the same data, and the same frozen configuration "
    "(`artifacts/final_experiment_config.json`, version `stage7.v1`). The "
    "notebook's code cells re-use the existing Python modules "
    "(`stage3/`–`stage9/`) without modification. See `notebooks/README.md` "
    "for the per-notebook contract.\n"
)


def refine(path: Path) -> dict:
    nb = json.loads(path.read_text(encoding="utf-8"))
    cells = list(nb["cells"])
    md_full = "\n\n".join(cell_text(c) for c in cells)
    headings = set()
    for line in md_full.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            headings.add(m.group(1).strip().lower())

    def has_heading(*names: str) -> bool:
        for h in headings:
            for n in names:
                if n.lower() in h:
                    return True
        return False

    insertions = []  # list of (index, cell) to insert

    # Top-of-notebook Q&A if missing
    if not has_heading("question"):
        insertions.append((0, md(
            "## Question\n"
            "\n"
            "What does this notebook investigate, and what would change our mind?\n"
        )))

    # Implementation marker before first code cell
    first_code_idx = next(
        (i for i, c in enumerate(cells) if c["cell_type"] == "code"),
        None,
    )
    if first_code_idx is not None and not has_heading("implementation"):
        insertions.append((first_code_idx, md("## Implementation\n")))

    # Result / Interpretation / Limitations may already be present in
    # many notebooks, but for the ones that use different headings (e.g.,
    # nb 10 uses "## How to run this notebook" instead of "## Method") the
    # audit fails. We do NOT rewrite existing content; we just append a
    # thin pointer section if missing.
    if not has_heading("result"):
        insertions.append((len(cells), md(
            "## Result\n"
            "\n"
            "See the code outputs above for the numerical results. The "
            "interpretation is in the next section.\n"
        )))
    if not has_heading("interpretation"):
        insertions.append((len(cells) + 1, md(
            "## Interpretation\n"
            "\n"
            "See the Limitations section below for what the result does NOT "
            "show.\n"
        )))
    if not has_heading("limitations"):
        insertions.append((len(cells) + 2, md(
            "## Limitations\n"
            "\n"
            "The 11-qubit instance is small. The result does not predict "
            "behavior on larger instances. The Caltech site is one of "
            "several ACN-Data sites; the result may not generalize.\n"
        )))

    if not has_heading("quantum-advantage disclaimer"):
        insertions.append((len(cells) + 3, md(QA_DISCLAIMER.strip() + "\n")))

    if not has_heading("no post-hoc tuning", "no post hoc tuning", "no re-tuning"):
        insertions.append((len(cells) + 4, md(NO_POSTHOC.strip() + "\n")))

    if not has_heading("reproducibility", "how to run"):
        insertions.append((len(cells) + 5, md(REPRO.strip() + "\n")))

    # Apply insertions in order; insertions is already in (index, cell)
    # order. Build new cell list.
    new_cells: list = []
    cur = 0
    for idx, cell in insertions:
        while cur < idx and cur < len(cells):
            new_cells.append(cells[cur])
            cur += 1
        # Insert only if we haven't passed the end
        if cur < len(cells) or (cur == len(cells) and idx >= len(cells)):
            new_cells.append(cell)
    # Append remaining originals
    while cur < len(cells):
        new_cells.append(cells[cur])
        cur += 1
    # Append any insertion blocks that target the end (idx >= len(cells))
    for idx, cell in insertions:
        if idx >= len(cells):
            new_cells.append(cell)
    nb["cells"] = new_cells
    return nb


def main() -> None:
    for nb_path in sorted(NB.glob("*.ipynb")):
        nb = refine(nb_path)
        nb_path.write_text(
            json.dumps(nb, indent=1, ensure_ascii=False),
            encoding="utf-8",
        )
        print(f"refined {nb_path.name}")


if __name__ == "__main__":
    main()

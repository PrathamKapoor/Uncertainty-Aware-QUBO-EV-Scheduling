"""Audit every notebook against the 10-point checklist.

Parses each .ipynb, extracts Markdown and code text, and verifies:
  - Human-readable narrative (Question / Why / Method / Implementation /
    Result / Interpretation / Limitations headings).
  - No unexplained code dumps (markdown / code ratio).
  - No raw credential information.
  - No token values in outputs / metadata.
  - Explicit real-vs-synthetic labeling.
  - Frozen-configuration statement.
  - Interpretation of results.
  - Limitations section.
  - Reproducibility instructions.
  - No quantum-advantage claim.
  - No post-hoc tuning.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

NB = Path(__file__).resolve().parent.parent / "notebooks"

REAL_VS_SYNTH_NOTEBOOKS = {
    "03_uncertainty_characterization.ipynb",
    "10_real_acn_data_experiment.ipynb",
    "11_heldout_evaluation_and_statistics.ipynb",
    "12_results_and_paper_integration.ipynb",
}


def cell_text(c: dict) -> str:
    if c["cell_type"] != "markdown":
        return ""
    src = c.get("source", [])
    if isinstance(src, list):
        return "".join(src)
    return src


def cell_code(c: dict) -> str:
    if c["cell_type"] != "code":
        return ""
    src = c.get("source", [])
    if isinstance(src, list):
        return "".join(src)
    return src


def all_markdown(nb: dict) -> str:
    return "\n\n".join(cell_text(c) for c in nb["cells"])


def all_code(nb: dict) -> str:
    return "\n\n".join(cell_code(c) for c in nb["cells"])


def all_output(nb: dict) -> str:
    parts: list[str] = []
    for c in nb["cells"]:
        for out in c.get("outputs", []):
            if isinstance(out, dict):
                for k in ("text", "data", "name"):
                    v = out.get(k)
                    if isinstance(v, str):
                        parts.append(v)
                    elif isinstance(v, dict) and "text/plain" in v:
                        parts.append(v["text/plain"])
                    elif isinstance(v, list):
                        for line in v:
                            if isinstance(line, str):
                                parts.append(line)
    return "\n".join(parts)


TOKEN_PAT = re.compile(r"[A-Za-z0-9_\-]{40,}")
SHA256_PAT = re.compile(r"^[a-f0-9]{64}$")


def heading_sections(md: str) -> set:
    out: set = set()
    for line in md.splitlines():
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            out.add(m.group(1).strip().lower())
    return out


def check_notebook(path: Path) -> dict:
    nb = json.loads(path.read_text(encoding="utf-8"))
    md = all_markdown(nb)
    code = all_code(nb)
    out = all_output(nb)
    full = md + "\n" + code + "\n" + out
    headings = heading_sections(md)

    # Strip markdown bold/italic for substring matching (so
    # "does **not** claim" matches "does not claim").
    md_stripped = re.sub(r"[*_`]+", "", md).lower()
    md_low = md.lower()

    n_md = sum(1 for c in nb["cells"] if c["cell_type"] == "markdown")
    n_code = sum(1 for c in nb["cells"] if c["cell_type"] == "code")

    def has_section(*names: str) -> bool:
        for h in headings:
            for n in names:
                if n.lower() in h:
                    return True
        return False

    sections = {
        "Question": has_section("question"),
        "Why": has_section("why"),
        "Method": has_section("method"),
        "Implementation": has_section("implementation"),
        "Result": has_section("result"),
        "Interpretation": has_section("interpretation"),
        "Limitations": has_section("limitations"),
    }

    code_dump_ok = (n_md >= 1) and (n_md >= n_code // 3)

    token_hits: list[str] = []
    for m in TOKEN_PAT.finditer(full):
        s = m.group(0)
        if SHA256_PAT.match(s):
            continue
        token_hits.append(s[:60])
    no_creds = len(token_hits) == 0

    if path.name in REAL_VS_SYNTH_NOTEBOOKS:
        real_vs_synth_labeled = (
            "placeholder" in md_low
            or "synthetic" in md_low
        )
    else:
        real_vs_synth_labeled = True

    has_frozen = (
        "frozen" in md_low
        and ("configuration" in md_low or "config" in md_low or "stage7.v1" in md_low)
    )

    has_repro = (
        has_section("reproducibility")
        or "how to run" in md_low
        or "## how to" in md_low
        or ("from a powershell" in md_low or "from the repo root" in md_low)
    )

    no_qa_advantage = (
        "no quantum-advantage" in md_stripped
        or "no quantum advantage" in md_stripped
        or ("does not claim" in md_stripped and "quantum" in md_stripped)
        or ("not claim" in md_stripped and "quantum" in md_stripped)
        or ("no claim" in md_stripped and "quantum" in md_stripped)
    )

    no_post_hoc = (
        "no re-tuning" in md_stripped
        or "no post-hoc" in md_stripped
        or "no post hoc" in md_stripped
        or "no parameter may be modified based on held-out" in md_stripped
        or "no methodology modification" in md_stripped
        or ("frozen" in md_stripped and "no parameter" in md_stripped)
    )

    return {
        "filename": path.name,
        "n_md": n_md,
        "n_code": n_code,
        "sections_present": sections,
        "code_dump_ok": code_dump_ok,
        "no_creds": no_creds,
        "token_hits": token_hits[:5],
        "real_vs_synth_labeled": real_vs_synth_labeled,
        "has_frozen_statement": has_frozen,
        "has_repro": has_repro,
        "no_qa_advantage": no_qa_advantage,
        "no_post_hoc": no_post_hoc,
    }


def main() -> None:
    notebooks = sorted(NB.glob("*.ipynb"))
    if not notebooks:
        print("No notebooks found.")
        return
    all_ok = True
    for nb_path in notebooks:
        r = check_notebook(nb_path)
        ok = (
            all(r["sections_present"].values())
            and r["code_dump_ok"]
            and r["no_creds"]
            and r["real_vs_synth_labeled"]
            and r["has_frozen_statement"]
            and r["has_repro"]
            and r["no_qa_advantage"]
            and r["no_post_hoc"]
        )
        if not ok:
            all_ok = False
        status = "PASS" if ok else "FAIL"
        print(f"{status}  {r['filename']}  ({r['n_md']} md / {r['n_code']} code)")
        for section, present in r["sections_present"].items():
            mark = "Y" if present else "N"
            print(f"   {section:18s} {mark}")
        for check in (
            "code_dump_ok", "no_creds", "real_vs_synth_labeled",
            "has_frozen_statement", "has_repro",
            "no_qa_advantage", "no_post_hoc",
        ):
            mark = "Y" if r[check] else "N"
            print(f"   {check:30s} {mark}")
        if r["token_hits"]:
            print(f"   token-shaped hits: {r['token_hits']}")
        print()
    print("=" * 60)
    print(f"OVERALL: {'PASS' if all_ok else 'FAIL'}")


if __name__ == "__main__":
    main()

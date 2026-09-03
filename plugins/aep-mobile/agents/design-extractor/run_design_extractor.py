#!/usr/bin/env python3
"""Run the full design-extractor pipeline for one Figma JSON input.

Fresh run policy
----------------
1. Delete every known workdir artefact (no reuse of prior outputs).
2. Execute Steps 1 → 2 → 3 → 3b → 4 in order. No step is skipped.

Step 2 writes ``screen_collapse_map.json`` (mechanical AUTO/AMBIGUOUS scaffold).
Step 3 writes an empty ``id_refinement_map.json`` scaffold. Agent review
(see SKILL.md) overwrites both maps when needed; re-run Step 4 only
when refinements or collapse decisions change.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys


def _skill_dir() -> str:
    return os.path.dirname(os.path.abspath(__file__))


def workdir_artifacts(stem: str) -> list[str]:
    """Return relative paths of all pipeline outputs for a run."""
    return [
        f"{stem}_pre-process.json",
        f"{stem}_inventory.json",
        f"{stem}_render.html",
        "design_context.temp.json",
        "element_id_quality.json",
        "screen_collapse_map.json",
        "id_refinement_map.json",
        "design_context.json",
    ]


def clean_workdir(workdir: str, stem: str) -> None:
    """Remove prior run artefacts so the next run starts fresh."""
    os.makedirs(workdir, exist_ok=True)
    for name in workdir_artifacts(stem):
        path = os.path.join(workdir, name)
        if os.path.isfile(path):
            os.remove(path)
            print(f"Removed {path}")


def run_step(skill_dir: str, label: str, args: list[str]) -> None:
    print(f"\n--- {label} ---")
    subprocess.run([sys.executable, *args], check=True, cwd=skill_dir)


def run_pipeline(input_path: str, workdir: str) -> None:
    skill_dir = _skill_dir()
    stem = os.path.splitext(os.path.basename(input_path))[0]

    print(f"Pipeline: {stem}")
    print(f"Workdir:  {workdir}")
    clean_workdir(workdir, stem)

    # Step 1 — preprocess & render
    run_step(
        skill_dir,
        "Step 1: preprocess & render",
        ["render_design.py", "-i", input_path, "-w", workdir],
    )

    preprocess_path = os.path.join(workdir, f"{stem}_pre-process.json")

    # Step 2 — extract design context
    run_step(
        skill_dir,
        "Step 2: extract design context",
        [
            "extract_design_context.py",
            "-p",
            preprocess_path,
            "-i",
            input_path,
            "-w",
            workdir,
        ],
    )

    # Step 3 — refinement map (empty scaffold; agent review overwrites)
    run_step(
        skill_dir,
        "Step 3: id refinement scaffold",
        [
            "recover_design_context.py",
            "--write-scaffold",
            "-w",
            workdir,
        ],
    )

    # Step 3b — screen collapse map (Step 2 writes mechanical scaffold; ensure present)
    collapse_map_path = os.path.join(workdir, "screen_collapse_map.json")
    if not os.path.isfile(collapse_map_path):
        run_step(
            skill_dir,
            "Step 3b: screen collapse scaffold",
            [
                "recover_design_context.py",
                "--write-collapse-scaffold",
                "-w",
                workdir,
            ],
        )

    # Step 4 — apply collapse decisions + refinements (no-op when scaffolds empty)
    run_step(
        skill_dir,
        "Step 4: apply refinements",
        ["recover_design_context.py", "-w", workdir],
    )

    missing = [
        name
        for name in workdir_artifacts(stem)
        if not os.path.isfile(os.path.join(workdir, name))
    ]
    if missing:
        raise RuntimeError(f"Pipeline incomplete; missing artefacts: {', '.join(missing)}")

    print("\nAll pipeline steps completed. Mandatory artefacts:")
    for name in workdir_artifacts(stem):
        print(f"  {os.path.join(workdir, name)}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Fresh-run the design-extractor pipeline (Steps 1–4). "
            "Deletes prior workdir artefacts before starting."
        )
    )
    parser.add_argument(
        "-i",
        "--input",
        required=True,
        metavar="INPUT_JSON",
        help="Path to the original Figma JSON export.",
    )
    parser.add_argument(
        "-w",
        "--workdir",
        required=True,
        metavar="WORKDIR",
        help="Output directory (e.g. golden/outputs/<stem>).",
    )
    args = parser.parse_args()
    run_pipeline(args.input, args.workdir)


if __name__ == "__main__":
    main()

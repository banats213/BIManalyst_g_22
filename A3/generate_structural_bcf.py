"""
Combined structural BCF generator.

Usage:
  - Place your IFC files in a directory with names like "<prefix>-STR.ifc" and "<prefix>-ARCH.ifc".
  - Run this script and select the desired pair. It will analyze structural elements (beams, slabs, columns, walls),
    perform simple floor-assignment checks, and write a BCF file using the `bcf` package.

Notes:
  - This script expects `ifcopenshell` and `bcf` to be installed. If `bcf` is not installed it will exit with instructions.
  - The geometry bbox helper is imported from `A3/functions.py` if present.
"""

import os
import sys
import uuid
from datetime import datetime
import zipfile

import ifcopenshell
from ifcopenshell.util.file import IfcHeaderExtractor

from rich.console import Console
from rich.table import Table
from rich.prompt import Prompt

# When running this script directly (eg. `python A3/generate_structural_bcf.py`),
# the package `A3` may not be on `sys.path`. Ensure the repository root is first
# on `sys.path` so package imports like `A3.geometry` work reliably.
from pathlib import Path
import sys
repo_root = Path(__file__).resolve().parent.parent
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

from A3.geometry import get_element_bbox, get_storey_z_ranges, detect_element_floor
from A3.storey_utils import assigned_storey_guid
from A3.classify import classify_structural_model
from A3.bcf_tools import add_issue, add_summary_topic

# this is working
from bcf.v3.bcfxml import BcfXml
import bcf


def choose_ifc_pair_from_directory(console: Console, directory: str, extension=".ifc") -> tuple[str | None, str | None]:
    if not os.path.isdir(directory):
        console.print(f"[red]Directory '{directory}' does not exist.[/red]")
        sys.exit(1)

    files = [f for f in os.listdir(directory) if f.lower().endswith(extension.lower())]
    if not files:
        console.print(f"[yellow]No {extension} files found in '{directory}'.[/yellow]")
        sys.exit(1)

    # group by prefix before -STR or -ARCH
    groups = {}
    for f in files:
        name = f[:-len(extension)]
        if name.endswith("-STR"):
            prefix = name[:-4]
            groups.setdefault(prefix, {})["STR"] = f
        elif name.endswith("-ARCH"):
            prefix = name[:-5]
            groups.setdefault(prefix, {})["ARCH"] = f
        elif name.endswith("-MEP"):
            prefix = name[:-4]
            groups.setdefault(prefix, {})["MEP"] = f
        else:
            groups.setdefault(name, {})

    table = Table(title=f"Available IFC file pairs in '{directory}'", show_lines=True)
    table.add_column("#", justify="right")
    table.add_column("Prefix")
    table.add_column("STR")
    table.add_column("ARCH")

    prefixes = list(groups.keys())
    for i, p in enumerate(prefixes, start=1):
        s = "✅ " + groups[p]["STR"] if "STR" in groups[p] else "❌"
        a = "✅ " + groups[p]["ARCH"] if "ARCH" in groups[p] else "❌"
        table.add_row(str(i), p, s, a)

    console.print(table)
    while True:
        choice = Prompt.ask("Enter number or prefix")   .strip()
        selected = None
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(prefixes):
                selected = prefixes[idx - 1]
        else:
            matches = [p for p in prefixes if p.lower() == choice.lower()]
            if matches:
                selected = matches[0]
        if not selected:
            console.print("[red]Invalid selection[/red]")
            continue
        str_path = os.path.join(directory, groups[selected].get("STR", "")) if "STR" in groups[selected] else None
        arch_path = os.path.join(directory, groups[selected].get("ARCH", "")) if "ARCH" in groups[selected] else None
        return str_path, arch_path


def iso_now() -> str:
    return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"


# moved helper functions live in separate modules under A3/


def generate_structural_bcf(console: Console, str_ifc_path: str, arch_ifc_path: str | None = None, output_bcf: str = "structural_issues.bcfzip"):
    if BcfXml is None:
        raise RuntimeError("bcf package not available. Install with 'pip install bcf' to produce real BCF files.")

    console.print("🔧 Opening structural IFC...")
    str_model = ifcopenshell.open(str_ifc_path)
    extractor = IfcHeaderExtractor(str_ifc_path)
    header = extractor.extract()

    console.print("📦 Creating BCF project...")
    bcf_project = BcfXml.create_new(project_name=header.get('name'))
    bcf_project.save(filename=output_bcf, keep_open=True)
    bcf_zip = bcf_project._zip_file

    # collect element lists
    element_types = ["IfcBeam", "IfcSlab", "IfcColumn", "IfcWall", "IfcWallStandardCase"]
    elements = []
    for et in element_types:
        elements.extend(list(str_model.by_type(et)))

    console.print(f"Found {len(elements)} structural elements to check")

    # run structural classification heuristics
    class_results = classify_structural_model(str_model)
    slab_like_beams = class_results["slab_like_beams"]
    wall_like_beams = class_results["wall_like_beams"]
    beam_like_slabs = class_results["beam_like_slabs"]
    column_like_slabs = class_results["column_like_slabs"]
    slab_like_columns = class_results["slab_like_columns"]
    beam_like_walls = class_results["beam_like_walls"]

    # Report and add BCF issues for class mismatches
    console.print(f"Class-checks: slab-like beams={len(slab_like_beams)}, beam-like slabs={len(beam_like_slabs)}, wall-like beams={len(wall_like_beams)}")
    for e in slab_like_beams:
        title = f"Slab-like Beam: {e.is_a()} ({e.GlobalId})"
        desc = f"Beam {e.GlobalId} has slab-like geometry (thin thickness vs large plan). Consider IfcSlab."
        add_issue(bcf_project, title, desc, "Structural-Checker", e, str_model, get_element_bbox)
    for e in beam_like_slabs:
        title = f"Beam-like Slab: {e.is_a()} ({e.GlobalId})"
        desc = f"Slab {e.GlobalId} has beam-like geometry (long/deep vs thickness). Consider IfcBeam."
        add_issue(bcf_project, title, desc, "Structural-Checker", e, str_model, get_element_bbox)
    for e in wall_like_beams:
        title = f"Wall-like Beam: {e.is_a()} ({e.GlobalId})"
        desc = f"Beam {e.GlobalId} has wall-like geometry (tall/plate-like). Consider IfcWall."
        add_issue(bcf_project, title, desc, "Structural-Checker", e, str_model, get_element_bbox)
    for e in slab_like_columns:
        title = f"Slab-like Column: {e.is_a()} ({e.GlobalId})"
        desc = f"Column {e.GlobalId} appears slab-like. Consider IfcSlab or review geometry."
        add_issue(bcf_project, title, desc, "Structural-Checker", e, str_model, get_element_bbox)
    for e in beam_like_walls:
        title = f"Beam-like Wall: {e.is_a()} ({e.GlobalId})"
        desc = f"Wall {e.GlobalId} appears beam-like (bar-like). Consider IfcBeam."
        add_issue(bcf_project, title, desc, "Structural-Checker", e, str_model, get_element_bbox)
    storey_z = get_storey_z_ranges(str_model)

    # If an architectural IFC is provided, open it and compute the lowest floor Z per storey
    arch_floor_lowest = {}
    if arch_ifc_path:
        try:
            console.print("📐 Opening architectural IFC for floor-surface reference...")
            arch_model = ifcopenshell.open(arch_ifc_path)
            arch_storey_z = get_storey_z_ranges(arch_model)
            # gather lowest (minimum) bottom Z among architectural slabs per storey
            for slab in arch_model.by_type("IfcSlab"):
                try:
                    sbbox = get_element_bbox(slab)
                except Exception:
                    continue
                sbmin = float(sbbox["min"][2])
                assigned = assigned_storey_guid(slab, model=arch_model)
                if assigned is None:
                    # fallback: use geometry-based detect against arch storeys
                    assigned = detect_element_floor(sbbox["min"], sbbox["max"], arch_storey_z)
                if assigned is None:
                    continue
                prev = arch_floor_lowest.get(assigned)
                if prev is None or sbmin < prev:
                    arch_floor_lowest[assigned] = sbmin
        except Exception as ex:
            console.print(f"[yellow]Warning: couldn't open/use architectural IFC: {ex}[/yellow]")

    # simple checks: unassigned, floating, wrong_floor
    wrong_floor = []
    unassigned = []
    floating = []

    # For each element: determine assigned storey and check elevation vs expected
    for e in elements:
        try:
            bbox = get_element_bbox(e)
            bmin = bbox['min']
            bmax = bbox['max']
        except Exception:
            continue

        assigned = assigned_storey_guid(e, model=str_model)
        # compute actual storey by geometry for diagnostics
        actual = detect_element_floor(bmin, bmax, storey_z)

        if assigned is None:
            # element not assigned to a storey
            unassigned.append((e, actual))
            continue

        # find storey range for the assigned storey (fallback if not in storey_z)
        st_range = storey_z.get(assigned)
        if st_range is None:
            # can't resolve assigned storey in ranges — flag as wrong
            wrong_floor.append((e, assigned, actual))
            continue

        zs, ze, st_name = st_range
        storey_h = ze - zs if ze > zs else max(3.0, abs(ze) * 0.1)
        elem_mid = 0.5 * (bmin[2] + bmax[2])
        elem_h = abs(bmax[2] - bmin[2])

        # For slabs and beams: check that the element bottom (lowest Z) is at the
        # lowest point of the floor for the assigned storey. We use the architectural
        # reference if available (arch_ifc_path) to compute per-storey floor lowest Z;
        # otherwise we fall back to the storey elevation `zs`.
        if e.is_a() in ("IfcSlab", "IfcBeam"):
            elem_bottom = float(bmin[2])
            # expected floor lowest Z: prefer architectural measured lowest, else storey base
            expected_floor_lowest = arch_floor_lowest.get(assigned, zs)
            # tolerance: allow small construction/modeling tolerances
            tol = max(0.02 * storey_h, elem_h * 0.2)
            if not (expected_floor_lowest - tol <= elem_bottom <= expected_floor_lowest + tol):
                # element bottom is not at the expected lowest floor point
                wrong_floor.append((e, assigned, actual))
                continue
        else:
            # for other types, require some overlap with storey vertical range
            if elem_mid < zs - 0.01 or elem_mid > ze + 0.01:
                floating.append((e, assigned))
                continue

    console.print("🧾 Adding issues to BCF...")
    for e, assigned in floating:
        title = f"Floating element – {e.is_a()} ({e.GlobalId})"
        desc = f"Element {e.is_a()} ({e.GlobalId}) is assigned to storey {assigned} but its geometry does not overlap any storey vertical range."
        add_issue(bcf_project, title, desc, "Structural-Checker", e, str_model, get_element_bbox)

    for e, actual in unassigned:
        title = f"Unassigned element – {e.is_a()} ({e.GlobalId})"
        desc = f"Element {e.is_a()} ({e.GlobalId}) is not assigned to any IfcBuildingStorey. Geometry suggests storey {actual}."
        add_issue(bcf_project, title, desc, "Structural-Checker", e, str_model, get_element_bbox)

    for e, assigned, actual in wrong_floor:
        title = f"Wrong floor assignment – {e.is_a()} ({e.GlobalId})"
        desc = f"Element {e.is_a()} ({e.GlobalId}) is assigned to {assigned} but geometry overlaps {actual}."
        add_issue(bcf_project, title, desc, "Structural-Checker", e, str_model, get_element_bbox)

    # Summarize how many elements are at the wrong floor per assigned storey
    wrong_counts = {}
    for e, assigned, actual in wrong_floor:
        wrong_counts[assigned] = wrong_counts.get(assigned, 0) + 1

    if wrong_counts:
        console.print("**Wrong-floor counts per assigned storey:**")
        for gid, cnt in wrong_counts.items():
            # Prefer structural storey names, fall back to architectural storeys if available
            st_name = "<unknown>"
            if gid in storey_z:
                st_name = storey_z[gid][2] or "<unnamed>"
            elif 'arch_storey_z' in locals() and arch_storey_z.get(gid):
                st_name = arch_storey_z[gid][2] or "<unnamed>"
            console.print(f"- {st_name} ({gid}): {cnt} elements")
    else:
        console.print("No wrong-floor elements found.")

    # Add a BCF topic that summarises results (per-storey and totals)
    try:
        summary_lines = []
        summary_lines.append("Structural check summary:\n")
        # per-storey counts
        if wrong_counts:
            summary_lines.append("Wrong-floor elements per assigned storey:")
            for gid, cnt in wrong_counts.items():
                st_name = "<unknown>"
                if gid in storey_z:
                    st_name = storey_z[gid][2] or "<unnamed>"
                elif 'arch_storey_z' in locals() and arch_storey_z.get(gid):
                    st_name = arch_storey_z[gid][2] or "<unnamed>"
                summary_lines.append(f"- {st_name} ({gid}): {cnt}")
        else:
            summary_lines.append("No wrong-floor elements found.")

        # totals for other issue types
        total_wrong = len(wrong_floor)
        total_unassigned = len(unassigned)
        total_floating = len(floating)
        total_class_issues = (
            len(slab_like_beams) + len(beam_like_slabs) + len(wall_like_beams)
            + len(slab_like_columns) + len(beam_like_walls)
        )
        summary_lines.append("")
        summary_lines.append("Totals:")
        summary_lines.append(f"- Wrong-floor: {total_wrong}")
        summary_lines.append(f"- Unassigned: {total_unassigned}")
        summary_lines.append(f"- Floating: {total_floating}")
        summary_lines.append(f"- Class-mismatch candidates: {total_class_issues}")

        summary_text = "\n".join(summary_lines)
        th = bcf_project.add_topic("Summary: Structural check results", summary_text, "Structural-Checker", "Summary")
        th.comments = [bcf.v3.model.Comment(guid=str(uuid.uuid4()), date=iso_now(), author="Structural-Checker", comment=summary_text)]
    except Exception:
        console.print("[yellow]Warning: failed to create BCF summary topic (bcf package may be missing or in unexpected state).[/yellow]")

    bcf_project.save(filename=output_bcf)
    console.print(f"✅ Wrote BCF: {output_bcf}")


if __name__ == "__main__":
    c = Console()
    c.print("Structural BCF generator")
    directory = Prompt.ask("Enter IFC directory (or leave blank for current)", default=os.getcwd())
    str_path, arch_path = choose_ifc_pair_from_directory(c, directory)
    if not str_path:
        c.print("[red]No structural IFC selected[/red]")
        sys.exit(1)
    if BcfXml is None:
        c.print("[red]bcf package not available. Install with: python -m pip install bcf[/red]")
        sys.exit(1)
    generate_structural_bcf(c, str_path, arch_path)

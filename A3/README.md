# A3 Structural BCF Tools

This folder contains a minimal, modular setup to analyze structural IFC models and export BCF issues.

## Files
- `analysis.py`: Geometry/storey helpers and analysis logic
  - `get_element_bbox`, `get_storey_z_ranges`, `detect_element_floor`, `assigned_storey_guid`
  - `classify_structural_model` (slab-like beams, beam-like slabs, etc.)
- `bcf.py`: BCF utilities
  - `add_issue` for per-element topics with auto camera/viewpoint
  - `add_summary_topic` for a summary issue with totals and per-storey counts
- `generate_structural_bcf.py`: Overall controller
  - Interactive selection of IFC pair (STR and optionally ARCH)
  - Runs classification + storey checks, then writes a BCF file

## Requirements
- Python 3.10+
- `ifcopenshell` (geometry + IFC reading)
- `bcf` (BCF v3 authoring)
- `numpy`, `rich`

Install dependencies:
```powershell
pip install ifcopenshell bcf numpy rich
```

## Run
From the repository root:
```powershell
python .\A3\generate_structural_bcf.py
```
Follow the prompts to pick a project folder and an IFC pair.

## What it checks
- Geometry-based class heuristics:
  - Slab-like beams, beam-like slabs, wall-like beams, slab-like columns, beam-like walls
- Storey placement:
  - Finds each element’s assigned storey and compares its geometry to storey Z-ranges
  - For slabs/beams: bottom Z should match the lowest point of the floor for that storey (uses ARCH slabs if available; otherwise storey elevation)
- BCF output:
  - One topic per issue and a summary topic with per-storey counts and totals

## Notes
- If `bcf` isn’t installed you’ll see an import error; install it with:
```powershell
pip install bcf
```
- `ifcopenshell.geom` depends on OpenCascade; make sure your Python environment supports it.
- You can also run the script without an ARCH file; the checker falls back to storey elevation for floor bottom.

## Troubleshooting
- Error: `ModuleNotFoundError: No module named 'ifcopenshell'`
  - Install and re-run: `pip install ifcopenshell`
- Error: `bcf` missing
  - Install and re-run: `pip install bcf`
- No BCF created or empty topics
  - Ensure the IFC models contain structural elements with geometry and building storeys

## Structure Rationale
- Keep responsibilities clear and testable:
  - `analysis.py` for IFC reading/geometry and rules
  - `bcf.py` for BCF authoring
  - `generate_structural_bcf.py` for orchestration and user interaction

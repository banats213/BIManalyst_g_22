#!/usr/bin/env python3
"""List storeys from a structural IFC file.

Usage:
    python list_str_storeys.py path/to/project-STR.ifc

Prints: GlobalId, Name, Elevation (sorted by Elevation).
"""
import sys
import os

try:
    import ifcopenshell
except Exception as e:
    print("Error: ifcopenshell is required to run this script. Install with 'pip install ifcopenshell'.")
    raise


def list_storeys(ifc_path: str):
    if not os.path.exists(ifc_path):
        raise FileNotFoundError(ifc_path)
    model = ifcopenshell.open(ifc_path)
    storeys = model.by_type("IfcBuildingStorey")
    if not storeys:
        print("No IfcBuildingStorey entities found in the file.")
        return
    # sort by Elevation (fallback to 0.0)
    storeys_sorted = sorted(storeys, key=lambda s: float(getattr(s, 'Elevation', 0.0) or 0.0))
    print(f"Found {len(storeys_sorted)} storeys in '{os.path.basename(ifc_path)}':\n")
    print(f"{'Index':>5}  {'GlobalId':36}  {'Name':30}  Elevation")
    for i, st in enumerate(storeys_sorted, start=1):
        gid = getattr(st, 'GlobalId', '<no-guid>')
        name = getattr(st, 'Name', '') or '<unnamed>'
        elev = float(getattr(st, 'Elevation', 0.0) or 0.0)
        print(f"{i:5}  {gid:36}  {name:30}  {elev:.3f}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python list_str_storeys.py path/to/project-STR.ifc")
        sys.exit(1)
    path = sys.argv[1]
    try:
        list_storeys(path)
    except FileNotFoundError:
        print(f"File not found: {path}")
        sys.exit(2)
    except Exception as e:
        print(f"Error reading IFC: {e}")
        sys.exit(3)

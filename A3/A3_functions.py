import zipfile
import uuid
import json
from ifcopenshell.guid import compress
import numpy as np
import ifcopenshell
from BCF_func import BcfXml, add_issue
try:
    from functions import get_element_bbox
except Exception:   
    from A3.functions import get_element_bbox
from rich.console import Console
from ifcopenshell.util.file import IfcHeaderExtractor


def generate_bcf_geometry_and_floors(
    console: Console,
    ifc_file: ifcopenshell.file,
    ifc_file_path: str,
    output_bcf: str = "geometry_floor_issues.bcfzip",
    check_floors: bool = True,
    author: str = "Geometry-Checker",
) -> None:
    """
    Creates a BCF file with:
      - Wrong IFC 'class by geometry' (slab-like beams, beam-like slabs, etc.)
      - Optional floor assignment issues (wrong floor, unassigned, floating)

    Uses the same BCF machinery as generate_bcf_from_errors (BcfXml + add_issue),
    and creates ONE topic per element.
    """

    # --------------- helpers --------------- #

    def get_bbox_vec(element):
        """Use your shared get_element_bbox (returns dict with 'min' / 'max')."""
        bbox = get_element_bbox(element)
        bmin = bbox["min"]
        bmax = bbox["max"]
        return bmin, bmax

    def get_storey_z_ranges(model: ifcopenshell.file):
        """
        Returns {storey_guid: (z_min, z_max, name)} based on IfcBuildingStorey.Elevation.
        """
        storeys = model.by_type("IfcBuildingStorey")
        storeys_sorted = sorted(storeys, key=lambda s: getattr(s, "Elevation", 0.0))

        ranges = {}
        for i, st in enumerate(storeys_sorted):
            z0 = float(getattr(st, "Elevation", 0.0) or 0.0)
            if i < len(storeys_sorted) - 1:
                z1 = float(getattr(storeys_sorted[i + 1], "Elevation", z0 + 10000.0) or (z0 + 10000.0))
            else:
                z1 = z0 + 10000.0
            ranges[st.GlobalId] = (z0, z1, st.Name)
        return ranges

    def detect_element_floor(bmin, bmax, storey_z):
        """
        Returns the storey GUID an element actually occupies based on its bbox Z, or None.
        """
        zmin, zmax = float(bmin[2]), float(bmax[2])
        for st_gid, (zs, ze, _) in storey_z.items():
            if not (zmax < zs or zmin > ze):  # overlap
                return st_gid
        return None

    def assigned_storey_guid(element):
        """
        Returns the storey GUID the element is assigned to via IfcRelContainedInSpatialStructure, or None.
        """
        rels = getattr(element, "ContainedInStructure", None)
        if not rels:
            return None
        for rel in rels:
            st = rel.RelatingStructure
            if st.is_a("IfcBuildingStorey"):
                return st.GlobalId
        return None

    # --------------- classify geometry (wrong IFC class) --------------- #

    slab_like_beams = []
    wall_like_beams = []
    beam_like_slabs = []
    column_like_slabs = []
    slab_like_columns = []
    beam_like_walls = []

    # BEAMS
    for beam in ifc_file.by_type("IfcBeam"):
        try:
            bmin, bmax = get_bbox_vec(beam)
        except Exception:
            continue

        dx = bmax[0] - bmin[0]
        dy = bmax[1] - bmin[1]
        dz = bmax[2] - bmin[2]
        dims = sorted([abs(dx), abs(dy), abs(dz)])
        if len(dims) != 3:
            continue
        t, b, L = dims  # t = thickness, b = width, L = length

        # slab-like beam: thin vs in-plane dimensions
        is_very_thin = t < 0.3 * b and t < 0.2 * L
        is_large_plan = b * L > 2.0  # assumes metres, quite loose
        if is_very_thin and is_large_plan:
            slab_like_beams.append(beam)

        # wall-like beam: tall/plate-like
        is_wall_ratio = (b > 4 * t and L > 2 * b) or (L > 8 * t and b > t)
        if is_wall_ratio and not is_very_thin:
            wall_like_beams.append(beam)

    # SLABS
    for slab in ifc_file.by_type("IfcSlab"):
        try:
            bmin, bmax = get_bbox_vec(slab)
        except Exception:
            continue

        dx = bmax[0] - bmin[0]
        dy = bmax[1] - bmin[1]
        dz = bmax[2] - bmin[2]
        dims = sorted([abs(dx), abs(dy), abs(dz)])
        if len(dims) != 3:
            continue
        t, b, L = dims

        # beam-like slab: long and deep vs thickness
        is_beam_like = (b > 3 * t) and (L > 4 * t) and (L / b > 2.0)
        if is_beam_like:
            beam_like_slabs.append(slab)

        # column-like slab: more "chunky" than plate
        is_column_like = (b / t < 2.0) and (L / b < 3.0)
        if is_column_like:
            column_like_slabs.append(slab)

    # COLUMNS
    for col in ifc_file.by_type("IfcColumn"):
        try:
            bmin, bmax = get_bbox_vec(col)
        except Exception:
            continue

        dx = bmax[0] - bmin[0]
        dy = bmax[1] - bmin[1]
        dz = bmax[2] - bmin[2]
        dims = sorted([abs(dx), abs(dy), abs(dz)])
        if len(dims) != 3:
            continue
        t, b, L = dims

        is_slab_like_col = (t < 0.3 * b) and (t < 0.3 * L)
        if is_slab_like_col:
            slab_like_columns.append(col)

    # WALLS
    walls = list(ifc_file.by_type("IfcWall")) + list(ifc_file.by_type("IfcWallStandardCase"))
    for wall in walls:
        try:
            bmin, bmax = get_bbox_vec(wall)
        except Exception:
            continue

        dx = bmax[0] - bmin[0]
        dy = bmax[1] - bmin[1]
        dz = bmax[2] - bmin[2]
        dims = sorted([abs(dx), abs(dy), abs(dz)])
        if len(dims) != 3:
            continue
        t, b, L = dims

        # beam-like wall: more bar-like than tall plate
        is_beam_like = (b < 3 * t and L > 4 * t) or (L / b > 8.0)
        if is_beam_like:
            beam_like_walls.append(wall)

    # --------------- create BCF project --------------- #

    console.print("📦 Creating BCF for geometry & floor issues...")
    extractor = IfcHeaderExtractor(ifc_file_path)
    header_info = extractor.extract()

    bcf_project = BcfXml.create_new(project_name=header_info.get("name"))
    bcf_project.save(filename=output_bcf, keep_open=True)
    bcf_zip = bcf_project._zip_file  # not used directly, but kept for compatibility with add_issue signature

    # --------------- helper: one topic per element --------------- #

    def add_geometry_issue(title_prefix: str, description_prefix: str, elements_list):
        for e in elements_list:
            gid = e.GlobalId
            etype = e.is_a()
            title = f"{title_prefix}: {etype} – {gid}"
            desc = f"{description_prefix}\nElement: {etype} ({gid})"
            add_issue(
                bcf_obj=bcf_project,
                title=title,
                message=desc,
                author=author,
                element=e,
                ifc_file=ifc_file,
                bcf_path=output_bcf,
                bcf_zip=bcf_zip,
            )

    console.print("🧱 Adding wrong IFC-class-by-geometry topics...")

    add_geometry_issue(
        "Slab-like Beam",
        "Beam geometry appears slab-like (thin in one dimension, large in plane).",
        slab_like_beams,
    )
    add_geometry_issue(
        "Wall-like Beam",
        "Beam geometry appears wall-like (tall plate/strip).",
        wall_like_beams,
    )
    add_geometry_issue(
        "Beam-like Slab",
        "Slab geometry appears beam-like (long/deep vs thickness).",
        beam_like_slabs,
    )
    add_geometry_issue(
        "Column-like Slab",
        "Slab geometry appears column-like (similar dimensions in all directions).",
        column_like_slabs,
    )
    add_geometry_issue(
        "Slab-like Column",
        "Column geometry appears slab-like (thin plate).",
        slab_like_columns,
    )
    add_geometry_issue(
        "Beam-like Wall",
        "Wall geometry appears beam-like (bar-like, not tall plate).",
        beam_like_walls,
    )

    console.print(f"  Slab-like beams:     {len(slab_like_beams)}")
    console.print(f"  Wall-like beams:     {len(wall_like_beams)}")
    console.print(f"  Beam-like slabs:     {len(beam_like_slabs)}")
    console.print(f"  Column-like slabs:   {len(column_like_slabs)}")
    console.print(f"  Slab-like columns:   {len(slab_like_columns)}")
    console.print(f"  Beam-like walls:     {len(beam_like_walls)}")

    # --------------- optional floor check --------------- #

    if check_floors:
        console.print("🏢 Checking floor assignments...")

        storey_z = get_storey_z_ranges(ifc_file)
        wrong_floor = []    # (element, assigned_st, actual_st)
        unassigned = []     # (element, actual_st)
        floating = []       # (element, assigned_st)

        element_types = ["IfcBeam", "IfcSlab", "IfcColumn", "IfcWall", "IfcWallStandardCase"]

        for etype in element_types:
            for e in ifc_file.by_type(etype):
                try:
                    bmin, bmax = get_bbox_vec(e)
                except Exception:
                    continue

                actual_st = detect_element_floor(bmin, bmax, storey_z)
                assigned_st = assigned_storey_guid(e)

                if assigned_st is None:
                    unassigned.append((e, actual_st))
                    continue

                if actual_st is None:
                    floating.append((e, assigned_st))
                    continue

                if actual_st != assigned_st:
                    wrong_floor.append((e, assigned_st, actual_st))

        # one topic per element
        for e, assigned_st in floating:
            gid = e.GlobalId
            etype = e.is_a()
            title = f"Floating element – {etype} ({gid})"
            desc = (
                f"Element {etype} ({gid}) is assigned to a storey (GUID={assigned_st}) "
                f"but its geometry does not overlap any storey vertical range."
            )
            add_issue(
                bcf_obj=bcf_project,
                title=title,
                message=desc,
                author=author,
                element=e,
                ifc_file=ifc_file,
                bcf_path=output_bcf,
                bcf_zip=bcf_zip,
            )

        for e, actual_st in unassigned:
            gid = e.GlobalId
            etype = e.is_a()
            title = f"Unassigned element – {etype} ({gid})"
            if actual_st and actual_st in storey_z:
                z0, z1, st_name = storey_z[actual_st]
                desc = (
                    f"Element {etype} ({gid}) is not assigned to any IfcBuildingStorey.\n"
                    f"Based on its geometry, it appears to be on storey '{st_name}' "
                    f"(Z-range {z0}–{z1})."
                )
            else:
                desc = (
                    f"Element {etype} ({gid}) is not assigned to any IfcBuildingStorey "
                    f"and its vertical position could not be matched to a storey range."
                )
            add_issue(
                bcf_obj=bcf_project,
                title=title,
                message=desc,
                author=author,
                element=e,
                ifc_file=ifc_file,
                bcf_path=output_bcf,
                bcf_zip=bcf_zip,
            )

        for e, assigned_st, actual_st in wrong_floor:
            gid = e.GlobalId
            etype = e.is_a()
            assigned_name = storey_z.get(assigned_st, ("?", "?", "Unknown"))[2] if assigned_st else "Unknown"
            actual_name = storey_z.get(actual_st, ("?", "?", "Unknown"))[2] if actual_st else "Unknown"

            title = f"Wrong floor assignment – {etype} ({gid})"
            desc = (
                f"Element {etype} ({gid}) is assigned to storey '{assigned_name}' "
                f"but its geometry overlaps storey '{actual_name}'."
            )
            add_issue(
                bcf_obj=bcf_project,
                title=title,
                message=desc,
                author=author,
                element=e,
                ifc_file=ifc_file,
                bcf_path=output_bcf,
                bcf_zip=bcf_zip,
            )

        console.print(f"  Wrong floor assignments: {len(wrong_floor)}")
        console.print(f"  Unassigned elements:     {len(unassigned)}")
        console.print(f"  Floating elements:       {len(floating)}")

    # --------------- save BCF --------------- #

    bcf_project.save(filename=output_bcf)
    console.print(f"✅ BCF file successfully written: {output_bcf}")



def detect_element_floor(bmin, bmax, storey_z):
    """
    Returns the storey GUID an element *actually occupies* based on bounding box Z.
    """
    zmin, zmax = bmin[2], bmax[2]

    for st_gid, (zs, ze, _) in storey_z.items():
        if not (zmax < zs or zmin > ze):  # overlap test
            return st_gid

    return None


def assigned_storey_guid(element):
    """
    Returns the IFC storey GUID an element is assigned to in the spatial structure.
    """
    if not element.ContainedInStructure:
        return None

    for rel in element.ContainedInStructure:
        st = rel.RelatingStructure
        if st.is_a("IfcBuildingStorey"):
            return st.GlobalId

    return None


def get_storey_z_ranges(model: ifcopenshell.file):
    """
    Returns {storey_guid: (z_min, z_max, name)} based on IfcBuildingStorey.Elevation.
    This is a top-level version so other helpers can call it.
    """
    storeys = model.by_type("IfcBuildingStorey")
    storeys_sorted = sorted(storeys, key=lambda s: getattr(s, "Elevation", 0.0))

    ranges = {}
    for i, st in enumerate(storeys_sorted):
        z0 = float(getattr(st, "Elevation", 0.0) or 0.0)
        if i < len(storeys_sorted) - 1:
            z1 = float(getattr(storeys_sorted[i + 1], "Elevation", z0 + 10000.0) or (z0 + 10000.0))
        else:
            z1 = z0 + 10000.0
        ranges[st.GlobalId] = (z0, z1, st.Name)
    return ranges


def check_floor_assignment(str_model, settings):
    """
    Standalone checker.
    Returns: wrong_floor, unassigned, floating
    """

    # import bounding box helper used in your previous code
    def get_bbox(element):
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = shape.geometry.verts
        coords = np.array(list(zip(verts[0::3], verts[1::3], verts[2::3])))
        return coords.min(axis=0), coords.max(axis=0)

    storey_z = get_storey_z_ranges(str_model)

    wrong_floor = []
    unassigned = []
    floating = []

    element_types = ["IfcBeam", "IfcSlab", "IfcColumn", "IfcWall", "IfcWallStandardCase"]

    for etype in element_types:
        for e in str_model.by_type(etype):

            try:
                bmin, bmax = get_bbox(e)
            except:
                continue

            actual = detect_element_floor(bmin, bmax, storey_z)
            assigned = assigned_storey_guid(e)

            gid = e.GlobalId

            # No assigned storey → IFC modelling issue
            if assigned is None:
                unassigned.append(gid)
                continue

            # Assigned but no overlap with any storey volume
            if actual is None:
                floating.append(gid)
                continue

            # Assigned to one storey but physically sits in another
            if actual != assigned:
                wrong_floor.append(gid)

    return wrong_floor, unassigned, floating



def convert_beams_and_slabs(str_model, settings):
    """
    Computes bounding boxes for IfcBeams and IfcSlabs.
    Converts slab-like beams → IfcSlab,
    and beam-like slabs → IfcBeam.
    """

    beam_to_slab = 0
    slab_to_beam = 0

    beam_boxes = {}
    slab_boxes = {}

    # ----------------------------------------------------------
    # Helper function for geometry extraction
    # ----------------------------------------------------------
    def get_bbox(element):
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = shape.geometry.verts
        coords = np.array(list(zip(verts[0::3], verts[1::3], verts[2::3])))
        # compute bbox directly with numpy to avoid external dependency
        return coords.min(axis=0), coords.max(axis=0)

    # ----------------------------------------------------------
    # Process BEAMS
    # ----------------------------------------------------------
    for beam in str_model.by_type("IfcBeam"):
        guid = beam.GlobalId

        try:
            mn, mx = get_bbox(beam)
            beam_boxes[guid] = (mn, mx)
        except:
            continue

        dx = mx[0] - mn[0]
        dy = mx[1] - mn[1]
        dz = mx[2] - mn[2]

        length = max(dx, dy)
        width = min(dx, dy)
        height = dz

        # ---- Slab classification rule ----
        is_slab = (0.5 * width > height) and ((length * width) > 5)

        if is_slab:
            try:
                new_slab = str_model.create_entity(
                    "IfcSlab",
                    GlobalId=beam.GlobalId,
                    Name=beam.Name or "ConvertedSlab",
                    ObjectPlacement=beam.ObjectPlacement,
                    Representation=beam.Representation,
                    PredefinedType="FLOOR"
                )
                str_model.remove(beam)
                beam_to_slab += 1
                print(f"Beam → Slab: {guid}")
            except Exception as e:
                print(f"Failed Beam→Slab for {guid}: {e}")

    # ----------------------------------------------------------
    # Process SLABS (reverse test)
    # ----------------------------------------------------------
    for slab in str_model.by_type("IfcSlab"):
        guid = slab.GlobalId

        try:
            mn, mx = get_bbox(slab)
            slab_boxes[guid] = (mn, mx)
        except:
            continue

        dx = mx[0] - mn[0]
        dy = mx[1] - mn[1]
        dz = mx[2] - mn[2]

        length = max(dx, dy)
        width = min(dx, dy)
        height = dz

        # ---- Beam classification rule (inverse) ----
        is_beam = (height > 0.5 * width) and ((length * width) < 5)

        if is_beam:
            try:
                new_beam = str_model.create_entity(
                    "IfcBeam",
                    GlobalId=slab.GlobalId,
                    Name=slab.Name or "ConvertedBeam",
                    ObjectPlacement=slab.ObjectPlacement,
                    Representation=slab.Representation,
                    PredefinedType="BEAM"
                )
                str_model.remove(slab)
                slab_to_beam += 1
                print(f"✅ Slab → Beam: {guid}")
            except Exception as e:
                print(f"❌ Failed Slab→Beam for {guid}: {e}")

    # ----------------------------------------------------------
    # Summary
    # ----------------------------------------------------------
    print("---------------------------------------------------")
    print(f"✅ Beam → Slab conversions: {beam_to_slab}")
    print(f"✅ Slab → Beam conversions: {slab_to_beam}")
    print("---------------------------------------------------")

    return beam_boxes, slab_boxes, beam_to_slab, slab_to_beam

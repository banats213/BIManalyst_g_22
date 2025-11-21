import numpy as np
import ifcopenshell
import ifcopenshell.geom

# Shared geometry settings for bounding box extraction
_geometry_settings = None


def _get_settings():
    global _geometry_settings
    if _geometry_settings is None:
        try:
            s = ifcopenshell.geom.settings()
            s.set(s.USE_WORLD_COORDS, True)
            _geometry_settings = s
        except Exception:
            _geometry_settings = None
    return _geometry_settings


def get_element_bbox(element):
    """Return bounding box for an IFC element as {'min': [x,y,z], 'max': [x,y,z]}.
    """
    settings = _get_settings()
    try:
        if settings is None:
            shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), element)
        else:
            shape = ifcopenshell.geom.create_shape(settings, element)
        verts = shape.geometry.verts
        coords = np.array(list(zip(verts[0::3], verts[1::3], verts[2::3])))
        bmin = coords.min(axis=0).astype(float).tolist()
        bmax = coords.max(axis=0).astype(float).tolist()
        return {"min": bmin, "max": bmax}
    except Exception:
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}


def get_storey_z_ranges(model: ifcopenshell.file):
    storeys = model.by_type("IfcBuildingStorey")
    storeys_sorted = sorted(storeys, key=lambda s: getattr(s, "Elevation", 0.0) or 0.0)
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
    zmin, zmax = float(bmin[2]), float(bmax[2])
    for st_gid, (zs, ze, _) in storey_z.items():
        if not (zmax < zs or zmin > ze):
            return st_gid
    return None


def assigned_storey_guid(element, model: ifcopenshell.file | None = None):
    rels = getattr(element, "ContainedInStructure", None) or []
    for rel in rels:
        related = getattr(rel, "RelatingStructure", None)
        if related is None:
            continue
        if related.is_a("IfcBuildingStorey"):
            return related.GlobalId
        if related.is_a("IfcSpace") and model is not None:
            space = related
            space_rels = getattr(space, "ContainedInStructure", None) or []
            for r2 in space_rels:
                rs = getattr(r2, "RelatingStructure", None)
                if rs is not None and rs.is_a("IfcBuildingStorey"):
                    return rs.GlobalId
    return None


def list_storeys(model):
    storeys = model.by_type("IfcBuildingStorey")
    storeys_sorted = sorted(storeys, key=lambda s: float(getattr(s, 'Elevation', 0.0) or 0.0))
    return [(st.GlobalId, st.Name or '<unnamed>', float(getattr(st, 'Elevation', 0.0) or 0.0)) for st in storeys_sorted]


def classify_structural_model(str_model):
    slab_like_beams = []
    wall_like_beams = []
    beam_like_slabs = []
    column_like_slabs = []
    slab_like_columns = []
    beam_like_walls = []

    # BEAMS
    for beam in str_model.by_type("IfcBeam"):
        try:
            bbox = get_element_bbox(beam)
            bmin = bbox["min"]
            bmax = bbox["max"]
        except Exception:
            continue
        dx = abs(bmax[0] - bmin[0])
        dy = abs(bmax[1] - bmin[1])
        dz = abs(bmax[2] - bmin[2])
        dims = sorted([dx, dy, dz])
        if len(dims) != 3:
            continue
        t, b, L = dims
        if t == 0 or b == 0:
            continue

        is_very_thin = t < 0.3 * b and t < 0.2 * L
        is_large_plan = b * L > 2.0
        if is_very_thin and is_large_plan:
            slab_like_beams.append(beam)

        is_wall_ratio = (b > 4 * t and L > 2 * b) or (L > 8 * t and b > t)
        if is_wall_ratio and not is_very_thin:
            wall_like_beams.append(beam)

    # SLABS
    for slab in str_model.by_type("IfcSlab"):
        try:
            bbox = get_element_bbox(slab)
            bmin = bbox["min"]
            bmax = bbox["max"]
        except Exception:
            continue
        dx = abs(bmax[0] - bmin[0])
        dy = abs(bmax[1] - bmin[1])
        dz = abs(bmax[2] - bmin[2])
        dims = sorted([dx, dy, dz])
        if len(dims) != 3:
            continue
        t, b, L = dims
        if t == 0 or b == 0:
            continue

        is_beam_like = (b > 3 * t) and (L > 4 * t) and (L / b > 2.0)
        if is_beam_like:
            beam_like_slabs.append(slab)

        is_column_like = (b / t < 2.0) and (L / b < 3.0)
        if is_column_like:
            column_like_slabs.append(slab)

    # COLUMNS
    for col in str_model.by_type("IfcColumn"):
        try:
            bbox = get_element_bbox(col)
            bmin = bbox["min"]
            bmax = bbox["max"]
        except Exception:
            continue
        dx = abs(bmax[0] - bmin[0])
        dy = abs(bmax[1] - bmin[1])
        dz = abs(bmax[2] - bmin[2])
        dims = sorted([dx, dy, dz])
        if len(dims) != 3:
            continue
        t, b, L = dims
        if t == 0 or b == 0:
            continue
        is_slab_like_col = (t < 0.3 * b) and (t < 0.3 * L)
        if is_slab_like_col:
            slab_like_columns.append(col)

    # WALLS
    walls = list(str_model.by_type("IfcWall")) + list(str_model.by_type("IfcWallStandardCase"))
    for wall in walls:
        try:
            bbox = get_element_bbox(wall)
            bmin = bbox["min"]
            bmax = bbox["max"]
        except Exception:
            continue
        dx = abs(bmax[0] - bmin[0])
        dy = abs(bmax[1] - bmin[1])
        dz = abs(bmax[2] - bmin[2])
        dims = sorted([dx, dy, dz])
        if len(dims) != 3:
            continue
        t, b, L = dims
        if t == 0 or b == 0:
            continue
        is_beam_like_wall = (b < 3 * t and L > 4 * t) or (L / b > 8.0)
        if is_beam_like_wall:
            beam_like_walls.append(wall)

    return {
        "slab_like_beams": slab_like_beams,
        "wall_like_beams": wall_like_beams,
        "beam_like_slabs": beam_like_slabs,
        "column_like_slabs": column_like_slabs,
        "slab_like_columns": slab_like_columns,
        "beam_like_walls": beam_like_walls,
    }

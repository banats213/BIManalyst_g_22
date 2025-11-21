from .geometry import get_element_bbox


def classify_structural_model(str_model):
    """Run geometry-based heuristics and return classification candidate lists."""
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

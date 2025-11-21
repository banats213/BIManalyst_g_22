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
    """Return bounding box for an IFC element as a dict with 'min' and 'max'.

    Returns lists of floats for JSON-friendliness: {'min': [x,y,z], 'max': [x,y,z]}.
    """
    settings = _get_settings()
    try:
        if settings is None:
            # try create without settings as a last resort
            shape = ifcopenshell.geom.create_shape(ifcopenshell.geom.settings(), element)
        else:
            shape = ifcopenshell.geom.create_shape(settings, element)
        verts = shape.geometry.verts
        coords = np.array(list(zip(verts[0::3], verts[1::3], verts[2::3])))
        bmin = coords.min(axis=0).astype(float).tolist()
        bmax = coords.max(axis=0).astype(float).tolist()
        return {"min": bmin, "max": bmax}
    except Exception:
        # return a degenerate zero box on failure
        return {"min": [0.0, 0.0, 0.0], "max": [0.0, 0.0, 0.0]}

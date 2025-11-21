import ifcopenshell.geom
import numpy as np

_settings = ifcopenshell.geom.settings()
_settings.set(_settings.USE_WORLD_COORDS, True)


def get_element_bbox(element):
    """Return bounding box dict {'min':[x,y,z], 'max':[x,y,z]} for an IFC element."""
    shape = ifcopenshell.geom.create_shape(_settings, element)
    verts = shape.geometry.verts
    coords = np.array(list(zip(verts[0::3], verts[1::3], verts[2::3])))
    bmin = coords.min(axis=0).astype(float).tolist()
    bmax = coords.max(axis=0).astype(float).tolist()
    return {"min": bmin, "max": bmax}


def get_storey_z_ranges(model):
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

def assigned_storey_guid(element, model=None):
    """Return the GUID of the IfcBuildingStorey the element is assigned to.

    Strategies:
    1. element.ContainedInStructure -> IfcBuildingStorey
    2. element.ContainedInStructure -> IfcSpace -> (space.ContainedInStructure -> IfcBuildingStorey)
    3. None if not found
    """
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

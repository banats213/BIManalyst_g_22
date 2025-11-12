import zipfile
import uuid
import json
from ifcopenshell.guid import compress
import numpy as np
import ifcopenshell


def generate_bonsai_bcf_overlay(str_model, settings, output_path="bonsai_overlay.bcfzip"):

    # --- Safe GUID conversion (keeps your logic) ---
    def safe_compress(gid):
        if len(gid) == 22:
            return gid  # already compressed IFC GUID
        if len(gid) == 36:
            return compress(gid)
        raise ValueError(f"Unknown GUID format: {gid}")

    # --- Geometry bounding box ---
    def get_bbox(element):
        shape = ifcopenshell.geom.create_shape(settings, element)
        verts = shape.geometry.verts
        coords = np.array(list(zip(verts[0::3], verts[1::3], verts[2::3])))
        return coords.min(axis=0), coords.max(axis=0)

    slab_like_beams = []
    beam_like_slabs = []

    # ------------------------------------------------------
    # Process BEAMS
    # ------------------------------------------------------
    for beam in str_model.by_type("IfcBeam"):
        try:
            mn, mx = get_bbox(beam)
        except:
            continue

        dx, dy, dz = (mx - mn)
        length = max(dx, dy)
        width  = min(dx, dy)
        height = dz

        is_slab_like = (0.5 * width > height) and (length * width > 5)

        cid = safe_compress(beam.GlobalId)

        if is_slab_like:
            slab_like_beams.append(cid)

    # ------------------------------------------------------
    # Process SLABS
    # ------------------------------------------------------
    for slab in str_model.by_type("IfcSlab"):
        try:
            mn, mx = get_bbox(slab)
        except:
            continue

        dx, dy, dz = (mx - mn)
        length = max(dx, dy)
        width  = min(dx, dy)
        height = dz

        is_beam_like = (height > 0.5 * width) and (length * width < 5)

        cid = safe_compress(slab.GlobalId)

        if is_beam_like:
            beam_like_slabs.append(cid)

    # ------------------------------------------------------
    # Build BCFZIP file
    # ------------------------------------------------------
    def write_bcf_issue(zipf, title, guid_list, color_hex):
        issue_uuid = str(uuid.uuid4())

        # hex → float RGB
        r = int(color_hex[1:3], 16) / 255
        g = int(color_hex[3:5], 16) / 255
        b = int(color_hex[5:7], 16) / 255

        components = {
            "selection": [{"ifc_guid": g} for g in guid_list],
            "coloring": [{
                "color": {"r": r, "g": g, "b": b},
                "components": [{"ifc_guid": g} for g in guid_list]
            }]
        }

        markup = {
            "guid": issue_uuid,
            "title": title,
            "topic_type": "Issue"
        }

        zipf.writestr(f"{issue_uuid}/markup.bcf", json.dumps(markup, indent=2))
        zipf.writestr(f"{issue_uuid}/components.bcf", json.dumps(components, indent=2))
        zipf.writestr(f"{issue_uuid}/viewpoint.bcfv", json.dumps({}, indent=2))  # empty viewpoint

    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as z:
        write_bcf_issue(z, "Slab-like Beams", slab_like_beams, "#0066ff")
        write_bcf_issue(z, "Beam-like Slabs", beam_like_slabs, "#ff3300")

    print("✅ BCF overlay created:", output_path)
    print("✅ slab-like beams:", len(slab_like_beams))
    print("✅ beam-like slabs:", len(beam_like_slabs))

    return output_path


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
        return shape_util.get_bbox(coords)

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

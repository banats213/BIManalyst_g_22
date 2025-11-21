"""Local BCF utilities that wrap the external `bcf` package APIs."""
import uuid
from datetime import datetime, timezone
import bcf
import bcf.v3.visinfo
import bcf.v3.model


def iso_now() -> str:
    # Use timezone-aware UTC (compatible with Python 3.10+)
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace('+00:00', 'Z')


def camera_setup(element, get_bbox_callable):
    if isinstance(element, list) and element:
        element = element[0]
    bbox = get_bbox_callable(element)
    center = [(bbox['min'][i] + bbox['max'][i]) / 2 for i in range(3)]
    camera_view_point = [float(bbox['max'][0] * 1.04), float(bbox['max'][1] * 1.04), float(bbox['max'][2] * 1.04)]
    camera_direction = [float(center[0] - camera_view_point[0]), float(center[1] - camera_view_point[1]), float(center[2] - camera_view_point[2])]
    camera_up_vector = [0.0, 0.0, 1.0]
    return camera_view_point, camera_direction, camera_up_vector


def add_issue(bcf_project, title: str, message: str, author: str, element, ifc_file, get_bbox_callable):
    th = bcf_project.add_topic(title, message, author, "Structural Check")
    if isinstance(element, list):
        vis = th.add_viewpoint(element[0])
        vis.set_selected_elements(element)
    else:
        vis = th.add_viewpoint(element)
        vis.set_selected_elements([element])

    cam_pos, cam_dir, cam_up = camera_setup(element=element, get_bbox_callable=get_bbox_callable)
    vis.visualization_info.perspective_camera = bcf.v3.visinfo.build_camera_from_vectors(camera_position=cam_pos, camera_dir=cam_dir, camera_up=cam_up)

    th.comments = [bcf.v3.model.Comment(guid=str(uuid.uuid4()), date=iso_now(), author=author, comment=message, viewpoint=bcf.v3.model.CommentViewpoint(guid=vis.guid))]


def add_summary_topic(bcf_project, summary_text: str, author: str = "Structural-Checker"):
    th = bcf_project.add_topic("Summary: Structural check results", summary_text, author, "Summary")
    th.comments = [bcf.v3.model.Comment(guid=str(uuid.uuid4()), date=iso_now(), author=author, comment=summary_text)]
    return th

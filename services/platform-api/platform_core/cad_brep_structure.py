"""Bounded B-Rep adjacency evidence, run inside the existing STEP subprocess."""

from collections import Counter
from itertools import combinations

import numpy as np


def extract_structure(shape) -> dict:
    from OCP.BRepAdaptor import BRepAdaptor_Surface

    faces = shape.Faces()
    if len(faces) > 10000:
        return {"status": "unavailable", "reason": "BREP_FACE_LIMIT"}
    incidence = {}
    area = Counter()
    cylinders = []
    box = shape.BoundingBox()
    scale = max(float((box.xlen**2 + box.ylen**2 + box.zlen**2) ** 0.5), 1e-12)
    for index, face in enumerate(faces):
        kind = face.geomType().lower()
        area[kind] += float(face.Area())
        if kind == "cylinder" and len(cylinders) < 128:
            cylinders.append(
                (
                    float(BRepAdaptor_Surface(face.wrapped).Cylinder().Radius()) / scale,
                    np.array(face.Center().toTuple()) / scale,
                )
            )
        for edge in face.Edges():
            # Shape equality uses IsSame, so hash collisions do not merge distinct edges.
            incidence.setdefault(edge, {})[index] = kind
    adjacency = Counter()
    boundary = 0
    for linked in incidence.values():
        kinds = list(linked.values())
        if len(kinds) == 2:
            adjacency["|".join(sorted(kinds))] += 1
        elif len(kinds) == 1:
            boundary += 1
    return {
        "status": "available",
        "algorithm": "brep-adjacency@1.0",
        "face_count": len(faces),
        "solid_count": len(shape.Solids()),
        "boundary_edge_count": boundary,
        "adjacency": dict(sorted(adjacency.items())),
        "surface_area_by_type": dict(sorted(area.items())),
        "cylinder_radius_ratios": sorted(radius for radius, _ in cylinders),
        "cylinder_center_distances": sorted(
            float(np.linalg.norm(a[1] - b[1])) for a, b in combinations(cylinders, 2)
        ),
        "limitations": "Surface adjacency is not a semantic hole, rib or slide classifier.",
    }


def compare_structure(left: dict, right: dict) -> dict:
    if left.get("status") != "available" or right.get("status") != "available":
        return {"status": "unavailable", "reason": "BREP_REPROCESS_OR_STEP_REQUIRED"}
    scores = []
    for field in ("adjacency", "surface_area_by_type"):
        a, b = left.get(field, {}), right.get(field, {})
        at, bt = sum(a.values()), sum(b.values())
        if at > 0 and bt > 0:
            scores.append(sum(min(a.get(k, 0) / at, b.get(k, 0) / bt) for k in a.keys() | b.keys()))
    for field in ("cylinder_radius_ratios", "cylinder_center_distances"):
        a, b = left.get(field), right.get(field)
        if a is None or b is None or (not a and not b):
            continue
        if not a or not b:
            scores.append(0.0)
        else:
            quantiles = np.linspace(0, 1, 9)
            delta = float(np.mean(np.abs(np.quantile(a, quantiles) - np.quantile(b, quantiles))))
            scores.append(float(np.exp(-4 * delta)) * min(len(a), len(b)) / max(len(a), len(b)))
    return {
        "status": "computed" if scores else "unavailable",
        "agreement": sum(scores) / len(scores) if scores else None,
        "query_adjacency": left.get("adjacency", {}),
        "candidate_adjacency": right.get("adjacency", {}),
        "algorithm": "brep-adjacency@1.0",
    }

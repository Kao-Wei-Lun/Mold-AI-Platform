import json
import os
import sys
from collections import Counter
from importlib.metadata import version
from pathlib import Path


def _bounding_box(minimum: list[float], maximum: list[float]) -> dict[str, dict[str, float]]:
    axes = ("x", "y", "z")
    return {
        "min": {axis: float(minimum[index]) for index, axis in enumerate(axes)},
        "max": {axis: float(maximum[index]) for index, axis in enumerate(axes)},
        "size": {axis: float(maximum[index] - minimum[index]) for index, axis in enumerate(axes)},
    }


def process_step(source_path: Path, preview_path: Path) -> dict[str, object]:
    import cadquery as cq

    imported = cq.importers.importStep(str(source_path))
    shapes = imported.vals()
    if not shapes:
        raise ValueError("The STEP file contains no geometry.")

    shape = shapes[0] if len(shapes) == 1 else cq.Compound.makeCompound(shapes)
    bounding_box = shape.BoundingBox()
    faces = shape.Faces()
    edges = shape.Edges()
    solids = shape.Solids()
    surface_types = Counter(face.geomType().lower() for face in faces)
    quality_flags = [] if solids else ["OPEN_SHELL"]

    preview_path.parent.mkdir(parents=True, exist_ok=True)
    cq.exporters.export(
        shape,
        str(preview_path),
        exportType="STL",
        tolerance=0.1,
        angularTolerance=0.1,
    )
    return {
        "unit_system": "mm",
        "parser_name": "cadquery-opencascade",
        "parser_version": version("cadquery"),
        "bounding_box": _bounding_box(
            [bounding_box.xmin, bounding_box.ymin, bounding_box.zmin],
            [bounding_box.xmax, bounding_box.ymax, bounding_box.zmax],
        ),
        "volume": float(shape.Volume()) if solids else None,
        "surface_area": float(shape.Area()),
        "face_count": len(faces),
        "edge_count": len(edges),
        "surface_type_histogram": dict(sorted(surface_types.items())),
        "quality_flags": quality_flags,
    }


def main() -> int:
    if len(sys.argv) != 4:
        return 64
    source_path, preview_path, result_path = map(Path, sys.argv[1:])
    try:
        result = process_step(source_path, preview_path)
        payload: dict[str, object] = {"result": result}
        exit_code = 0
    except Exception as exc:
        payload = {
            "error": {
                "code": "CAD_PARSE_INVALID_STEP",
                "message": "The STEP file could not be converted to valid geometry.",
                "operator_detail": f"{type(exc).__name__}: {exc}",
            }
        }
        exit_code = 2

    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_path.write_text(json.dumps(payload), encoding="utf-8")
    return exit_code


if __name__ == "__main__":
    code = main()
    sys.stdout.flush()
    sys.stderr.flush()
    # VTK currently corrupts the Windows heap during normal interpreter finalization.
    # The native parser is isolated in this child process, so bypassing finalizers is intentional.
    os._exit(code)

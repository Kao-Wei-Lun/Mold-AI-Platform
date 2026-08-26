import json
import subprocess
import sys
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path


class CADProcessingError(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.user_message = message


@dataclass(frozen=True)
class CADParseResult:
    unit_system: str
    parser_name: str
    parser_version: str
    bounding_box: dict[str, dict[str, float]]
    volume: float | None
    surface_area: float
    face_count: int
    edge_count: int
    surface_type_histogram: dict[str, int]
    quality_flags: list[str]


def _bounding_box(minimum: list[float], maximum: list[float]) -> dict[str, dict[str, float]]:
    axes = ("x", "y", "z")
    return {
        "min": {axis: float(minimum[index]) for index, axis in enumerate(axes)},
        "max": {axis: float(maximum[index]) for index, axis in enumerate(axes)},
        "size": {axis: float(maximum[index] - minimum[index]) for index, axis in enumerate(axes)},
    }


def _parse_stl(source_path: Path, preview_path: Path) -> CADParseResult:
    import trimesh

    try:
        loaded = trimesh.load(source_path, file_type="stl", force="scene", process=True)
        if isinstance(loaded, trimesh.Scene):
            if not loaded.geometry:
                raise CADProcessingError("CAD_PARSE_EMPTY", "The STL contains no geometry.")
            mesh = loaded.to_geometry()
        else:
            mesh = loaded

        if not isinstance(mesh, trimesh.Trimesh) or mesh.is_empty:
            raise CADProcessingError("CAD_PARSE_EMPTY", "The STL contains no geometry.")

        preview_path.parent.mkdir(parents=True, exist_ok=True)
        mesh.export(preview_path, file_type="stl")

        quality_flags = ["UNIT_UNCERTAIN"]
        volume: float | None = abs(float(mesh.volume))
        if not mesh.is_watertight:
            quality_flags.append("OPEN_SHELL")
            volume = None

        bounds = mesh.bounds.tolist()
        return CADParseResult(
            unit_system="unknown",
            parser_name="trimesh",
            parser_version=version("trimesh"),
            bounding_box=_bounding_box(bounds[0], bounds[1]),
            volume=volume,
            surface_area=float(mesh.area),
            face_count=int(len(mesh.faces)),
            edge_count=int(len(mesh.edges_unique)),
            surface_type_histogram={"triangle": int(len(mesh.faces))},
            quality_flags=quality_flags,
        )
    except CADProcessingError:
        raise
    except Exception as exc:
        raise CADProcessingError(
            "CAD_PARSE_INVALID_STL", "The STL could not be converted to a valid mesh."
        ) from exc


def _parse_step(source_path: Path, preview_path: Path) -> CADParseResult:
    result_path = preview_path.with_suffix(".result.json")
    try:
        completed = subprocess.run(
            [
                sys.executable,
                "-m",
                "platform_core.step_subprocess",
                str(source_path),
                str(preview_path),
                str(result_path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=240,
        )
        payload = (
            json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
        )
        if completed.returncode != 0 or "error" in payload:
            error = payload.get("error", {})
            raise CADProcessingError(
                error.get("code", "CAD_PARSE_SUBPROCESS_FAILED"),
                error.get("message", "The STEP parser process failed."),
            )
        return CADParseResult(**payload["result"])
    except subprocess.TimeoutExpired as exc:
        raise CADProcessingError(
            "CAD_PARSE_TIMEOUT", "The STEP parser exceeded its 240 second time limit."
        ) from exc
    except (OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CADProcessingError(
            "CAD_PARSE_INVALID_STEP", "The STEP file could not be converted to valid geometry."
        ) from exc
    finally:
        result_path.unlink(missing_ok=True)


def parse_cad_file(source_path: Path, cad_format: str, preview_path: Path) -> CADParseResult:
    if cad_format == "stl":
        return _parse_stl(source_path, preview_path)
    if cad_format in {"step", "stp"}:
        return _parse_step(source_path, preview_path)
    raise CADProcessingError("CAD_PARSE_UNSUPPORTED_FORMAT", "The CAD format is not supported.")

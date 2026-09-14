"""SB3 packager - writes the final .sb3 file.

An .sb3 file is a ZIP archive containing:
  * project.json   - the Scratch 3.0 project JSON
  * <asset-md5>.<ext>  - one file per costume/sound asset

The zip is uncompressed for the JSON (Scratch expects to read it first)
and stored normally for the assets.
"""

from __future__ import annotations

import json
import zipfile
from typing import Dict, Tuple


def write_sb3(path: str, project: dict, assets: Dict[str, bytes]) -> None:
    """Write a Scratch 3.0 project (.sb3) to `path`."""
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        # project.json - first entry, smallest compression overhead
        zf.writestr(
            "project.json",
            json.dumps(project, indent=2, ensure_ascii=False),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        # assets
        for md5ext, data in assets.items():
            zf.writestr(md5ext, data, compress_type=zipfile.ZIP_DEFLATED)


def write_sb3_bytes(project: dict, assets: Dict[str, bytes]) -> bytes:
    """Return the .sb3 as a bytes blob instead of writing to disk."""
    import io
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "project.json",
            json.dumps(project, indent=2, ensure_ascii=False),
            compress_type=zipfile.ZIP_DEFLATED,
        )
        for md5ext, data in assets.items():
            zf.writestr(md5ext, data, compress_type=zipfile.ZIP_DEFLATED)
    return buf.getvalue()


def read_sb3(path: str) -> Tuple[dict, Dict[str, bytes]]:
    """Read a .sb3 file and return (project_json, {md5ext: data})."""
    project = None
    assets: Dict[str, bytes] = {}
    with zipfile.ZipFile(path, "r") as zf:
        for name in zf.namelist():
            data = zf.read(name)
            if name == "project.json":
                project = json.loads(data)
            else:
                assets[name] = data
    if project is None:
        raise ValueError(f"{path} is not a valid .sb3 file (no project.json)")
    return project, assets

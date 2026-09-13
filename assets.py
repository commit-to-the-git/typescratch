"""Default Scratch assets used when a sprite/backdrop has no image.

We embed the OFFICIAL Scratch Cat costume SVG (costume1 from the
default Scratch 3.0 project) - extracted from an actual .sb3 file -
so that any project we generate looks correct in the Scratch editor.

A blank white backdrop SVG is also provided.
"""

import os

# Path to the official Scratch Cat SVG (sitting alongside this module)
_CAT_SVG_PATH = os.path.join(os.path.dirname(__file__), "scratchcat_official.svg")


def _load_official_cat() -> bytes:
    """Load the official Scratch Cat SVG from disk."""
    try:
        with open(_CAT_SVG_PATH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback to a placeholder if the SVG file is missing (e.g. if
        # the package was installed without the data file)
        return PLACEHOLDER_CAT_SVG.encode("utf-8")


# Official Scratch Cat - the real deal, loaded from scratchcat_official.svg
# Rotation center: (48, 50) - matches Scratch's default.
SCRATCH_CAT_SVG = _load_official_cat().decode("utf-8", errors="replace")


# A simple blank white backdrop, the size of a default Scratch stage.
BLANK_BACKDROP_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360" viewBox="0 0 480 360">
  <rect width="480" height="360" fill="#ffffff"/>
</svg>
"""

# A neutral grey costume used as a last-resort fallback if the official
# SVG file is missing from the install.
PLACEHOLDER_CAT_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">
  <rect width="96" height="96" fill="#cccccc"/>
  <text x="48" y="50" text-anchor="middle" font-family="sans-serif" font-size="14">cat</text>
</svg>
"""

# A short silent WAV used when a sound is referenced but no file exists.
SILENT_WAV = (
    b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)


def default_sprite_costume():
    """Return (name, svg_bytes, md5ext, rotation_center_x, rotation_center_y)
    for the official Scratch Cat."""
    data = SCRATCH_CAT_SVG.encode("utf-8")
    return ("costume1", data, "scratchcat.svg", 48, 50)


def default_backdrop():
    """Return (name, svg_bytes, md5ext, rotation_center_x, rotation_center_y)
    for a blank white backdrop."""
    return ("backdrop1", BLANK_BACKDROP_SVG.encode("utf-8"), "backdrop1.svg", 240, 180)


def placeholder_costume(name="costume1"):
    return (name, PLACEHOLDER_CAT_SVG.encode("utf-8"), "placeholder.svg", 30, 30)

"""Default TypeScratch assets.

The official TypeScratch mascot is **Lint Zippy**, an original character
created by the TypeScratch project.  Lint Zippy is licensed under
CC BY-NC-ND 4.0 (see MASCOT_LICENSE).  The TypeScratch language itself
is Apache 2.0 (see LICENSE).

A blank white backdrop SVG is also provided.
"""

import os

# Path to the official TypeScratch mascot - Lint Zippy!
_MASCOT_SVG_PATH = os.path.join(os.path.dirname(__file__), "lint_zippy.svg")


def _load_mascot() -> bytes:
    """Load the Lint Zippy mascot SVG from disk."""
    try:
        with open(_MASCOT_SVG_PATH, "rb") as f:
            return f.read()
    except FileNotFoundError:
        return PLACEHOLDER_MASCOT_SVG.encode("utf-8")


# Lint Zippy - the official TypeScratch mascot!
# Rotation center: (123, 131) - from the SVG's rotationCenter comment
MASCOT_SVG = _load_mascot().decode("utf-8", errors="replace")
MASCOT_ROTATION_CENTER_X = 123
MASCOT_ROTATION_CENTER_Y = 131

# A simple blank white backdrop, the size of a default Scratch stage.
BLANK_BACKDROP_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="480" height="360" viewBox="0 0 480 360">
  <rect width="480" height="360" fill="#ffffff"/>
</svg>
"""

# A neutral grey costume used as a last-resort fallback.
PLACEHOLDER_MASCOT_SVG = """<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="96" height="96" viewBox="0 0 96 96">
  <rect width="96" height="96" fill="#cccccc"/>
  <text x="48" y="50" text-anchor="middle" font-family="sans-serif" font-size="14">Lint</text>
</svg>
"""

# A short silent WAV used when a sound is referenced but no file exists.
SILENT_WAV = (
    b"RIFF\x24\x00\x00\x00WAVEfmt \x10\x00\x00\x00\x01\x00\x01\x00"
    b"\x44\xac\x00\x00\x88\x58\x01\x00\x02\x00\x10\x00data\x00\x00\x00\x00"
)


def default_sprite_costume():
    """Return (name, svg_bytes, md5ext, rotation_center_x, rotation_center_y)
    for the official TypeScratch mascot (Lint Zippy)."""
    data = MASCOT_SVG.encode("utf-8")
    return ("Lint Zippy", data, "lint_zippy.svg",
            MASCOT_ROTATION_CENTER_X, MASCOT_ROTATION_CENTER_Y)


def default_backdrop():
    """Return (name, svg_bytes, md5ext, rotation_center_x, rotation_center_y)
    for a blank white backdrop."""
    return ("backdrop1", BLANK_BACKDROP_SVG.encode("utf-8"), "backdrop1.svg", 240, 180)


def placeholder_costume(name="costume1"):
    return (name, PLACEHOLDER_MASCOT_SVG.encode("utf-8"), "placeholder.svg", 30, 30)

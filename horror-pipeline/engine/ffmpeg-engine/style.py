"""Ficknime/Vu house style, encoded as constants. Change here, not in the renderer."""
import os

# Paths resolve from this file, never from a machine-specific absolute path.
# The originals pointed at /home/claude/hp/... which exists on exactly one
# machine, so every font load failed anywhere else. Override with HP_FONT_DIR
# if the fonts ever move.
_ENGINE_DIR = os.path.dirname(os.path.abspath(__file__))
_REPO_ENGINE = os.path.dirname(_ENGINE_DIR)                      # engine/
FONT_DIR = os.environ.get(
    "HP_FONT_DIR", os.path.join(_REPO_ENGINE, "remotion-engine", "public", "fonts")
)

W, H, FPS = 1920, 1080, 30

# palette: black / white + ONE red accent. Nothing else (video-qc-workflow step 6).
WHITE   = (255, 255, 255)
BLACK   = (17, 17, 17)
RED     = (214, 32, 32)
GREY    = (120, 120, 120)

CANVAS  = WHITE

# image box: boxed + centered, never stretched full-bleed unless shot.full_bleed
BOX_W, BOX_H   = 1240, 680
BOX_CX, BOX_CY = 960, 600
BOX_RADIUS     = 20
BOX_BORDER     = 6

# persistent section title, top-center, ALL CAPS, bold
TITLE_FONT  = os.path.join(FONT_DIR, "anton-latin-400-normal.ttf")
TITLE_SIZE  = 76
TITLE_Y     = 56
TITLE_TRACK = 4          # letter-spacing px

POP_FONT    = os.path.join(FONT_DIR, "archivo-black-latin-400-normal.ttf")
POP_SIZE    = 58
CARD_FONT   = os.path.join(FONT_DIR, "bangers-latin-400-normal.ttf")
BODY_FONT   = os.path.join(FONT_DIR, "inter-latin-700-normal.ttf")

# motion — rule #1: nothing is ever fully static
KB_MIN_SCALE   = 1.06     # every held image starts at least 5% in
KB_DRIFT       = 0.30     # and travels at least this much over the shot
POP_IN_DUR     = 0.20     # slide+fade in
POP_OUT_DUR    = 0.16

# pacing guardrails, checked at build time
MAX_SHOT_LEN   = 6.5      # brief says never >8s on one asset; we keep headroom
TARGET_CHANGE  = (2.0, 4.0)

# audio targets (video-qc-workflow step 9)
LUFS_TARGET    = -15.0
TRUE_PEAK      = -1.5
LRA_TARGET     = 9.0      # keep it OPEN; Vu's 2026-08-03 cut failed at LRA 1.9
BED_GAIN_DB    = -19.0
SFX_GAIN_DB    = -9.0
DUCK_RATIO     = 6

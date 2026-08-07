"""Speech bubbles, drawn as PNGs and composited as cards.

Why this element gets its own module. On the reference format this was measured from,
the speech bubble is not decoration — it is the thing the audience quotes back. The
single most-liked comment on a nine-minute video is a bubble gag that is on screen for
about two seconds, and the next two most-liked are a parody of the survival block and a
joke about the narrator's flatness. The horror is the premise; the comedy is the
engagement. A reproduction of that format that copies the anecdotes, the stats and the
survival tips and drops the bubbles reproduces everything except the reason anybody
comments.

Why PIL rather than a filtergraph. A bubble is a rounded rectangle with a tail, and
`drawbox` draws neither a corner radius nor a triangle. It could be faked with layered
boxes; it would look faked. Rendering the shape once to a PNG and compositing it as an
`ImageCard` reuses the path stills already take, keeps the tail honest, and gives the
text a real wrap instead of `drawtext`'s single line.

The bubble is deliberately plain — white fill, black outline, black text, a straight
tail. That is what the reference uses, and it is also what reads at thumbnail size on a
phone. A gradient or a drop shadow here would be the tell.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

#: How wide a bubble is allowed to get, as a fraction of frame width. Past this it stops
#: reading as somebody speaking and starts reading as a caption with a tail on it.
MAX_WIDTH = 0.46

#: Characters per line before wrapping. A bubble is a punchline, not a paragraph — the
#: reference's are all one short sentence, and the wrap is here to stop a long one
#: becoming a single unreadable line rather than to support long ones.
WRAP_CHARS = 26

#: Hard ceiling on the joke. Longer than this and it is not a bubble.
MAX_CHARS = 120

PAD_X, PAD_Y = 26, 20
RADIUS = 26
OUTLINE = 5
TAIL_W, TAIL_H = 34, 30


def _font(size: int):
    from .compose import font_file

    path = font_file()
    if path:
        try:
            return ImageFont.truetype(path, size)
        except OSError:                                            # pragma: no cover
            pass
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                              # pragma: no cover
        return ImageFont.load_default()


def wrap(text: str, width: int = WRAP_CHARS) -> list[str]:
    """Break at words. A bubble that hyphenates reads as a mistake."""
    flat = " ".join(str(text or "").split())[:MAX_CHARS]
    if not flat:
        return []
    lines: list[str] = []
    line = ""
    for word in flat.split():
        candidate = f"{line} {word}".strip()
        if len(candidate) > width and line:
            lines.append(line)
            line = word
        else:
            line = candidate
    if line:
        lines.append(line)
    return lines


def draw(text: str, out_path: Path, *, frame_width: int = 1920, frame_height: int = 1080,
         tail: str = "left") -> Path | None:
    """Render one bubble to a transparent PNG. `None` when there is nothing to say.

    `tail` is which side the pointer comes off, matching where the speaker is. It is a
    side rather than an angle because the only thing that matters is that the tail
    points at the character, and on a composited shot the character is on one side.
    """
    lines = wrap(text)
    if not lines:
        return None

    size = max(18, int(frame_height * 0.036))
    font = _font(size)

    probe = ImageDraw.Draw(Image.new("RGBA", (8, 8)))
    widths, heights = [], []
    for line in lines:
        box = probe.textbbox((0, 0), line, font=font)
        widths.append(box[2] - box[0])
        heights.append(box[3] - box[1])
    line_height = max(heights) + 10
    body_w = min(max(widths) + PAD_X * 2, int(frame_width * MAX_WIDTH))
    body_h = line_height * len(lines) + PAD_Y * 2

    image = Image.new("RGBA", (body_w, body_h + TAIL_H), (0, 0, 0, 0))
    pen = ImageDraw.Draw(image)
    pen.rounded_rectangle(
        [(0, 0), (body_w - 1, body_h - 1)], radius=RADIUS,
        fill=(255, 255, 255, 255), outline=(0, 0, 0, 255), width=OUTLINE,
    )

    # The tail, drawn as a filled triangle with its own outline. Inset from the corner
    # so it reads as coming off the body rather than off the radius.
    base = int(body_w * (0.22 if tail == "left" else 0.78))
    points = [(base, body_h - OUTLINE // 2),
              (base + TAIL_W, body_h - OUTLINE // 2),
              (base + (TAIL_W // 3 if tail == "left" else TAIL_W * 2 // 3),
               body_h + TAIL_H - 1)]
    pen.polygon(points, fill=(255, 255, 255, 255), outline=(0, 0, 0, 255))
    # Redraw the body's bottom edge inside the tail's footprint so the two shapes read
    # as one outline rather than as a triangle stuck onto a box.
    pen.line([(base + OUTLINE, body_h - OUTLINE // 2 - 1),
              (base + TAIL_W - OUTLINE, body_h - OUTLINE // 2 - 1)],
             fill=(255, 255, 255, 255), width=OUTLINE)

    y = PAD_Y
    for line in lines:
        pen.text((body_w // 2, y), line, font=font, fill=(0, 0, 0, 255), anchor="ma")
        y += line_height

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    return out_path


def path_for(text: str, workdir: Path, *, tail: str = "left") -> Path:
    """A stable filename for a bubble's text.

    Hashed rather than counted, so re-rendering a scene that says the same thing lands
    on the same file instead of accumulating `bubble_1..bubble_40` across retries.
    """
    digest = hashlib.sha1(f"{tail}:{text}".encode()).hexdigest()[:12]
    return Path(workdir) / f"bubble_{digest}.png"

# Thumbnail Packaging Spec (matched to M Simplified, 2026-07)

Derived from a real M Simplified 8-creature roster thumbnail that did 700K+ in weeks. This is the house target for compilation ("X Monsters Explained / You Cannot Survive") thumbnails.

## Layout
- 8 creatures, 4 columns x 2 rows, each in a rounded-corner box with a thick black border, on a plain white background.
- One creature image per cell, dramatic/high-contrast.

## Text packaging (the part that was getting missed)
- **ALL CAPS.** Every label uppercase.
- **Font: chunky BOLD COMIC display face**, NOT a clean corporate sans. (M Simplified's looks like Komika / a heavy comic display; Comic Neue Bold is the closest free installable match. Original Vu/Abel comic-ish font was closer to correct than DejaVu/Montserrat — do NOT "upgrade" to a clean sans for this niche.)
- **Fill white, thick even BLACK stroke.** No drop shadow. No colored highlight box or banner behind the text.
- **Big and chunky**, centered directly under each cell, one line per label.
- Keep names SHORT so they render large: drop "The" where it helps (WANDERING FAITH not THE WANDERING FAITH), abbreviate long ones (UPSIDE-DOWN FACE not THE MAN WITH THE UPSIDE-DOWN FACE).

## Build note (for reproducing in this environment)
- `apt-get install -y fonts-comic-neue` → `/usr/share/fonts/opentype/comic-neue/ComicNeue-Bold.otf`.
- Faux-chunk in PIL: draw a black base pass (fill black, stroke black, width sw+2), then a white pass on top (fill white, stroke white, width 2). Autofit size per column width (~452px cols at 1920 wide), cap ~70px.
- Cover the video's baked-in labels with white rectangles first (bg is white), then redraw.

## Strategic note (bigger win than typography)
The 8-box roster is the house format and it works (700K proof), so it's fine. But for a harder-hitting variant, a hero-forward layout (1-2 large creatures + short bold hook + number badge) can out-click a full grid at feed size. Offer as an A/B option, don't force it.

## Lesson logged
Owner corrected a wrong call here: do not push this niche toward "clean/professional" sans fonts. The heavy all-caps COMIC look IS the professional standard for this niche. Match competitors' actual packaging, verified against a real reference, not general design instinct.

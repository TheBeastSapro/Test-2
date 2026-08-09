# VIDEO QC ROUND 2 — "Trevor Henderson Monsters You Cannot Survive Explained"
**Editor:** Abel · **File:** revised cut, 2026-07-29 · **Compared against:** round-1 QC 2026-07-27 (20-item fix list)

## VERDICT
**Big step up. 16 of 20 items landed.** Motion is genuinely fixed and the canon/asset problems are cleared. Two things block approval: a font regression I caused with an ambiguous note, and the export/audio items were not touched at all.

## MEASURED, v1 → v2

| Metric | Round 1 | Round 2 | Status |
|---|---|---|---|
| Duration | 595.3s | 595.1s | same |
| Static runs >=3s | 19 runs, 72.0s (12.1%) | **10 runs, 31.5s (5.3%)** | FIXED |
| Longest static hold | **9.0s** (1:47-1:56) | **3.5s** | FIXED |
| Dead/blank canvas frames | ~19 | **1** (1:01) | FIXED |
| Frames <30/255 luminance | 56s | 54s | not addressed |
| Video bitrate | 870 kbps | 913 kbps | **not addressed** |
| Frame rate | 60 fps | 60 fps | not addressed |
| Audio mean | -16.3 dB | -16.3 dB | in range |
| Audio true peak | +0.25 dBTP | **+0.25 dBTP** | **not addressed** |
| Loudness range | 2.0 LU | 2.0 LU | not addressed |

## FIXED (verified frame by frame)
1. **Motion.** Longest hold down from 9.0s to 3.5s; total static time cut by 56%.
2. **Good Boy 1:47-1:56.** Brightened and moved to white canvas. Now unmistakably canon: black body, pointed ears, wrinkled near-human face, two cloudy pupil-less eyes, open mouth with no teeth or tongue. Arrow lands on the cloudy eye. This is now one of the better shots in the video.
3. **Title casing.** "The Fetid King" and "Cartoon Cat" both Title Case throughout.
4. **9:15 Sonic replaced** with a clean black-and-white Cartoon Cat vector. On-palette, on-style.
5. **3:53 Seth Meyers replaced** with a Ghostface/Scream clip. Horror register restored.
6. **3:25 child convention photo removed**, replaced with the canon night photo plus an "ordinary performer" pop.
7. **9:43 outro roster labels restored.** All 8 present, correctly spelled, pictures match labels.
8. **Text fixes all landed:** "rubber-hose body", "human-like teeth", "9-foot arms", "bone-like fingers".
9. **Capitalisation consistent:** "Squeeze beneath doors" / "Climb across ceilings".
10. **Numeral formatting consistent:** "40ft" and "20ft".
11. **Green removed from palette.** The "36" at 7:56 is now black; the green scale bar at 0:13 is gone.
12. **HAIL KING added** at 5:37 (see open issue on size).
13. **Dates 1943 (4:28) and 1948 (4:30) added.**
14. **Upside-Down Face fixed and now canon-correct** — composited as a small BACKGROUND figure in the 1940s crash photo, face inverted, circled with a red ellipse and arrow. This is exactly the canon framing.
15. **Subtitles substantially shortened.** Most are now 3-5 word pops rather than full lines.
16. **Scale reference at 0:13** replaced with an actual building (see open issue on proportion).

## NOT DONE
17. **1951 date never appears.** 1943 and 1948 landed; the train disaster date did not.
18. **Export bitrate unchanged** (870 → 913 kbps). Still very low for 1080p60; dark scenes still block up.
19. **Audio untouched.** True peak still +0.25 dBTP against a sub -1 dB spec. Loudness range still 2.0 LU.
20. **General brightness untouched** (56s → 54s under 30/255). Only the specifically flagged Good Boy shot was lifted.
21. **Still 60 fps**, brief says 30.
22. **A few subtitles are still full clauses:** 7:21 "it will be running beside you", 8:03 "When prey becomes scarce", 8:33 "old-fashioned and warped", 9:38 "The show has already started".

## NEW / REGRESSED
23. **TITLE FONT REGRESSION — my fault.** Round-1 item 14 said the roster serif and the comic section titles should match. Abel matched them the wrong direction: every section title is now a Times-style SERIF. Per `claude/thumbnail-spec.md`, the chunky bold COMIC face is the house standard for this niche and the owner has already corrected a push toward clean/professional fonts once. Worse, it did not resolve the inconsistency — the keyword pops are still in the comic font, so there are still two typefaces, just swapped around. The correct fix is to move the ROSTER to comic, not the titles to serif.
24. **HAIL KING is far too small** at 5:37 — roughly 20px tall on a 1080 frame, illegible on a phone.
25. **Siren Head scale comparison is wrong at 0:13.** The building is roughly 13 storeys and Siren Head reads about 7 storeys against it, implying 70+ ft, while the pop beside it says 40ft. Canon 40 ft is about a 4-storey building. The comparison now contradicts its own caption.
26. **Ghostface clip is copyrighted film footage** and sits letterboxed with black bars on the white canvas. Lower risk than a real named person, but still a claim exposure and an off-canvas treatment.

## TRACKING
Abel's recurring failure mode (requested canon swaps not landing in the next cut) is **CLOSED for this round** — every canon and asset fix requested was verified present. Motion regression from round 1 is also closed. The open coaching item is now font/style discipline, and that one traces to an ambiguous note from me rather than to him.

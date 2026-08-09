# Video QC — "Analog Horror Monsters You Can't Beat | Explained in 10 Minutes"
*Full-length edit, 10:07. Editor: **Vu** (Drive owner duhoangvu3007@gmail.com). Delivered 2026-08-01, QC'd 2026-08-03.*
*Graded against `claude/editor-brief-2026-07.md`, `claude/editor-materials-analog-horror-cant-beat.md`, `claude/qc-notes-analog-horror-cant-beat-2026-07-24.md`, `claude/thumbnail-spec.md`, per `claude/video-qc-workflow.md`.*

## VERDICT: Needs another round. 11 hard fixes, 6 style fixes, 2 audio fixes.
The craft floor is the highest we have had. Motion is the best measured result across every cut to date and the canon research on Rolling Giant, Moon, Boiled One and Gemini is genuinely accurate. What sinks it is a cluster of off-register meme assets (one of them is the final frame of the video), three mutually inconsistent Horned Serpent designs where one of them contradicts the narration on the line it plays under, and a text-pop collapse across the last three minutes.

---

## Measured numbers

| Check | Result | Verdict |
|---|---|---|
| Motion, avg frame change per 0.5s | **25.1%** (prior Vu benchmark 22%) | **Best yet** |
| Stretches ≥4s under motion threshold | **1** (9:27.5–9:31.5, 4.0s) | Green |
| Stretches >8s on one asset | **0** | Green |
| Resolution / fps / codec | 1920x1080 / 30 / H.264 | Green |
| Video bitrate | **10.1 Mbps** (Abel's last was 0.87) | Green |
| Audio bitrate | 320 kbps AAC 48 kHz | Green |
| Integrated loudness | **-12.5 LUFS** (target -14 to -16) | **Hot** |
| True peak | **+0.42 dBTP** (target under -1.0) | **Over** |
| Loudness range (LRA) | **1.9 LU** | **Over-limited** |
| Hard-clipped samples | 0 | Green |
| Mean luminance | 124/255; only 52s under 30, all with bright anchors | Green |
| Section titles | 8/8 ALL CAPS, consistent comic-bold, top-center, no typos | Green |
| Roster grids (0:00, 9:47) | 8 cards, labeled, correct names/spelling/count, matches thumbnail spec | Green |
| VO gaps | **None.** Whisper dropped ~15% on the music bed; RMS per 0.5s is flat through every apparent gap | Green |

**Section map:** Roster 0:00 · Mimic 0:05 · Man in the Suit 1:19 · Alternates 2:24 · Rolling Giant 3:43 · Boiled One 4:38 · Moon 5:48 · Horned Serpent 6:54 · Iris 8:19 · Outro 9:47.

---

## HARD FIXES

1. **4:30 — Minion (Despicable Me) on screen** in the Rolling Giant escalator gag. Licensed studio IP and a total tone break. Same class as the Seth Meyers catch on Abel's cut.
2. **10:05–10:07 — a pig hanging out of a car window with a laser pointer is the FINAL frame of the video.** Full screen, low-res upscaled GIF, with a transparency checkerboard strip visible along the top edge. The last thing a viewer sees should be an Iris beauty shot or the roster card.
3. **2:10 — real-person meme cutaway** (man in a yellow jacket with a blue book, sky-blue background) in the Man in the Suit section. Real identifiable person plus a bright meme palette dropped into a horror explainer.
4. **7:44 — cartoon chicken pressing a red button** in the Horned Serpent section. That section is the apocalyptic one and the script has no joke line there. Unscripted gag in the wrong register.
5. **7:15 and 7:53 — photoreal 3D horned serpent coiled around a planet, whole body visible, playing under the VO line "no one has ever seen the whole thing."** Direct narration contradiction, and the materials sheet is explicit: colossal limbs surfacing beneath monuments, **never the whole being**. This is the Long Horse lower-jaw failure repeating.
6. **8:05 — crude MS-Paint serpent wrapped around a NASA Blue Marble.** Third mutually inconsistent Horned Serpent design inside one section (cinematic 3D render, MS Paint cartoon, Alcatraz containment skull). Pick the containment-skull register and hold it.
7. **4:55 — on-screen card reads "Boiled one Phenomenom."** Typo: Phenomenon. Also lowercase "one" where every other creature name is title case.
8. **9:05 — stock photo of a landscaper trimming a hedge** on the VO line "through the gardeners." The Gardeners are a Gemini Home Entertainment canon entity, not literal gardeners. Bright daylight stock photo of a real person in the middle of the deep-space finale. Also half the frame is empty white.
9. **8:13 — county-jail stock photo of a real inmate** for the "prisons / the prisoner" metaphor. Literal-minded and another real-person likeness.
10. **1:35 — on-screen text reads "Unknowingly's"** with nothing after it. The series is *Unknowingly*. Dangling possessive.
11. **Mimic design conflict.** The roster card (0:00 and 9:47) shows a grinning red face with large glossy eyes. The section hero renders (0:15, 1:15) are a different creature entirely. Two designs for the same creature in one video. Owner needs to pick the canon Vita Carnis look and both must match it.

## STYLE / BRIEF FIXES

12. **Horned Serpent (6:54–8:18, 84s) has 2 keyword pops and both are filler connectives:** "At that point" (7:59) and "mistake" (8:13). No dates, names, or canon numbers in the whole section.
13. **Iris (8:19–9:46, 87s) has zero editor-added keyword pops.** The only on-screen text is baked into source images (Gemini logo 8:37, Crusader 5 card 9:21). The finale is the softest-texture stretch in the video.
14. **7:59 — "At that point" sits alone in red on an empty white frame** for about 3 seconds. No image at all.
15. **Series attribution pops are inconsistent.** 0:15 is thin white "Mimic from Vita Carnis"; 1:35 is bold red "Unknowingly's". Pick one treatment and one phrasing and apply it to all eight.
16. **3:09 — "Metaphysical Awareness Disorder" runs off the bottom edge of the boxed image onto the white canvas.** Spelling is correct, layout is sloppy.
17. **Man in the Suit runs three visual registers** for one creature: grey vinyl toy product photo (1:35, 1:40), painted gore illustration (1:27, 2:00), B/W 1954 film stills (1:55). All lineage-correct, but pick a dominant one.

## AUDIO FIXES

18. **Loudness.** -12.5 LUFS integrated (target -14 to -16), true peak +0.42 dBTP. Set the limiter ceiling to -1.0 dBTP and pull the master about 2.5 dB.
19. **Over-limited mix.** LRA 1.9 LU means the bed and the VO sit at the same level all the way through and SFX have no headroom to punch. Only about a third of hard cuts carry a measurable audio transient. Loosen the master limiter and duck the bed properly under the VO so the whooshes and booms can actually rise above it.

---

## WHAT IS GREEN (keep all of it)

- **Motion is solved and then some.** 25.1% average frame change per 0.5s, one 4.0s low-motion stretch in the entire video, nothing over 8s. Nothing static anywhere.
- **Rolling Giant name-twin trap avoided.** Correct Kane Pixels *The Oldest View* parade puppet, "THE OLDEST VIEW" title card at 3:51, "Julien Reverchon" spelled correctly at 3:55. The escalator gag lands.
- **Boiled One universe rule respected.** No Doctor Nowhere, no Silas Orion, no channel logo. "Broadcast-813" correct with the hyphen.
- **Moon section is the strongest canon work in the video.** WCLV-TV Local 58 logo, "CIVIL DANGER ALERT", "GO OUTSIDE NOW", "HIS THRONE" in red across a bright moon. All spelled correctly, all canon, moon stays legible.
- "Metaphysical Awareness Disorder / M.A.D.", "Gemini Home Entertainment", "Crusader 5" all correct.
- **Grade is right.** Night scenes keep 2 to 3 bright anchors (candle, lamp pools, lit city windows, TV glow). No illegibility flag anywhere.
- **Roster grids match the thumbnail spec exactly** (white background, 4x2, rounded black-bordered cells, white-fill black-stroke comic caps), and the outro roster is labeled.
- **Thumbnail moment present** (Iris planet-eye, 8:35 onward).
- **Outro CTA present and woven** (comment ask plus "which series next", no subscribe graphics).
- Alternates section is excellent: peephole shot at 3:34, the four red alternate dialogue lines at 3:05, dispatcher text at 2:28. Tragic register held, no jokes.

## OWNER-SIDE ITEMS (not the editor)

- **The mid-roll CTA is missing from the VO.** The recorded voiceover goes straight from the Alternates verdict at 3:38 into "The rolling giant" at 3:40. The scripted ~55-word woven comment ask after creature 3 was never recorded. Needs a VO pickup and an insert, not an edit fix.
- **Rolling Giant opener still uses the "you look away" framing** (3:43). The 2026-07-24 script QC flagged this as non-canon and offered a rewrite; owner kept the section. Restating only, no action needed unless you want it swapped now.
- **Canon calls only you can make:** the Vita Carnis Mimic design (item 11) and the Monument Mythos Horned Serpent design (items 5 and 6). See open items below.

## OPEN (could not close, close before publish)

- **The materials sheet never locked approved image URLs per creature** ("no locked per-creature image shortlist yet, Fandom was blocked at QC time"). So both Mimic renders and all three Horned Serpent designs were checked against the sheet's written descriptions, not against an approved source set. Recommend locking a per-creature shortlist before the re-cut so this stops recurring.
- **VO pronunciation not fully verifiable.** The dense music bed dropped about 15% of the transcript. RMS analysis confirms there are no actual VO gaps, but I could not verify pronunciation on "Reverchon" and "Vita Carnis" by ear.

---

## Checklist status (steps 1–17)

| # | Check | Status |
|---|---|---|
| 1 | Motion | **Green (best yet)** |
| 2 | Pacing / dead zones | Green (one 4.0s stretch) |
| 3 | Canvas & layout | Fix sent (items 14, 16) |
| 4 | Keyword pops | **Fix sent (items 12, 13, 15)** |
| 5 | Canon image accuracy | **Fix sent (items 5, 6, 8, 11)** |
| 6 | Asset drift | **Fix sent (items 1, 2, 3, 4, 6, 9, 11, 17)** |
| 7 | Tone / grade | Green |
| 8 | SFX | Fix sent (item 19) |
| 9 | Audio levels | **Fix sent (item 18)** |
| 10 | Humor gags | Fix sent (items 1, 4) |
| 11 | Roster / section cards | Green |
| 12 | VO / transcript | Green (no gaps) · **OPEN: pronunciation** |
| 13 | CTA | **Owner-side: mid-roll CTA missing from VO** |
| 14 | Delivery specs | Green |
| 15 | Retention read | See below |
| 16 | Thumbnail moment | Green |
| 17 | Third-party / likeness | **Fix sent (items 1, 3, 8, 9)** — no minors in frame |

## Retention read

Pacing supports a strong curve for the first two thirds. At 25.1% average change per 0.5s with no dead zones, the 0:30 hook should clear the 65–75% niche bar comfortably, and the Mimic-to-Alternates run (0:05–3:42) is the densest, best-textured stretch.

The risk is the back third. From **6:54 to 9:46** (2:52 of runtime, the Horned Serpent and Iris sections) keyword pops fall to two filler words and then to zero, there is a text-only white frame at 7:59, and the only low-motion stretch in the video sits at 9:27. That is the exact window where drop-off compounds, and it is also where the meme breaks (7:44, 8:13, 9:05) pull the viewer out of the dread. Fixing items 4, 8, 9, 12, 13 and 14 is worth more retention than everything else on the list combined.

---

## Editor tracking row

| Date | Video / section | Editor | Recurring-mistake status | Turnaround | Verdict |
|---|---|---|---|---|---|
| 2026-08-03 | Analog Horror Can't Beat, full 10:07 | Vu | **Motion SOLVED and improved** (25.1%/0.5s vs 22% prior, one 4s stretch, nothing over 8s). **Grade legibility FIXED** (bright anchors present, no dark flag). **NEW: off-register meme assets** (Minion 4:30, real-person meme 2:10, chicken 7:44, pig as final frame 10:05) which is the failure mode we had only seen from Abel. **NEW: canon contradiction** on Horned Serpent (whole body shown under "no one has seen the whole thing", three inconsistent designs). **NEW: keyword-pop collapse** in the final two sections. Quiet-gap issue GONE. Bitrate and specs excellent. | first full-length delivery | **Needs another round.** 19-item fix list sent, split into 4 chunks. |

**Watchlist update:**
- **Vu** — motion and grade are both CLOSED, do not re-flag unless they regress. **New unsolved: asset register discipline.** Vu's meme instinct is reaching for whatever is funny rather than whatever is in-tone; brief him that gags must stay inside the horror register and that a gag on a non-joke line is a fix, not a bonus. Second new item: keyword-pop density must hold through the finale, not taper.
- **Both** — real-person and licensed-IP assets are now a repeat across both editors. Add a standing line to the brief: no licensed characters, no real identifiable people, no meme photographs, ever.
- **Both** — a locked per-creature approved image list before the edit starts would have prevented items 5, 6 and 11. This is now the highest-leverage process fix.

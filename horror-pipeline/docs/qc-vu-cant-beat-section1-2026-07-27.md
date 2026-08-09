# Video QC — Vu, Section 1 (THE MIMIC)
**Video:** "Analog Horror Monsters You Can't Beat Explained" — first section only
**v1:** 78.9s, 1920x1080, 30 fps, H.264, 8.37 Mbps — QC'd 2026-07-27
**v2 (revision):** same duration, 9.68 Mbps — QC'd 2026-07-28
**Verdict on v2:** APPROVED FOR THE FULL BUILD. Seven of nine notes fully cleared, one partially, one is an audio item that needs a real fix.

## v1 vs v2 measured
| Metric | v1 | v2 | Standard | Verdict |
|---|---|---|---|---|
| Mean frame-to-frame change | 25.5% | **28.3%** | 20%+ | improved |
| Longest fully frozen hold | 3.7s @ 0:29.5 | **2.5s @ 1:03.2** | under 3s | now passing |
| Total frozen holds 1.5s+ | 5 across the section | **3, all inside one scene (1:03–1:10)** | 0 | improved, one scene left |
| Visible change events | 80 (mean gap 1.00s) | **94 (mean gap 0.85s)** | constant | improved |
| Longest gap with no change | 3.75s | **3.00s** | under 4s | passing |
| Bitrate | 8.37 Mbps | **9.68 Mbps** | 8+ | fine |
| Loudness (mean) | -16.6 dB | **-15.2 dB** | -14 to -16 | now in range |
| Samples at full scale | 29 | **60** | 0 | **worse — see note 9** |
| Samples within 1 dB of full scale | 173 | **519** | few | **worse** |

## Fix scorecard
1. **0:06 speech bubble grammar** — FIXED. Now reads "Why are the lights off?"
2. **0:10 phone message** — FIXED. Now reads "I'm still at work". He also added a new beat: the stick figure sits up alarmed after the message lands. Good instinct, not asked for.
3. **Three blank white text-only cards** — FIXED.
   - Card 1 (0:35) is now the keyword pop **DELAY** over the live wardrobe scene. This is exactly the competitor pattern.
   - Card 2 (0:48) now has a stick figure holding a gun beside the text.
   - Card 3 (0:54) is now a "PLAN" notepad photo.
   - Residual: cards 2 and 3 still use sentence fragments ("The obvious counter", the plan line) instead of keywords, and the PLAN notepad is generic stock. Low priority.
4. **1:12–1:17 verdict line over a Tom and Jerry clip** — FIXED. Cartoon is gone. The closer now runs on the Mimic render turning through three poses, 17 to 19% motion per second. Rule satisfied. Soft note: three renders side by side on white reads like a model showcase rather than a dread beat. One large Mimic with a slow push-in on a dark plate would hit harder.
5. **0:29.5–0:33 frozen wardrobe reveal** — FIXED, and this is the standout. Motion went from 0.3% to 26% per second. Now a full staged emergence: head over the top of the wardrobe, then shoulder, then arm, then the body sliding out from behind. Best beat in the section.
6. **Frozen composites between element pops** — PARTIAL.
   - 0:11–0:13 fixed (0.0% to 6.3%).
   - **1:03–1:10 not fixed.** Three frozen holds remain: 1:03.2 for 2.5s, 1:06.0 for 2.25s, 1:08.8 for 1.5s. This is the wardrobe comedy beat. Elements pop in but the plate under them never drifts. It is now the only unmoving scene left in the section.
7. **0:50–0:54 misaligned overlapping collage** — FIXED. The mismatched pile is gone, replaced by a clean sequential 1-up and 2-up.
8. **Creature asset canon** — unchanged, owner decision still open. He kept the 3D render and used it consistently across the whole section, which is the important part. Decide whether to bless it as the house look for the Mimic before he builds the remaining seven creatures.
9. **Audio** — HALF DONE, and the half he did made the other half worse.
   - He raised the gain by 1.4 dB as asked. Mean is now -15.2 dB, inside the brief.
   - He did **not** add the limiter. Without a ceiling, the gain bump pushed more of the track into the wall: samples at full scale went from 29 to 60, and samples within 1 dB of full scale went from 173 to 519.
   - Worst inter-sample overs sit at **0:07 to 0:12**, reaching about +2.2 dBTP. Also hot at 0:51.
   - Correct fix: leave the gain where it is, add a true-peak limiter with the ceiling at -1 dBTP, and re-export.

### Correction to the v1 report
The v1 QC recorded "no clipping, peak -0.4 dB". That was wrong. v1 already had 29 samples pinned at full scale and a max_volume of 0.0 dB. The clipping predates the revision; the gain bump amplified an existing problem rather than creating one.

## Style consistency notes for the remaining sections
- Stick figures are solid black with a white outline everywhere except the gun figure at 0:48, which is grey. Match it to the rest.
- Keyword pops: DELAY at 0:36 uses red fill with an outline; "The obvious counter" at 0:49 uses a different stroke weight. Lock one keyword-pop style and reuse it for all eight creatures.

## What is working (carry into all eight sections)
1. Layered PNG staging as the default, not a fallback. Dark doorway, hallway, bedroom composites, wardrobe room, size ramp, closet plus stick figure.
2. Creature emerging from **behind** scenery rather than sliding in over it.
3. Comedy beat with stick figures and speech bubbles, placed on an actual joke line.
4. Persistent MIMIC top title on every frame including the dark cinematic ones. No corner mascot.
5. Source credit "Mimic from Vita Carnis" at 0:22.
6. Real Vita Carnis found footage at 1:09–1:11 (caged specimen, concrete corner) as a canon anchor.
7. Section ends on the roster/thumbnail grid card at 1:17 before "The Man In The Suit". No blank seam.

## Canon reference (Vita Carnis, Darian Quilloy) — for the asset decision in note 8
- **Mature Mimic:** skinless bright red, bulging empty eye sockets, wide grin of mostly incisors, limbs longer than human, extended fingers.
- **Elder Mimic:** pale pink face, large round black eyes, **toothless** grin (teeth migrate into the throat), thick black skin over the body, taller and more spindly.
- **Young Mimic:** small, thin, four appendages, moves quadrupedally.
- **Mimic Morph:** grows skin and hair, near-identical to a human.
- The render in use has the mature Mimic's body and grin but the Elder's glossy black eyes, so it blends two life stages.
- The Mimics documentary contains no wire-cage lab shot and no concrete-pipe shot; those come from elsewhere in the series.

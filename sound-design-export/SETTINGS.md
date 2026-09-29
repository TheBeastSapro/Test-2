# SETTINGS.md — GENERAL vs CHANNEL TASTE

Every setting in the pipeline, tagged.

- **GENERAL** — would apply to any channel. Delivery standards, measurement
  method, how a cue is timed against the picture, how a level is *derived* from
  a measurement.
- **TASTE** — chosen for ExplainTory. Style, density, section length, the tier
  gains, the bed level, the thresholds tuned against this channel's VO.

**When in doubt I tagged TASTE.** A wrong GENERAL tag silently exports one
channel's preference into somebody else's; a wrong TASTE tag only makes someone
re-decide something they could have inherited. The second mistake is cheaper.

Where a value is a script default, the flag and file are given so it can be
checked against the code rather than trusted from this table.

---

## Delivery and mastering

| setting | value | where | tag |
|---|---|---|---|
| Master anchored to the voice, not a programme target | `loudness_target_lufs: null` | cue sheet | **GENERAL** |
| Sum at unity | `amix=inputs=3:normalize=0` | `assemble.py` | **GENERAL** |
| True-peak ceiling | **−1.0 dBTP** (`alimiter=limit=0.8913`) | `assemble.py` | **GENERAL** |
| Explicit limiter appended after any `loudnorm` | always | `assemble.py` | **GENERAL** |
| Internal sample rate / channels | 48 kHz stereo | `SR`, `CH` | **GENERAL** |
| Audio export codec by extension | `.mp3` → `libmp3lame -q:a 2`; else `pcm_s16le` | `assemble.py` | **GENERAL** |
| Video never re-encoded on mux | `-c:v copy` | `assemble.py` | **GENERAL** |
| Muxed audio codec | `aac 320k` (previews `aac 256k`) | `assemble.py` | **GENERAL** |
| Mux from the WAV master, not the mp3 | — | SOP §9.2 | **GENERAL** |
| Resulting programme loudness | −14.4 LUFS (an *output*) | measured | **GENERAL** |
| Shipping ~7–9 dB hotter than the reference channel's back catalogue | deliberate | — | **TASTE** |
| Expected VO stem: −14.5 LUFS, LRA 1.6–1.7 | this channel's VO master | — | **TASTE** |

## Ducking

| setting | value | tag |
|---|---|---|
| Duck the music bus only; SFX and beds never duck | — | **GENERAL** |
| Sidechain keyed by the VO stem | — | **GENERAL** |
| Threshold | 0.03 linear (≈ −30 dBFS) | **TASTE** |
| Ratio | 6:1 | **TASTE** |
| Attack / release | 5 ms / 300 ms | **TASTE** |
| Makeup | 1 (none) | **TASTE** |

## Bed level

| setting | value | tag |
|---|---|---|
| Solve the trim from a measurement, never a fixed dB | `calibrate_bed()` | **GENERAL** |
| Report both the target and the measured under-speech figure | — | **GENERAL** |
| Don't use the gap method on a continuous VO | — | **GENERAL** |
| Don't use `measure_ref.py`'s bed ratio on our own mixes | — | **GENERAL** |
| `--bed-target-db` | **−20.0** | **TASTE** |
| `--sfx-db` | **−6.0** | **TASTE** |
| `--music-db` | **0.0** | **TASTE** |
| Resulting bed under speech | −25.9 dB | **TASTE** |

## Music

| setting | value | tag |
|---|---|---|
| One track per section | — | **TASTE** |
| `SECTION_SECONDS` | **47.0**, clipped 1–24 | **TASTE** |
| Boundaries on story turns, snapped to the transition card | — | **TASTE** |
| Push `vocals:false` and `duration.min` into the query | — | **GENERAL** |
| Treat a vocal tag as a hard reject, not a score penalty | — | **GENERAL** |
| Measure rhythmic drive before casting | `mus_measure.py` | **GENERAL** |
| Drive formula weights (1.0 / 1.6 / 2.2) | — | **TASTE** |
| Acceptable drive score | ≈ 3.3–3.8 | **TASTE** |
| Search terms (the eight mood strings) | — | **TASTE** |
| One consistent palette; no per-era instruments | — | **TASTE** |
| Start offset = first −12 dB point, minus 0.25 s | `energy_onset()` | **GENERAL** |
| Trim rather than time-stretch | `atrim` | **GENERAL** |
| Loop only when the asset is shorter than the section | — | **GENERAL** |
| Fade in 0.4 s first section / 1.2 s others; out 1.2 s | — | **TASTE** |

## SFX selection and placement

| setting | value | tag |
|---|---|---|
| Epidemic Sound only; nothing generated | — | **GENERAL** (for this pipeline) |
| Place the *perceived* moment on the beat | — | **GENERAL** |
| Per-file energy anchor at 15 % accumulated energy | `palette.py` | **GENERAL** |
| Zero the anchor when ≥ 40 % of peak inside first 30 ms | — | **GENERAL** |
| One-frame deadband on the rest | — | **GENERAL** |
| Trim leading silence once, at palette prep only | — | **GENERAL** |
| Peak-normalise hits to −3.0 dBFS | `palette.py` | **GENERAL** |
| Snap a hand beat to the nearest picture change within 1.2 s | — | **TASTE** |
| Resolve collisions by tier priority, never by strength | — | **GENERAL** |
| `--drop-weakest` | 0.35 | **TASTE** |
| Tier gains (−5 / −7 / −8 / −12 / −15 / −19 dB) | `TIERS` | **TASTE** |
| Tier guards (2.20 / 1.30 / 1.10 / 1.00 / 0.85 / 0.80 s) | `TIERS` | **TASTE** |
| SFX sit above the bed | — | **TASTE** |
| Anticipation swish at −0.13 s, −7 dB | — | **TASTE** |
| Weight layer at +0.035 s (+0.05 s each), −5 dB | — | **TASTE** |
| Weight pool configurable per video | `default_weight_cats` | **GENERAL** |
| What is *in* the weight pool | per subject | **TASTE** |
| Card guard (`CARD_SOLO`) | 0.45 s | **TASTE** |
| Hand beats survive guards via `solo_ok` | — | **GENERAL** |
| Hand beats survive mute windows | — | **GENERAL** |
| Density target | one per ~2.2 s | **TASTE** |
| Reuse cap | ×10 per 13 min, never twice in 30 s | **TASTE** |
| Rotator cooldown | 30 s (90 s for booms) | **TASTE** |
| Split takes only when the title says so (`x2`/`Variations`/`Impacts`) | — | **GENERAL** |
| Cap a cue at its shot via `max_len`, per cue never globally | — | **GENERAL** |
| `max_len` fade | `min(0.12 s, max_len/4)` | **GENERAL** |

## SFX bus polish

| setting | value | tag |
|---|---|---|
| Dip the speech band so effects stop masking consonants | principle | **GENERAL** |
| 2400 Hz −4 dB, 3600 Hz −3 dB | — | **TASTE** |
| High shelf 9 kHz −3 dB | — | **TASTE** |
| Low shelf 120 Hz +2.5 dB | — | **TASTE** |
| High-pass 45 Hz | — | **GENERAL** |
| Convolved room tail, wet 0.16 | — | **TASTE** |
| Makeup +2.8 dB | — | **GENERAL** (compensates the chain) |
| Never run ambience beds through the room impulse | — | **GENERAL** |

## Ambience beds

| setting | value | tag |
|---|---|---|
| Hand-assign every bed; never rotate | — | **GENERAL** |
| Event-type beds belong to the shot, not the section | — | **GENERAL** |
| Audit bed presence against the picture | `onscreen.py` | **GENERAL** |
| Presence threshold below which a bed is suspect | ~45 % | **TASTE** |
| Room tone exempt from the presence test | — | **GENERAL** |
| Beds carry their own fade | — | **GENERAL** |
| Default bed fade | 2.5 s | **TASTE** |
| `--bed-rms` default | −42 dBFS | **TASTE** |
| Ambience target | −42 to −43 dBFS | **TASTE** |
| Featured texture target | −37 dBFS | **TASTE** |
| Crowd target | −38 dBFS | **TASTE** |
| Test an unnamed bed for voices by pitch confidence | — | **GENERAL** |
| Voice-detection threshold (crowds 0.14–0.25, clear ≤ 0.04) | — | **TASTE** |

## Picture analysis

| setting | value | tag |
|---|---|---|
| Use redraw, not optical flow, on animation | — | **GENERAL** |
| Cut / action / element thresholds (0.15 / 0.02 / 0.004) | `visual_redraw.py` | **TASTE** |
| Coarse sheet finds the scene; ~1 s sheet finds the frame | — | **GENERAL** |
| Contact sheet 4×4 at 420 px, sampled 0.45 s after each cut | — | **TASTE** |
| Find the transition device before scanning for it | — | **GENERAL** |
| Card detector thresholds (white > 0.55, red × 100 > 0.9) | `cards.py` | **TASTE** |
| Red-card detector (`r>110, r−g>45, r−b>45`, > 0.55) | `fire.py` family | **TASTE** |
| `--scene-threshold` | 0.4 | **TASTE** |
| `--silence-db` / `--silence-min` | −30 dB / 0.5 s | **TASTE** |
| `sync_check.py --fps` must be the file's real rate | — | **GENERAL** |
| Expected sync: median ≈ 0 ms, ~70–75 % inside one frame | — | **TASTE** |

## Cold open

| setting | value | tag |
|---|---|---|
| Intro riser at `first_voice − 1.2 s`, −7 dB | `analyze.py` | **TASTE** |
| `under_voiceover` is computed but never read by the mixer | — | **GENERAL** (a limitation, not a choice) |

## Process

| setting | value | tag |
|---|---|---|
| Score the picture, not the animator's note | — | **GENERAL** |
| Never place a hit you have not seen | — | **GENERAL** |
| Run `preflight.py` + `overrun.py` before every render | — | **GENERAL** |
| Send 3–4 clips with picture before the full mix | — | **TASTE** |
| A note says what is wrong; it does not authorise a re-score | — | **GENERAL** |
| API keys from environment variables only | — | **GENERAL** |

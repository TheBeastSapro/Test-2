# The Most Effective Helmets in History Explained

Voiceover run, 2026-08-23/24. Source doc: Google Docs `12u6lmBie6po…` — the
title comes from the DOCUMENT NAME, not the script's H1, which is the
structural label `# Script`.

## Delivered

`The Most Effective Helmets in History Explained (final).mp3` — 12:59,
-14.4 LUFS, true peak -1.3 dBFS, 256 kbps. Opens on "Boar's Tusk Helmet",
closes on the outro.

## Spend: 13,332 characters

| chars | what |
|------:|------|
| 12,958 | first render, 53 sections |
| 155 | section 16 re-rendered — the voice dropped the ending on "flat-topped" |
| 374 | outro, added as section 54 |

Three stitches and four masters cost nothing. `generate.py --stitch-only`
re-stitches from cached takes for free; the wrapper cannot, and
`--from generate` will propose re-sending everything.

## Settings that are NOT the defaults

- **`--no-level-headings`.** Levelling retimed 8 of 11 chapter announcements
  and pinned 7 at the ±15% clamp. A/B'd against unlevelled, Sapro chose
  unlevelled and reported no big difference. The levelled master is kept at
  `.vo_…/superseded-levelled-headings.mp3`.
- **`--max-wpm` off.** The approved sound; the fast punchlines are the delivery.

## Read-check

15 of 53 sections flagged, 10 of them false — ASR orthography (numerals,
British spelling, apostrophes, compound boundaries), including three names
the voice read exactly as the pronunciation guide specifies. Five went to
Sapro as clips; he flagged only "flat-topped" and approved the rest
(Stahlhelm, Ambroise, Gjermundbu, Morion, sunburst).

## Script prep needed every time for a Docs export

Chapter titles arrive as bold paragraphs (`**Corinthian Helmet**`), which the
structure detector does not see — it found 1 chapter instead of 11. Convert
standalone bold lines to `##` headings before planning. The outro must be
inserted BEFORE the pronunciation guide heading, or it is stripped with it.

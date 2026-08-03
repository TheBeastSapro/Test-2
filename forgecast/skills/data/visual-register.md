# Photoreal vs Cinematic Register

Runs at the start of every visual generation. Decides whether a shot, a thumbnail, a B-roll
cutaway or a whole channel uses **authentic-amateur**, **cinematic-polished**, or a
deliberate mix.

One rule: **wrong register kills trust faster than wrong content.** A senior-finance channel
rendered with cinematic studio lighting reads as a Wall Street ad and the audience exits in
five seconds. A drill music video rendered as webcam-amateur reads as low-effort. Each niche
has a register its audience has been pre-conditioned to expect.

## What register is made of

Lighting style (studio vs natural) · composition (centre vs thirds vs intentional asymmetry)
· colour grade (clinical vs cinematic vs warm-natural vs stylized) · pose and expression
(controlled vs candid) · production cues (gimbal vs handheld vs locked tripod) · set design
(curated vs lived-in vs neutral).

## Register A — Authentic-amateur

Natural window light plus warm lamp fill, no three-point setup · slightly off-angle,
slightly imperfect framing · minimal grade, no LUT · candid expression, not a held smile ·
reads as a webcam at a desk · visible imperfection in the set (a coffee mug, an askew
picture) · **visible skin texture, age-appropriate, NO smoothing**.

Signals: *this is a real person sharing what they know. No production team, no agenda.*

Niches: senior finance / IRS / retirement · doctor advice and health authority · faith ·
genealogy · true-crime narrators · vlog/lifestyle · conservative commentary · mentor/coach.

Anti-pattern: rendering it with three-point lighting. One wrong detail — perfect skin,
perfect hair, a professional backdrop — collapses the trust signal.

## Register B — Cinematic-polished

Three-point key/fill/rim with intentional shadow placement · thirds executed precisely,
clean · graded with a LUT · posed or directed · steady camera, sometimes shallow depth ·
curated set, no accidental clutter · slight skin smoothing acceptable.

Signals: *production team, budget, quality, brand.*

Niches: music videos / drill / propaganda · premium documentary · channel trailers and hero
content · some tech reviews · high-production gaming · cinematic travel · branded reads.

Anti-pattern: using it for an authority/finance/health channel. Read as "ad" within seconds.

## Register C — Mixed

Host shots in A, B-roll and establishing shots in B, document overlays clean, title cards
and motion graphics in B.

Signals: *a real person sharing a real story, with quality production supporting it.* The
most common premium register.

Niches: news-hijack documentary · premium health authority · long-form interview ·
investigative content · long-form science explainer.

Anti-pattern: mismatch *within* one shot — an amateur host in studio lighting, or a
cinematic host with amateur B-roll. Both read as production confusion.

## Decision tree

1. **Niche.** Senior finance / health / faith / genealogy / mentor → A. Music video /
   propaganda / trailer → B. News-hijack docs / premium documentary / long-form science → C.
   Tech reviews → B for product hero, A or mid for talking-head. Gaming → highlights B,
   vlog-style A.
2. **Surface.** Host talking-head matches the channel register. B-roll may be one register up
   (mixed). Thumbnail can be any register but must pair coherently with the video. Title and
   end cards cinematic by default. Document overlays and screenshots Register A — clean.
3. **Audience.** 60+ leans A (older audiences trust amateur authenticity more). 25-45 tech
   leans B. Mixed leans C.
4. **Script.** Story-led / personal narrative → A or C. Information / data-led → C.
   Hype / entertainment → B. Reveal / investigation → C.
5. **Confirm before locking the channel's register.** Surface the proposal: *"Based on your
   niche and audience I'd recommend Register A — authentic amateur. This is the register
   that performs in your niche. Confirm?"* The operator can override; the niche default is
   the safe starting point.

## Per-niche table

| Niche | Host | B-roll | Thumbnail | Notes |
|---|---|---|---|---|
| Senior finance / IRS / retirement | A | A or mixed-light | A | Hard rule: never cinematic for host |
| Tech / AI / dev | A or mid | B (product hero) | A or B | Host A + product B |
| Gaming / Roblox / Minecraft | A | B (highlights) | B (saturated) | Energy register |
| Music video / drill / propaganda | B | B | B | Always cinematic |
| News-hijack documentary | A | B | B | Investigative pattern |
| True crime | A (narrator) | B (recreation) | B | Mournful register |
| Health / medical / supplements | A | A or mixed-light | A | Senior-trust mandatory |
| Real estate / home | A or mid | B (property hero) | B | Hybrid |
| Beauty / fashion | A | A | A | Personality-driven |
| Cooking / food | A | B (food hero) | B | Hybrid |
| History / explainer | A or none | B (recreation) | A or B | Faceless + B |
| Science | A or none | B (animation) | A or B | Mixed |
| Vlog / lifestyle | A | A | A | Personality-driven |
| Crypto / trading | A or B | B (charts) | B | Hype register often B |
| How-to / education | A | A or mixed-light | A or B | Practical |
| Fitness | A or B | B (workout hero) | B | Hype register |
| Faith / Christian | A | A | A | Reverent, trust |
| Politics / commentary | A or B | B | B | Rage register often B |
| Travel | A | B (location hero) | B | Aspirational |
| Comedy / shorts | A or mid | A or B | A or B | Personality |
| Documentary long-form | A or none | B | B | Hybrid mandatory |
| Ambient / sleep / focus | n/a | B | B | All B |

## The studio-lighting trap

The most common register failure: Register A is asked for, but the image model defaults to
studio lighting because that is what it was trained on.

Symptoms: three-point lighting visible · background blur deeper than a real home camera
gives · even frontal illumination · no visible window light · magazine-portrait composition.

Prevent it with explicit prompt language — *"natural daylight from one side, warm lamp fill
from another, NO studio lighting, NO three-point setup"* — window-lit reference images, and
the sample gate. When a host shot comes back with studio lighting, reject and regenerate.
This is the #1 failure mode for Register A.

## The over-grade trap

The opposite: Register B graded so hard it looks fake. Symptoms: everything teal-and-orange
· crushed blacks, blown highlights · visible LUT · unnatural skin tone. Specify moderation —
*"cinematic warm grade, subtle, not over-processed"* — and reference real cinematic content
rather than filter sets.

## Mixed-register coherence

Host and B-roll must feel like one video. The B-roll grade should be related to the host
grade, the palette shared, the pacing matched, and the aspect ratio identical. The failure
is a warm-natural host against cool-teal cinematic B-roll — two different videos.

Run a coherence check: put a host frame and a B-roll frame side by side. They must read as
belonging together. If not, regrade or regenerate.

## Switching register within a video

Some structures earn it: cinematic establishing open (B) → amateur-authentic host body (A) →
cinematic interlude at a reveal (B) → amateur close (A). The cinematic moments are earned
punctuation, not the default. What kills it is a switch with no narrative justification —
that reads as an error.

## Register as audience pre-screening

Register is the entry filter, not decoration. A retiree audience has been burned by polished
sales presentations and has learned to read gloss as *someone is selling me something* — so
with the exact same script, Register B underperforms by 30-40% in senior finance. A music
video audience expects production value, so Register A underperforms by 50%+ there.

These are not preferences, they are trained pattern-recognition responses. Never fight the
pre-trained expectation. Match the niche, match the audience, then differentiate *within* the
matched register rather than across registers.

## Anti-patterns

1. **Defaulting to cinematic** — models trend that way; actively prompt for amateur.
2. **Mixing registers within one shot** — authentic face plus cinematic background blur.
3. **Cinematic LUT on amateur content** — teal-and-orange on a home office ruins it.
4. **Amateur-authentic for music videos** — reads as low-effort.
5. **Studio-lighting tells** — three-point, even shadows, no window: Register A failed.
6. **Inconsistent register across episodes** — the audience stops knowing what the channel is.
7. **Switching mid-video without justification** — reads as a mistake.
8. **Forcing C when A would be cleaner** — cinematic B-roll on content that did not need it
   muddies the message.

## Checklist

Niche identified · audience demographic considered · register chosen per the table · new
channel: register surfaced for approval and locked to memory · existing channel: register
pulled from channel memory · the specific surface (host / B-roll / thumbnail / title card)
matched to register · coherence check across mixed-register shots · anti-patterns scanned —
no studio drift on A, no over-grade on B, no mismatch in C.

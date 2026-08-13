# EXPLAINTORY TITLE SCAN — STANDARD OPERATING PROCEDURE v1.4
## Trigger: Sapro says "title scan" (optionally with a video link, videoId, screenshot, or topic)
## Companion files: explaintory-channel-skill (current version), Competitor Sweep SOP v1.2, Scripting SOP v1.0, **Subject-Type Law v1.0**

**Where this sits in the pipeline:** The Title Scan is the FAST gate — validate one candidate (or discover 3–5) and produce a ship-ready reskin package in a single session. It does NOT replace the full Competitor Sweep SOP v1.2 (transcript teardown, comment mining, heatmap slot translation, visual-sync pass). A title that passes the scan still gets a full sweep before scripting begins. Scan → Sweep → Script. The scan decides *whether a vein is worth a sweep*; the sweep decides *how to mine it*.

> ## WHAT CHANGED IN v1.4
>
> **One change: §0.2 is reconciled with Scripting SOP Gate 7.** The stem
> `The Deadliest [X] From Every Era` was listed here as BURNED. It is not, and
> has not been since 2026-08-06 — the weekly scan of that date re-ran G6 and
> reversed the flag in its §8.1: *"the wrapper is not burned; the burn flag was
> built on a misread of the swarm."* The two corpses cited as evidence
> (Battles 1,390; Military Units 3,094) failed **G0 on subject class**, not on
> packaging, which is the exact error the Subject-Type Law exists to correct.
>
> Scripting SOP v1.6 Gate 7 had already been rewritten to match and carried a
> standing note that this file was unreconciled and that both must be edited in
> the same pass. This is that pass; Scripting SOP v1.7 drops the note.
>
> Evidence at time of writing (weekly scan 2026-08-13): Sword **116,416** at
> 9.4 days and still climbing · Weirdest Weapons **159,081** · Warships
> **159,357** · Weapons **513,673**. Four in-house instances against two
> third-party attempts, neither above 50K.
>
> **The live constraint is variant occupancy, not the wrapper.** Run exact-match
> on the precise `[X] from every era` string and take an unoccupied noun —
> `"sword from every era"` returned zero results, which is why that variant was
> available.
>
> **Nothing else in this file is changed.** No gate, no threshold, no procedure.
>
> ## WHAT CHANGED IN v1.3, AND WHAT DELIBERATELY DID NOT
>
> **v1.2 was working.** Its seven gates, its anchor-fusion rule, its §3 output package, its §3.5 thumbnail procedure and its bookkeeping discipline are unchanged and are reproduced verbatim below. Nothing that produced the 512K / 137K / 111K decisions has been touched.
>
> **Two things are added, both bounded:**
> 1. **G0 SUBJECT TYPE** — a new gate that runs *before* G1. It is the cheapest possible rejection and it catches the one failure mode the seven gates could not see (§1.0).
> 2. **A tiered competitor roster** replacing the stale five-channel list — but rotated, so a scan still pulls ~7 channels, not 25 (§0.1). The roster grew; the per-scan workload did not.
>
> **§6 STABILITY RULES is new and exists to stop this expansion from collapsing the scan.** Read it if a scan ever starts returning nothing, taking too long, or drifting off-format.

---

## 0. INPUT MODES

**Mode A — Target scan** (Sapro provides a video: link, videoId, screenshot, or exact title):
Validate that specific video as an anchor and produce the reskin package (§2–§4).

**Mode B — Open scan** (Sapro says "title scan" with no target):
Run discovery first, then validate the top 3–5 hits and produce a reskin package per qualifier.
Discovery config (proven reliable on this channel):
- `search_viral_videos_small_channels` with `minViews: 100000`, `sortBy: videoViews` — the curated breakout feed; 90-day window only
- `faceless_outliers_videos` with `minViews: 100000`, `minOutlierScore: 3` — semantic sweep; the outlier-score filter lives on this tool, not on the viral feed
- `search_videos` with `isExactMatch: true`, `sortBy: viewCount` on proven compound stems (see §0.2)
- Roster check per §0.1 — compute outlier multiples manually; do NOT trust `youtube_channel_outliers`
- **Keyword pollution guard:** never search bare "war" (matches warm/warned), "roman" (romantic), "sword" (gaming/anime), "armor" (gaming), **"banned weapon"** (Fortnite/Roblox/TF2/Destiny + Iran-Israel news). Always compound with deadliest/medieval/ancient/genius/failed/explained. Filter off-niche noise silently but state the count.
- Pagination discipline: nothing past page 2 — results degrade into unrelated content regardless of keyword specificity.
- `channelSubCount` in search results is untrustworthy (missing data defaults to 1) — verify subs via `youtube_channel_about` before citing.
- **Publish-date discipline [v1.3]:** relative-date text from `youtube_channel_videos` rounds to the nearest month and is systematically optimistic. Three anchors moved their dates in a single week when read properly, and all three moves cost runway. **Never issue a SHIP NOW verdict on a relative date.** Use `youtube_video_details` → `publishDate` for anything carrying a timing verdict.
- **Median discipline [v1.3]:** recompute every roster median every scan. Four of five medians moved inside four days in the 2026-08-03 run. Reusing last week's median silently inflates or deflates every multiple cited against it.

### 0.1 COMPETITOR ROSTER — TIERED ROTATION [NEW v1.3]

The old roster was five channels, re-pulled every week, which is why four scans in a row surfaced the same four carry-over anchors. The roster is now 25 channels **but only ~7 are pulled per scan.** Workload is flat; coverage is 5×.

**EVERY SCAN — fixed core (4 pulls).** These are the closest format twins and the ones currently winning the suggested surface.

| Channel | channelId | Why fixed |
|---|---|---|
| ExplainTory (own scoreboard) | UCfqJsOXexvOvaDe-KJSi09w | Always first |
| Cowball | UCkvUaMHVmw1K0bvE-kFRM8Q | Hardware taxonomy, outlier 7.17, 3 uploads in July |
| Mil Gear Explainer | UCeSv-5lk1uqGyO9zpNYMvrA | Hardware taxonomy, 53 videos, median 27K |
| Uncivil Engineer | UCfqxnFCPcIrkCMt_LXDZtjg | Weirdest-engine owner; decay curve must be tracked |

**EVERY SCAN — rotating pair (2 pulls).** Take the next two in the cycle, then wrap. Record which pair was pulled in §4 bookkeeping so the next scan continues the cycle.

`Scribble Scholar (UCu6S_MpYydihE-R_MMY1y5A)` → `Ravelin (UCf7-PDJ_l7HrH5k7iPgcS1A)` → `Swords Explained (UCl4eLtVC2rjfMAHXsobrk_Q)` → `Overscaled (UCBVoNQN9sJLP324gRKekdbQ)` → `Data illusion (UCLvzG3Axx3woai3kpnL_SNQ)` → `Statewide USA (UCOEgyETg3BbroC98G6gTI_Q)` → `Animated History (UCLuIudjbquBATgqkIJxQi6A)` → `Drawn of History (UC3l6ot2f6E6hxOOfMA3uIPQ)` → `Deep Cee Explained (UChED0mz8-ImpHXuVaAO8IWA)` → `krisis LOGS (UC6sd1KXJcFlH4ktvUmetpcQ)` → `MM Loadout (UCSphV_pGcwMijwaRdHRgLPg)` → `Military Simply Explained (UCrGlmof8fOL9RWLvRa_vHqw)` → `Sketch & Explain (UC9CQ3i6ISrXtMg0pf1EUi-w)` → `Paintify (UCyJR4fhuZIk1AD3-BzpQaPw)` → `Plot Twist Files (UCjK-uxbVjnptt8BySSGnARw)` → `Loony Throne (UC19C0C608BmSEcExuSJpqTw)` → wrap

**EVERY SCAN — suggested-surface check (1 pull, cheap).** `search_youtube_suggested_videos` with `isFromHomeFeed: true` on 2–3 of the channels pulled this scan. Presence and outlier score in the feed catalog is the only competitor-distribution proxy available; their Studio analytics are private and must never be claimed.

**MONTHLY ONLY — format benchmarks.** Study the engine, not the topic. Do not pull weekly; they move slowly and they crowd the scan.
Paint Explainer `UCnwUjPK7dXety-AJ4fNw_RQ` · Trust Me Bro `UC4GYgpgZzfMhYr9y6rs5O6Q` · Just a Rock in Space `UCol6LjFAUqYyZntAe_1n6-Q` · Agent Flappy `UCRi2h75k0cAsMin5TYxZJgw`

**MONTHLY ONLY — small over-performers.** The most instructive tier: all are at or below our size and beating their weight.
Weapon Programs Explained `UCjzdJXNsNExIPfuAMmcJXDA` (93.8×) · Scribble History `UCeFoC7D3yug1HSNJLc_mt0Q` (1.67K subs, 239K) · History Outline `UCYEKF5O3hF0fo8BzHuPabrA` · Paint Warfare Explainer `UCULL07PSUuJSjb5seHP5Q3Q` · Agent Canine `UCN-YJFJYFLM6k4EKvnxBkFw` · Paint Skool (888 subs, 320K)

**RETIRED from the weekly roster.** Professor Historian (cooling — non-compilation uploads at 1.1K–6.1K, and despite huge subs it barely surfaces in the feed catalog at outlier 1.96) and Arch Meld (median ~0.85K, decayed). Both may be re-pulled on cause; neither earns a weekly slot.

### 0.2 STEM LIST [v1.4]

Run exact-match on the house stems plus the imported engines. **Stems marked BURNED are checked to confirm they are still burned, never to build on.**

| Stem | Status |
|---|---|
| `Every [X] Explained` | HOT — 7 independent channels |
| `Every Failed [X]` | HOT — 15+ channels across 10+ niches |
| `The Weirdest [X] Explained` | VALIDATED house engine |
| `Every Genius [X] Explained` | VALIDATED house engine |
| `Every Hidden [Advantage/Weakness] of Each [X]` | WATCH — 1 channel at scale |
| `Why [Institution] Rejected The World's Best [X]` | WATCH — 1 channel, 93.8× |
| `Every [X] Ranked By [Unexpected Metric]` | WATCH — 4 channels, proven at 888 subs |
| `Every [X] in [N] Years` | WORKING — 3 channels |
| `The 7 Levels of [X]` | WORKING — 5 channels, off-niche so far |
| `The [Superlative] [X] From Every Era` | **VALIDATED house engine [v1.4]** — burn flag reversed 2026-08-06 (§8.1 of that scan). Four in-house instances: 513,673 · 159,357 · 159,081 · 116,416. The two corpses failed G0 on subject class, not packaging. **Check variant occupancy** by exact-match on `[X] from every era` before committing |
| `Explained in 10 Minutes` | **BURNED** — 199 sub-10K copies since 2026-06-01 vs 5 hits. Odd runtimes (8/9/11/12) outperform round ones |
| `Met Their End` | **BURNED** — short-form clone swarm, no long-form proof |
| `Every Single [X]` | **DEAD** |

---

## 1. VALIDATION GATES

### 1.0 GATE ZERO — SUBJECT TYPE [NEW v1.3] · runs BEFORE G1

**Classify what the candidate is *about* before testing anything else.** This is the cheapest rejection available and it catches the failure mode the seven gates could not see: a candidate can pass all seven on packaging while belonging to a subject class this channel has never converted on.

| Class | Definition | Verdict |
|---|---|---|
| **OBJECT** | A physical thing that can be drawn and that did something — weapon, ship, machine, fortification, substance, vehicle, kit | **GO** |
| **SYSTEM** | A repeatable method or structure — tactic, formation, doctrine, logistics, engineering principle | **GO** |
| **PEOPLE** | A roster of humans or human groups — units, warriors, commanders, ranks, dynasties, roles | **STOP** |
| **EVENT** | A thing that happened — battles, campaigns, invasions, sieges-as-events | **STOP** |

**The evidence, on our own channel, with no overlap between the groups:**

| Class | Videos | Views |
|---|---|---|
| Objects | Deadliest Weapons · Warships · Weirdest Weapons | 512K · 137K · 111K |
| Systems | Roman Tactics · Napoleon Tactics | 145K · 52K |
| People | Military Units · Legendary Warriors Died | 2.8K · 2.7K |
| Events | Deadliest Battles | 1.3K |

Five for five on things and systems. Zero for three on people and events. The worst thing/system video beats the best people/event video by 19×.

**Why the seven gates missed it, and why retention data actively hid it:** AVD and views are *inversely ranked* across all four benchmarked videos — Military Units posted the channel's best AVD (41.9%) and near-worst views (2.8K); Deadliest Weapons posted the worst AVD (27.9%) and best views (512K). **Subject type governs the click; structure governs retention.** Full reasoning in `claude/explaintory-subject-type-law-v1.md`.

**The override, if a people/event candidate is ever advanced:** it must carry a hardware or system spine — the video is *about a thing*, with people present as operators of it. "Every Rank in a Medieval Army" is people. "Every Piece of Kit a Medieval Soldier Carried" is objects with the same research. The second is the shape that ships. State the override in writing or do not advance the candidate.

**Watch the word, not the vibe.** "Every Failed Siege in History" is an EVENT and carries the Battles risk. "Every Siege Engine Explained" is an OBJECT and is clean. Same subject, different class — check which one the *title* promises.

### 1.1 THE SEVEN GATES (unchanged from v1.2 — all must pass; one fail = REJECT, say why, move on)

| Gate | Pass condition |
|---|---|
| G1 Scale | ≥100K views OR ≥3× the source channel's median (computed manually from raw view data) |
| G2 Faceless proof | Proven by a faceless / Paint-style / explainer-format channel, OR a faceless reskin of a talking-head original already exists and performed. A talking-head-only hit does not prove the format survives the translation |
| G3 Clone window | If the anchor is a breakout: are we inside the ~2–3 month entry window? Inside = timing bonus. Outside = the vein must be evergreen on its own merits (Arch Meld decay curve: 449K → 98K → 0.5–1.3K; a big number on a 3rd+ clone is a trap, not a signal). Log the anchor's position on the decay curve explicitly |
| G4 Engine match | Maps to a proven ExplainTory engine, or a verified transferable engine. A NEW engine needs 2+ independent channel proofs before it can ship (single-channel outliers = "watch," not "act"). **[v1.3] Engine proof from an unrelated niche counts, and counts strongly — `Every Failed [X]` is proven across 10+ niches — but engine proof never substitutes for G0 or for subject demand** |
| G5 Red lines | Not modern-only (WW2/Nuclear flop pattern — cross-era sweeps folding famous modern items into a historical arc are fine, modern-only is not). Not a "Deadliest Battles" / "Military Units" retread — **[v1.3] this line is now the special case of G0; G0 is the general rule**. Not a framing trap: armor collides with gaming search intent, siege weapons with Rust, bare "castle defense" with tower-defense games, **"banned weapon" with Fortnite/Roblox/Destiny and Iran-Israel news** — qualifiers (medieval/ancient/in History/explained) are REQUIRED if the subject is contested. **[v1.3] A framing trap is a fixable condition, not an automatic reject — apply the qualifier remedy before rejecting** |
| G6 Near-clone / burn check | Run `search_videos` `isExactMatch: true` on the exact candidate title AND its closest phrasings. Hard stop conditions: (a) a near-identical title already exists and is underperforming (Military Units precedent: prior identical title dead at 3.2K = hard stop that was missed); (b) a clone swarm is visible (multiple recent copies at trivial views = burned vein). Soft condition: same-lane competitor published a near-identical title <6 months ago → may advance ONLY with a written differentiation plan (Sweep SOP v1.2 Stage 4 rule: different hook + different structural spine + one content layer they lack) |
| G7 Vein check (internal) | Mine each vein once. WEAPONS, ROME, NAVAL are each mined. A candidate touching a mined vein needs a genuinely new angle (Swords ≠ Weapons re-skin: it survived because the subject class narrowed and triple-validation existed), not a cosmetic re-title. **[v1.3] Also check roster collision against LIVE videos — a candidate whose entry list overlaps a currently-surging video cannibalises it** |

---

## 2. ANCHOR FUSION (the core move) — unchanged from v1.2

Best reskins fuse TWO proofs:
- **Premise anchor** — the video proving the *subject* has demand (e.g., Deep Cee swords 102K + Arch Meld 449K proving sword demand)
- **Packaging anchor** — the proven *stem or engine* that wraps it (house stems: "The Deadliest [X] From Every Era Explained" / "Every Genius [X] Explained"; imported engines: "ACTUAL" contrarian, mystery framing, `Every Failed [X]`)

Rule: the final title must be exactly **ONE twisted variable** away from each anchor, verbatim copy of neither. ExplainTory twist axes:
- **Subject class** (weapons → swords → armor; warships → naval tactics)
- **Civilization** (Roman → Mongol → Viking → Ottoman)
- **Era span** (from-every-era sweep ↔ single-era deep dive)
- **Framing engine** (capability → mystery → debunk inversion → **failure**; proven multiplier: mystery framing dramatically outperforms capability framing on the *same subject*)
- **Structure** (listicle ↔ single-battle narrative ↔ daily-life question)

Never clone verbatim against a video that is currently surging — competing head-to-head with a hot incumbent inside its own seed window is the losing side. Reskin into the *adjacent* lane instead.

---

## 3. OUTPUT FORMAT (every title scan returns this, per qualifying anchor) — unchanged from v1.2 except §3.0a

**0a. SUBJECT CLASS: OBJECT / SYSTEM / PEOPLE / EVENT** — *required, stated first, per G0.* One line. If PEOPLE or EVENT, the written override must appear here or the candidate does not advance.

0. **SUBJECT DEMAND: STRONG / WEAK / UNVALIDATED** — *required on every candidate, stated before anything else.*

   This is a **reporting requirement, not a gate.** It never blocks a title on its own; it makes the risk visible so the decision is made with eyes open rather than by accident.

   The gates below test *packaging* — engine match, clone window, vein, framing traps. A candidate can pass all of them on packaging alone while nobody has ever shown that anyone wants the subject. That is the exact shape of both Deadliest Battles (1.1K) and Deadliest Military Units (2.3K): good frame, unproven premise. The standing channel rule is **subject demand beats format every time**.

   - **STRONG** — at least one video proves demand for *this subject* (not this frame), ideally on a small channel at a high multiple. Cite it: title, views, subs, multiple.
   - **WEAK** — some signal exists but it is single-source, off-lane, or heavily polluted.
   - **UNVALIDATED** — no demand proof found, or the search returned pollution. **Say which**, because "no proof found" and "proof impossible to search for" are different situations.

   Never let engine proof stand in for premise proof, and never report only the stronger of the two.

1. **PRIMARY TITLE** — house architecture preserved exactly. Singular subject where the swords precedent applies ("Sword," not "Swords"). Proven power words: "Deadliest," "Genius," "Weirdest," "Failed," "Explained." ≤10 words.
2. **2 backup variants** — for post-upload title A/B only, never pre-launch dithering.
3. **Anchor citation** — which video(s), views, subs (verified, not `channelSubCount`), outlier multiple, age, and position on the clone-decay curve.
4. **Format assignment** — era-block listicle (default), single-battle narrative, or daily-life question. Target: 1,600–2,000 words (~8:40–10:50 at the measured 185 WPM). Entry tier plan per Scripting SOP (Heavy/Medium/Light).
5. **Thumbnail to pair** — full procedure in §3.5.
6. **Content spine** — 4–6 beats: candidate opener (most visually shocking, not most famous), rehook-slot candidate, closer register (devastation, not surprise), spoken era blocks if from-every-era, and the meta-pivot carrier if one exists.
7. **Timing verdict** — SHIP NOW (inside a live clone window, state remaining days), SHIP NORMAL (evergreen vein), or HOLD.
8. **Slate position** — where it slots against the current pre-sweep slate and what it displaces or defers.

### 3.5 THUMBNAIL-TO-PAIR PROCEDURE (mandatory per qualifying anchor) — unchanged from v1.2 except Step 2 and Step 4

The thumbnail is copied from a PROVEN thumbnail the same way the title is copied from a proven stem. Never invent packaging from scratch.

**Step 1 — Pick the source thumbnail.** Default: the premise anchor's own thumbnail. If it's face-dependent, stock-photo-based, or otherwise untranslatable to Paint-style, borrow the packaging anchor's layout instead and say which was chosen and why. **Always include the direct link** (`https://www.youtube.com/watch?v={videoId}`) so Sapro can open the source and hand it to the animator.

**Step 2 — Name the click device.** One line: WHAT in the source thumbnail does the click work. Recurring devices:
- **Single hero object** — one big subject, silhouette-legible at browse size. **[v1.3] This is now the default.** The 2026-08-05 adjacency pull found the panel-grid look is what the dated big-channel listicles and the failing micro-channel copycats both use; the adjacent thumbnails that actually performed were single-hero images.
- **Panel grid** (3–4 panels, one label each) — the house device; use for compilations and completeness promises, where signalling *quantity* is the point
- **Superlative label in caps** — instant read at feed size
- **Timeline / era arrow** — carries the "From Every Era" promise visually
- **Crossed-out myth** — pairs with debunk inversion
- **"?" mystery device** — pairs with mystery framing only

**Step 3 — Paint-style translation.** State what gets dropped (faces, photo-realism, licensed/game imagery, competitor branding) and confirm the click device survives as a simple drawing. If the device WAS photorealism or a face reaction, it does not translate — borrow a device from another proven thumbnail in the same cluster (soft fail: title still ships).

**Step 4 — Concrete build spec.** Every thumbnail-to-pair line specifies:
- Panel count and layout (or single-subject full-frame)
- Labels with exact spelling written out (TORSION precedent: spelling errors have shipped before — the spec is the spellcheck)
- Text budget: ≤4 words total; prefer the superlative word + subject nouns
- **[v1.3] CAPTION GATE — the label must state a consequence, a verdict or an absurdity, never just the object's name.** Confirmed across three independent channels in three different subjects: Agent Flappy (presidents), Mil Gear Explainer (firearms), Cowball (firearms). ❌ PANJANDRUM / TSAR BOMBA / TRIREME. ✅ CHASED ITS OWN CREW / SHOCKWAVE CIRCLED EARTH 3× / RAMMED SHIPS IN HALF. A name means nothing to a stranger on a home feed; a consequence opens a gap they have to close. A hand-drawn silhouette reads cleaner at 168px than a photo cut-out, so the caption can go larger than the competitors'.
- Panel order: strongest-recognition subject in the top-left/first read position
- Accuracy: labeled items must match the animator accuracy reference note — the thumbnail is a promise the script must keep

**Step 5 — Small-size test + B-variant.** Must read at 168px: if a panel label blurs, cut the label and let the drawing carry it. Provide ONE B-variant (usually: single-subject ↔ panel grid swap) — for A/B only after 48–72h of first-impression data from the Studio Reach tab, never before.

---

## 4. BOOKKEEPING (always, no asking)

- Save the scan as a versioned file: `claude/titlescan-weekly-YYYY-MM-DD.md` using today's real date (check with bash). Increment the filename, never overwrite. A scan "on record" means this file exists, not a memory of a chat.
- **[v1.3] Record which rotating pair was pulled** (§0.1) so the next scan continues the cycle rather than restarting it.
- Update the slate: note the candidate's verdict (SHIP NOW / SHIP NORMAL / HOLD / REJECT) and its position vs the standing pre-sweep slate. **[v1.3] Include each slate item's SUBJECT CLASS.**
- **[v1.3] REFRESH THE TITLE BANK.** After writing the scan, update `claude/explaintory-title-bank-v1.md` so it reflects this run: bump its "Last refreshed" date, move any newly-gated candidate into Tier A, demote or delete anything this scan rejected, promote Tier B entries whose outstanding check now passed, and update §5 VEIN STATUS if a vein was mined or opened. The bank is what answers "what should I cover next" in a single turn — a stale bank is worse than none. If nothing changed, bump the date and say "no change."
- If a new stem or engine earns its 2nd/3rd independent proof during the scan, flag it explicitly as a channel-skill update candidate (versioned skill file, never overwritten).
- A SHIP verdict automatically queues the full Competitor Sweep SOP v1.2 as the next action — the scan never feeds the Scripting SOP directly.

---

## 5. STANDING JUDGMENT RULES

- **[v1.3] Subject class first, everything else second.** G0 is not a tiebreaker. A PEOPLE or EVENT candidate that passes all seven gates brilliantly is still a stop.
- **Timing beats vein depth:** a 3×+ breakout aged <3 weeks in an unmined vein outranks a stronger evergreen anchor — the suggested-shelf window is forming NOW, and suggested traffic is the compounding tap this channel needs.
- **The clone window is 2–3 months, and the clock started at the breakout's publish date, not the scan date.** State remaining runway in days on every SHIP NOW verdict.
- **Aggregate CTR/AVD will not tell you if this works.** They are channel constants across hits and misses. The scan's job is topic freshness + early-cohort viability.
- **[v1.3] High AVD is not a green light.** AVD and views are inversely ranked on this channel. Military Units holds the channel's best AVD and did 2.8K. Never cite retention as evidence that a subject will convert.
- **CTR/impressions are never retrievable via NexLev.** Post-upload verification is manual: YouTube Studio → Reach tab at 48–72h. Say this in the verdict; never estimate.
- **[v1.3] Competitors' Studio analytics are private and can never be retrieved.** The only legitimate proxy is `search_youtube_suggested_videos` feed-catalog presence plus `get_similar_videos` adjacency. Never claim competitor traffic-source data.
- **Report subject demand and engine demand separately, always.**
- **Subject beats format.** "From Every Era" did not save Battles or Military Units.
- **[v1.3] Engine transfer across niches is real evidence and should be weighted heavily** — `Every Failed [X]` works in firearms, anime, business, sports, tech and history. But an engine that transfers still has to land on an OBJECT or SYSTEM, and it still has to clear G5's framing-trap test with qualifiers applied before rejection.
- If nothing passes, say so plainly. No anchor = no production. Never soften a REJECT into a "maybe."

---

## 6. STABILITY RULES — protecting the scan from this expansion [NEW v1.3]

The roster grew 5×. These rules exist so the weekly scan stays as fast and as decisive as it was at v1.2.

1. **Per-scan pull budget: ~7 channels.** 4 fixed + 2 rotating + own scoreboard. If a scan is running long, cut the rotating pair before cutting anything else. Never cut the own-channel scoreboard, and never cut G0.
2. **G0 is a filter, not a wall.** If G0 rejects every candidate in a run, that is a finding — report it plainly per §5 and spend the remaining effort on the OBJECT/SYSTEM veins that are still open (currently: siege engines, fortifications, armour, cavalry-as-hardware, failed weapons). Do not relax G0 to manufacture a candidate.
3. **Carry-over anchors get a delta, not a re-derivation.** Re-pull the anchor's live views, exact publish date and multiple; do not re-run the full §3 package. Point at the scan that holds it. This is what keeps the scan short.
4. **Full §3 packages are for NEW qualifying anchors only** — plus any carry-over whose verdict changes.
5. **One scan may not open more than 3 new full packages.** More than that means the scan has become a research document; split it and write the research as its own doc (the 2026-08-05 roster expansion is the precedent).
6. **If two sources disagree, say so and pick.** The 2026-08-05 run had one pass recommending "Met Their End" and another showing it swarming. State the conflict, state the resolution, move on. Do not average.
7. **Monthly tiers are monthly.** Resist pulling Paint Explainer or Trust Me Bro weekly because they are interesting. They move slowly and they crowd out the peer-scale channels where the actionable signal lives.
8. **The scan's output contract is unchanged:** scoreboard → discovery summary → anchors with full §3 packages → REJECTS → watch list → consolidated slate. If that shape is drifting, the scan is drifting.

---

*v1.3 (2026-08-05) — adds G0 SUBJECT TYPE as gate zero, replaces the stale five-channel roster with a 25-channel tiered rotation at flat per-scan cost, adds the caption gate to §3.5 Step 4, makes single-hero the default click device, adds publish-date and median discipline, adds §6 stability rules. Seven gates, anchor fusion, §3 output contract and bookkeeping are unchanged from v1.2. Origin: the Subject-Type Law v1.0 and the 2026-08-05 roster expansion.*
*v1.2 — subject-demand strength is a REQUIRED reported line on every candidate (reporting, not a gate). v1.1 — VO rate corrected to measured 185 WPM. v1.0 — adapted from the TitleScan SOP v1.1 (finance channel) for ExplainTory, July 2026.*

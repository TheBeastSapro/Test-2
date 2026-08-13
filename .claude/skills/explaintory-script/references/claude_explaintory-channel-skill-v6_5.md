---
name: explaintory-channel
description: Channel-specific script writing skill for ExplainTory — a weapons/military explainer YouTube channel using a casual but restrained dry-wit voice. Use this skill whenever writing scripts for the ExplainTory channel. Combines with FacelessOS core skills (script-structures, retention-mechanics, authenticity-audit) but overrides their generic guidance with channel-proven specifics derived from retention data. Apply automatically when the topic is weapons, military history, military organizations, military technology, or military tactics. Handles two formats: Listicle (default, proven) and ENTIRE History (adapted from outlier videos), plus the From Every Era era-block variant. Compatible with the explaintory-punchy-dark-wit-overlay skill, which may be loaded after it and which itself runs in two modes — DRY WIT or DRAMATIC. Ask which voice state before drafting: base, dry wit, or dramatic.
---

# ExplainTory Channel Script Writing Skill

This skill captures everything proven about how the ExplainTory channel performs. It overrides generic FacelessOS defaults with channel-specific calibration based on real retention data.

> **v6.5 change (2026-08-09):** the overlay gained a second mode, so there are now **three voice states, not two** — base, dry wit, dramatic. v6.3's OVERLAY RECONCILIATION described only two, which is why a drafting session asks "base or dry wit?" and never offers the dramatic option. This version rewrites that subsection to name all three, points at the v1.1 overlay file by path, and grants the overlay one further carve-out (fact-floor enforcement scale) that v1.1 claims from its side. Marked **[v6.5]**. **Nothing else in this file is changed** — no doctrine, no Fix, no format rule, no threshold.
>
> **v6.4 change (the Subject-Type Law, 2026-08-05):** the v6.2 four-video benchmark was built entirely from `audienceWatchRatio` curves and **was never cross-checked against view counts**. When it was, AVD and views turned out to be *inversely ranked* across all four videos. The AVD tier table was therefore recommending, on retention grounds, the one subject class that has never converted on this channel. This version adds **THE SUBJECT-TYPE LAW** as doctrine principle #0 — it sits above every other rule in this file — and patches the three places where v6.3 implied that people-subjects are a normal choice. Marked **[v6.4]** at each location. Full derivation in `claude/explaintory-subject-type-law-v1.md`.
>
> **v6.3 merge (2026-07-28):** two separate v6.2 files existed — one adding the **WRITE MODE** rule, one adding the four-video retention diagnosis and the five mandatory fixes. This version is the union of both. WRITE MODE is preserved as **doctrine principle #10**. v6.3 added an **OVERLAY RECONCILIATION** subsection under VOICE CALIBRATION.
>
> **v6.2 change (four-video retention comparison, 2026-07-27):** the channel's retention was re-diagnosed using lifetime 100-point curves from four videos. The result splits the channel into two families — **listicle 39–42% AVD, era-block 28–30% AVD**. Added the **FOUR-VIDEO BENCHMARK**, **five mandatory rules**, doctrine principle **#9 survivor mechanics**, and **replaced the aspirational retention checkpoint table with measured, achievable targets**.
>
> **v6.1:** added the format-agnostic **RETENTION DOCTRINE**, corrected the From Every Era opener rule, recalibrated VO pace to the measured **185 WPM**.
>
> **v6.0:** the **FROM EVERY ERA spoken-era-block variant**. **v5.9:** the **Fact staging** rule. **v5.7:** total length retargeted to **1,600–2,000 words**, entry length variable by explanatory load. **v5.6:** outcome-type variety, the comprehension analogy, the franchise/sequel rule, commit-to-the-skeleton topic philosophy, the misdirect-then-deflate opener shape.

**Combine with FacelessOS core skills.** This skill assumes you have also loaded:
- `faceless-scripts-os-master.md`
- `retention-mechanics-skill.md`
- `script-structures-skill.md`
- `authenticity-audit-skill.md`

When in conflict with generic FacelessOS guidance, **this skill wins** — because it reflects this specific channel's actual performance data.

---

## 0. THE SUBJECT-TYPE LAW [v6.4] — sits above everything else in this file

**ExplainTory converts on THINGS and SYSTEMS. It does not convert on PEOPLE or EVENTS.**

| Subject type | Videos | Views | Verdict |
|---|---|---|---|
| **Objects / hardware** | Deadliest Weapons · Deadliest Warships · Weirdest Weapons | 512K · 137K · 111K | **3 for 3** |
| **Systems / tactics** | Roman Battle Tactics · Napoleon Battle Tactics | 145K · 52K | **2 for 2** |
| **People** | Deadliest Military Units · How Every Legendary Warrior in History Died | 2.8K · 2.7K | **0 for 2** |
| **Events** | Deadliest Battles From Every Era | 1.3K | **0 for 1** |

No overlap between the groups. The worst thing/system video beats the best people/event video by 19×.

*(Two videos sit outside the split and are explained by existing rules: Most Feared Military Weapons of WW2, 6.4K — an object killed by the modern-only red line. Every Advanced Tech of the Roman Empire, 2.5K — an object killed by capability framing on a civilian-tech subject.)*

### 0.1 Why this was invisible until now — retention and views are INVERSELY ranked

| Video | Subject type | AVD | Views |
|---|---|---|---|
| Deadliest Military Units | People | **41.9%** (channel best) | **2,800** |
| Napoleon Battle Tactics | Systems | 39.1% | 52,000 |
| Weirdest Weapons | Objects | 30.4% | 111,000 |
| Deadliest Weapons | Objects | **27.9%** (channel worst) | **512,000** |

Perfect inverse rank correlation across all four benchmarked videos. This is not a paradox:

- **Subject type governs the CLICK.** Objects and systems get served and clicked; people and events do not.
- **Structure governs RETENTION.** People subjects retain beautifully because recognition carries the seams for free. That finding is real, measured, and unchanged.
- **The channel had been optimising the variable that does not gate views.**

Military Units posted the best AVD and the best survivors-kept in channel history and did 2,800 views. That was never a content or retention failure — it was a click-and-distribution failure, and no amount of retention work would have fixed it. Confirmed independently: the adjacency graph ExplainTory sits inside is shaped like hardware, so a people video is orphaned from the cluster the channel already owns.

### 0.2 The rule, operationally

**Before choosing a topic, classify it.**

| Class | Definition | Verdict |
|---|---|---|
| **OBJECT** | A physical thing that can be drawn and that did something — weapon, ship, machine, fortification, substance, vehicle, kit | **GO** |
| **SYSTEM** | A repeatable method or structure — tactic, formation, doctrine, logistics, engineering principle | **GO** |
| **PEOPLE** | A roster of humans or human groups — units, warriors, commanders, ranks, dynasties, roles | **STOP** |
| **EVENT** | A thing that happened — battles, campaigns, invasions, sieges-as-events | **STOP** |

**The override, if a people/event topic is ever commissioned:** it must carry a hardware or system spine — the video is *about a thing*, with people present as operators of it. "Every Rank in a Medieval Army" is people. "Every Piece of Kit a Medieval Soldier Carried" is objects with the same research. The second is the shape that ships. State the override in writing or do not write the script.

**Watch the word, not the vibe.** "Every Failed Siege in History" is an EVENT. "Every Siege Engine Explained" is an OBJECT. Same subject, different class — check which one the *title* promises.

**Never cite high AVD as evidence a subject will convert.** That inference is exactly backwards on this channel.

---

## CHANNEL IDENTITY

**Channel:** ExplainTory
**Niche:** Weapons, military history, military organizations, military technology, and military tactics — explained simply
**Format heritage:** Originally Paint-style drawings, but scripts are now produced as pure narration with no visual cues in the script itself. The numbered entry/era headers (`## 1. Name`) are navigation aids only — strip them before sending the script to TTS or VidRush, or they will be read aloud. EXCEPTION, heavily restricted: in the "From Every Era" variant, **at most two** era headers are read aloud — see Fix 2.
**Subscriber count:** ~4,290 and growing (was ~3,140 at v6.2)

### FOUR-VIDEO BENCHMARK [v6.2, annotated v6.4]

Measured 2026-07-27 from lifetime `audienceWatchRatio` curves. This table is the channel's ground truth **for structure**. Every retention target elsewhere in this file is calibrated to it.

| Video | Format | Length | AVD | 0:30 | 1:00 | 1:30 | End | Survivors kept | Views |
|---|---|---|---|---|---|---|---|---|---|
| Military Units | Listicle | 11:11 | **41.9%** | 75.5% | 63.7% | 57.9% | 27.6% | **43.3%** | **2.8K** |
| Napoleon Tactics | Listicle | 12:04 | **39.1%** | 74.2% | 56.9% | 53.3% | 25.5% | **44.9%** | 52K |
| Weirdest Weapons | Era-block | 12:21 | **30.4%** | 78.2% | 46.2% | 43.2% | 14.9% | **32.2%** | 111K |
| Deadliest Weapons | Era-block | 15:16 | **27.9%** | 72.4% | 49.9% | 45.2% | 15.2% | **30.4%** | **512K** |

**[v6.4] The Views column is new and it changes how this table must be read.** The original table had no view data in it, which is how the channel spent months treating Military Units as the model to emulate. **Copy this table's structural lessons. Never copy its subject-class implications.** See §0.

**Survivors kept** = end-of-video retention ÷ 1:00 retention. It isolates mid and late bleed from first-minute loss, and it separates the two families more cleanly than AVD does: 43–45% listicle versus 30–32% era-block. Track it on every video.

**Three readings that must inform every script:**

1. **The hook is not the problem.** Weirdest Weapons has the best 0:30 on the channel (78.2%, above the 70% golden benchmark) and the worst AVD. A benchmark hook followed by a bad thirty seconds is worse than a decent hook followed by a good one.
2. **The gap opens in one bucket.** Every video on this channel drops in the 36–52 second window. Only the size differs: Military Units loses 5.8 points there, Napoleon 14.2, Weirdest **17.0 points between 0:37 and 0:44**. See Fix 1.
3. **Beating the viral video is not a pass mark.** Deadliest Weapons did 512K views on packaging while retaining at 27.9%. Benchmark scripts against the listicle family, never against another era-block video.

**[v6.4] A fourth reading, added:** these four videos are ranked in exactly reverse order by views. Retention work is worth doing — the 2026-08-05 analytics pull shows relative retention below the peer median for the entire runtime of the breakout, which is capping suggested placement — but retention is the *second* decision. Subject class is the first.

### AVD tiers, measured

| Subject class | Measured AVD | Notes |
|---|---|---|
| Famous, distinct, human subjects (elite units, named people) | **39–42%** | Retention ceiling. Recognition carries the seams for free. **[v6.4] AND THE DISTRIBUTION FLOOR — this class posts the channel's best AVD (41.9%) and its worst views (2,800). Use this row to calibrate STRUCTURE TARGETS ONLY. Never use it to choose a subject. See §0.** |
| Abstract subjects with strong structure (tactics, systems) | **39%** | Requires open loops at every seam to hold. **[v6.4] This is a GO class — 145K and 52K.** |
| Obscure / novelty rosters in era blocks | **28–30%** | Structurally handicapped. Never run solo without the Fix 2–3 corrections. **[v6.4] Also the channel's highest-converting class — 512K and 111K. Fix the structure; keep the subject.** |

Novelty rosters are banned for solo carry. "Weirdest"-class framing is packaging only, and must always be loaded with recognized subjects.

### What the channel is
A serious-but-conversational explainer channel. The audience comes to *learn*, not to be entertained. They click because they want to understand a weapon, a military system, a tactic, or a military force — and they expect to actually understand it by the end.

### What the channel is not
- Not a comedy channel — humor is sparse, restrained, dry
- Not a documentary channel — no cinematic prestige tone
- Not a hot-take channel — no opinions disguised as analysis

### No outro
This channel does NOT use outros. Scripts end on the final entry's resolution. No "I'll see you in the next one," no CTA, no meta-lesson, no sign-off. The final entry's last sentence is the script's last sentence.

---

## RETENTION DOCTRINE — format-agnostic, sits above every format

Derived from mapping retention curves second-by-second against transcripts and visuals. These principles are not a format. They apply to Listicle, ENTIRE History, From Every Era, the Weirdest overlay, and any future format. When a format rule and this doctrine conflict, the doctrine wins. **[v6.4] When this doctrine and §0 conflict, §0 wins — it is the only thing in this file that outranks the doctrine.**

### 1. Payoff proximity (the master principle)
Viewers do not leave before a payoff. They leave in the gap AFTER one, when the next promise hasn't been made yet — and they leave in the fifteen seconds *before* a payoff they have stopped believing is coming. Every measured drop on this channel sits in one of those two gaps. The unit of retention is therefore not the entry or the block — it is the **promise→payoff cycle**, and the script's job is to keep the next promise arriving before the last payoff's credit expires (~10–15 seconds). Per format: in a Listicle, the entry's kicker doubles as the next entry's setup pressure; in From Every Era, weapons chain inside blocks so the block never coasts; in a single-battle narrative, the battle is decomposed into a chain of small questions rather than one long question.

### 2. The script is the storyboard
On a Paint channel, narration that cannot be drawn is retention debt. Every sentence must answer "what is on screen while this is being said" — and the answer must change every ~8–10 seconds in minute one, every ~15 seconds after. Highest-debt sentence types, in order: abstract bridges, era theses, historian quotes without a scene, biographical setup before the subject has done anything. None are banned; each must either carry a drawable image in its own words or ride on a scene that is still moving. Write the visual INTO the sentence ("the file proposed sealing live chickens inside") rather than trusting the animator to invent one.

### 3. Setup after payoff, at every scale
In medias res is not just an opener trick — it is the default at video, block, and entry scale. The subject acts first; the inventor, the date card, and the context arrive after the viewer has a reason to care. The bat bombs entry spent 15 seconds on a dentist and a mailbox before showing a bat; the curve stepped down exactly there. Reverse it: bat with bomb first, dentist second.

### 4. Predictability is an exit ramp
Uniform structures teach viewers where the exits are. Spoken headers, same-shaped entries, kickers landing on schedule — after three repetitions the viewer can time their exit to the seam. Counters, used deliberately: vary entry lengths within a video (the tier system already does this — protect it); let one entry in each script break the expected shape; stagger seams so audio and visual do not cut together (J-cut); occasionally withhold a header and let the era change reveal itself through the content. **[v6.2] The last of these is no longer occasional — see Fix 2.**

### 5. Adaptive entry shaping (replaces beat-filling)
Before writing any entry, name in one word what actually holds viewers for THIS subject: **spectacle** (claw, hwacha), **absurdity** (chickens, square bullets), **irony** (Panjandrum chasing its own generals), **stakes** (Davy Crockett's arithmetic), **mystery** (coal torpedo). Then shape the entry to deliver that one thing early and exit before it is spent. Templates are diagnostic checklists to run AFTER drafting, never assembly instructions to write BY. An entry that holds without a beat skips the beat. This is the difference between a script that knows what it is doing and a script that sounds generated: the generated one fills every slot; the professional one spends words only where the grip is.

### 6. Human texture (anti-AI voice)
The measurable tells of generated writing are rhythm-uniformity and slot-filling, not word choice. Rules: sentence lengths must vary hard within every paragraph (a four-word sentence after two long ones is worth more than any vocabulary choice); at most one symmetrical construction per script beyond the licensed negate-contrast; kickers land on roughly two-thirds of entries, not all — some entries end on a plain fact, a date, or a quote, and one entry per script just stops; one planted callback per script; micro-judgments are allowed and encouraged ("the man had no reason to flatter the weapon that was trying to kill him") because opinion is the thing templates cannot fake; never explain a joke, never announce a section's purpose, never summarize what was just said.

### 7. Measured VO pace governs all runtime math
The channel's VO reads at **~185 WPM measured** (2,291 words → 12:21), not the 165–170 planning figure. All word budgets, entry-second estimates, and the kill-line cap use 185 WPM (≈ 3.1 words/second). Practical: **78 words ≈ 25 seconds**, 120 words ≈ 39 seconds, 2,300 words ≈ 12:25.

### 8. Post-mortem discipline
Every published video gets its curve mapped to its transcript at timecode level before the next script is written — drops are attributed to specific sentences, not to vibes or priors. Rules in this doctrine may only be added or amended with a timecoded attribution behind them. **[v6.4] And every post-mortem must now record the video's SUBJECT CLASS and its view count alongside its curve. The v6.2 benchmark's blind spot was that it recorded neither.**

### 9. Survivor mechanics are a separate job from the hook
The first minute and the remaining eleven fail for different reasons and are fixed by different rules. The first minute is won by **speed to payoff** (Fix 1). Everything after 1:30 is won by **payoff frequency** (Fix 4) and by **seams that don't announce themselves** (Fix 2). A script can ace one and fail the other — Weirdest Weapons did exactly that. Diagnose them separately: if 1:00 retention is below 55%, the opener is the problem; if survivors-kept is below 40%, the body is the problem. Both can be true at once.

### 10. WRITE MODE — ask before drafting
After the entry list is locked and before any script text is written, ask one question: **section-by-section or full draft?**

**Section-by-section (default for: new formats, experiments, any script over ~1,800 words, or any script where a prior video in the same format underperformed):** write one era block or one entry at a time, deliver it with its own mini-audit (word count, seconds at 185 WPM, visual-event check), and wait for approval before the next. Each approved section becomes fixed context that the next section must flow from — this is what prevents drift. Cheaper to correct too: a rejected section costs one section, not a rewrite pass through a finished script.

**Full draft (fine for: proven formats on proven subjects where the entry list, tiers, and running order were confirmed in detail):** write the whole script, then run the full battery audit.

Either way, the choice belongs to the channel owner per script — never assume. If section-by-section is chosen, the full battery audit still runs once on the assembled script at the end.

**Every era block and every listicle entry is a section for this purpose.** The From Every Era format defaults to section-by-section until an era-block script clears 36% AVD.

**The per-section mini-audit leads with the Fix checks:** for the opening section, the kill-line timecode; for every section, seconds since the last payoff (Fix 4) and whether the seam is spoken or silent (Fix 2).

**[v6.5] Ask the VOICE STATE in the same turn** — base, dry wit, or dramatic. See OVERLAY RECONCILIATION. Like WRITE MODE, it belongs to the channel owner per script and is never assumed.

---

## THE FIVE MANDATORY RULES

Ordered by measured AVD value. Rules 1, 4 and 5 apply to every script; rules 2 and 3 apply to any script with era blocks or low-recognition rosters.

### Fix 1 — The 25-second kill-line rule (worth ~5–7 AVD points)

**Write the opener's payoff line first, then write backwards from it.** The kill-line is the sentence that makes the viewer glad they clicked. It must be spoken **within the first 25 seconds**, which at measured VO pace means **everything before it fits in 78 words**.

Evidence: Military Units reaches its kill-line at ~0:22 and loses 5.8 points in the 36–52 second window. Weirdest Weapons does not reach its kill-line until **0:52** and loses **17.0 points in the single bucket from 0:37 to 0:44**. The drop is not at the payoff. It is in the fifteen seconds before a payoff the viewer has given up on.

**[v6.4] Live confirmation.** The 2026-08-05 analytics pull on the published Weirdest Weapons shows a **15-point cliff between 0:45 and 0:52 (66% → 51%)** at the hook-to-intro handoff, and `relativeRetentionPerformance` below the 0.50 peer median at *every* data point across the whole runtime. Fix 1 is the highest-value single edit available on this channel.

**If the payoff cannot be reached in 25 seconds, the subject is wrong for position one — not the writing.**

**Cut list, in this order, until the opener fits:**
1. Historian attributions ("Polybius wrote that…") — move the source inside the action as a character, or cut
2. Date tangents and duration framing ("the siege lasted two years")
3. Mechanism explanations — how it worked belongs after the viewer knows why they care
4. Inventor and origin biography

**Applies to entry openers too, at reduced strength:** no entry anywhere in the script may run more than 40 seconds before its own payoff lands.

### Fix 2 — Silence the era headers (worth ~2–3 AVD points)

The From Every Era variant reads the era name aloud at every seam — seven times a video, at predictable intervals. That tells the viewer a unit of content just ended, on a schedule they can learn. That is an exit ramp with a bell on it, and the stair-steps in the Weirdest curve sit on the headers.

- **At most TWO era names are read aloud per video.** Spend them where a deliberate reset is wanted — typically the opening block and the modern-threshold meta pivot.
- **Every other era header stays an on-screen card only.**
- **Every silent seam gets an implicit open loop instead.** End the block on a short line containing a contradiction or a missing piece; open the next block by naming its weapon.
- **Where a spoken header is kept, J-cut it.**

❌ **What aired:** "[block ends on era thesis]" → "World War One." → "[new block begins]"

✅ **The fix:** "Standing still worked right up until the factories learned to make more men than the line could hold. The Tsar Tank was designed by a man who had never built a vehicle."

**Why the listicles get away without this:** recognition carries the gap. Weapons-per-era have no such pull. The era format removed the open loop *and* removed the recognition that was covering for its absence. Only one of those can be given back cheaply, and it is the open loop.

### Fix 3 — The recognition floor (worth ~2 AVD points)

**Every block, era, or section opens on its most recognisable subject. Obscure entries ride second or third inside the block.**

Weirdest Weapons opened its WWI block on the **Tsar Tank**, the least recognisable object in the video, and that block is the worst relative-retention stretch of the entire runtime (0.36 → 0.25).

Operationalize at the outline stage: rank each block's subjects by how likely a general viewer is to have heard of them, and put the top-ranked one first. If no subject in a block is recognisable at all, the block is too weak to open a section.

### Fix 4 — A mini-payoff every 75 seconds in the survivor zone (worth ~1–2 AVD points)

From 1:30 onward the Weirdest curve is a clean **slow bleed** — no mechanics, not bad content. There is simply too much distance between rewards.

**Map every payoff on a timeline before recording.** Mark the second at which each reveal, hard number, reversal, or punchline lands. **Any gap longer than 90 seconds gets a payoff inserted, or the block gets shortened.** Target spacing is 75 seconds.

A payoff is: a reveal, a hard number that reframes something, a reversal, or a landed dry observation. It is not: a transition, a date, a spec delivered without consequence, or a thesis line.

Evidence: the Tsar Tank block at 6:54–7:49 ran **55 seconds of setup with no interior beat**.

### Fix 5 — Kill the post-reveal logistics beat (worth ~1 AVD point)

The sharpest mid-video drop in the Weirdest video is **8:24–8:31**, immediately after "attack Japan with bats" lands. What follows is the **$2 million budget and the Project X-Ray paperwork**.

Funding figures, programme names, committee decisions, and procurement chronology are what a script reaches for when the reveal is spent. They are the single most reliable exit point in the body of a script.

**After a reveal, the next sentence either escalates the same image or opens the next loop. Nothing else.** If a funding fact is genuinely good, move it *before* the reveal where it functions as setup ("the war department gave a dentist two million dollars"). Otherwise cut it.

---

## TWO FORMATS

### Format 1: LISTICLE (DEFAULT — proven)
The channel's bread-and-butter format and its **only demonstrated 39–42% AVD structure**. Use by default unless specified otherwise.

**Use when:** Topic is a set of distinct items, examples, tactics, or instances within a category.

**Example titles [v6.4 — all revised to OBJECT/SYSTEM class]:**
- The Deadliest Warships From Every Era Explained
- Every Genius Napoleon Battle Tactic Explained
- Every Failed Weapon in History Explained
- Every Siege Engine Explained
- Every Piece of Kit a Medieval Soldier Carried Explained
- The Weirdest Warships Ever Built Explained

*(Removed at v6.4: "The Worst Military Defeats Ever" — EVENT class. "Every Major Tank in Military History" retained as OBJECT but subject to the modern-only red line.)*

### Format 2: ENTIRE History (adapted from outliers)
Adapted from viral outlier videos. Use when the topic has a clear chronological evolution with cause-and-effect across centuries.

**Use when:** Topic has 500+ years of evolution, multiple distinct phases, and an ironic throughline (rise → unintended consequence → fall).

**[v6.4] CAUTION — class check required.** "The ENTIRE History of the AK-47" and "…of Nuclear Weapons" are OBJECT class and clean. "The ENTIRE History of the Roman Military" and "…of the Mongol Empire" are institution/civilization arcs, which sit close to PEOPLE/EVENT. Run §0.2 before commissioning one, and prefer the object-spine version.

---

## TOPIC SELECTION RULES (Both formats)

Before writing a script, the topic must pass these filters:

0. **[v6.4] SUBJECT CLASS — §0.2. OBJECT or SYSTEM, or a written override. This runs first and it is the cheapest rejection available.**
1. **Within niche** — weapons, military tech, military forces, military tactics, or military history
2. **Search demand exists** — verify via YouTube autocomplete or search volume
3. **Short-form competition is sparse** — no existing 15–25 minute version with high views
4. **Format fit** — does the topic naturally form a list of items (Listicle) or a chronological arc (ENTIRE History)?
5. **Recognition load** — at least half the planned subjects must be things a general viewer has heard of. A roster where the viewer recognises nothing has no free retention anywhere in it, and no rewrite fixes that.
6. **[v6.4] Roster collision check** — does the entry list overlap a currently-surging video on this channel? Weirdest Weapons is live at 111K and its roster owns Panjandrum, bat bombs and the Tsar Tank. A "failed weapons" script must be scoped to *adopted and mass-produced* failures instead, or it cannibalises its own sibling.

If a topic could go either way, **default to Listicle**.

### Commit to the proven skeleton

Novelty should come from the **topic**, not from reinventing the structure. Uncivil Engineer's channel did 350–2,600 views per video until it locked onto one title-and-format skeleton, after which every upload cleared 100K. Once a skeleton is proven, run it across topics rather than experimenting.

### Sequel proven winners

When a format or title skeleton performs, the **Pt 2 is the next obvious upload**. At the candidate-pool stage of any hit-eligible video, deliberately **hold back 4–6 strong entries** to seed a Pt 2.

### Research before writing (Both formats)

Do a research pass BEFORE drafting, not while drafting.

- Use research/search tools up front. Pull the dates, names, and numbers for each planned section before writing a word.
- Reach past the first page of results.
- Keep a quick fact list per section.
- Soften or flag anything you cannot verify.
- **Identify the kill-line during research, not during drafting.** If research produced no such sentence for a subject, that subject cannot open the video.

### Fact staging: one scene per entry

**Every entry is built around ONE scene, and every remaining fact either is the scene or points at it.**

- **One scene per entry.** A scene is something happening to someone at a moment. Exhibits are not scenes.
- **4–6 fact units per entry, not 8–13.**
- **Two dating anchors per entry, maximum.**
- **One measurement cluster, one unit system.**
- **At most one attribution verb per entry.** Prefer witness-framing over citation-framing. **In the opener, the cap is zero until after the kill-line.**
- **Provenance only when the provenance IS the story.**
- **Density varies by entry function.** A myth-bust or contrarian entry keeps its full evidence stack.

**The read-aloud test:** if the entry sounds like exhibits being toured, restage it around the scene.

---

## LISTICLE FORMAT (Default)

### Structure overview
- **8–12 entries** standard
- **No extracted hook section** — Entry #1's opening line carries the curiosity load directly
- **No outro**
- **Target runtime:** ~9.5–12 minutes (1,600–2,000 words; 2,000 ≈ 10:50 at 185 WPM)
- **Words per entry:** VARIABLE by explanatory load — never uniform

### Title formula patterns

**Pattern A: "Every [X]" — chronological.** Used when entries have a timeline.

**Pattern B: "The Most / Worst / Craziest / Deadliest [X]" — superlative, NOT ranked.**

**Pattern C: "Things That [X]" — thematic grouping.**

**Pattern D (HYBRID): "The [Superlative] [X] From Every Era" — chronological.** The channel's proven packaging format — and its weakest retention structure. Use it for the title; do not let it dictate the script's seams. **[v6.4] Note the exact stem "The Deadliest [X] From Every Era" is BURNED per the Title Scan SOP — clone swarm plus our own two corpses. The era-block *structure* is fine; that specific wrapper is not.**

**[v6.4] Pattern E: "Every Failed [X] Explained" — the negative-set list.** Proven across 15+ independent channels and 10+ niches, including a Paint-style history channel at 342K. Failure outperforms success by 3–6× on the same channels. OBJECT class when the [X] is a thing.

When a title contains BOTH a superlative AND a chronological signal, the chronological signal wins for ordering.

### FROM EVERY ERA structural variant: era blocks

1. **Era names are on-screen cards, not narration — with at most two exceptions per video.** See Fix 2.
2. **The unit of structure is the era block, not the weapon entry.** One era holds 1–5 weapons chained with quick in-prose pivots.
3. **Blocks open on their most recognisable weapon.** See Fix 3.
4. **Era-closing thesis lines.** At most two per script, and never on a block whose seam is silent.
5. **Mid-video meta pivot as the rehook.** The natural home for one of the two spoken era headers.
6. **The opening block is governed by payoff proximity.** Kill-line within **25 seconds (~78 words)**.
7. **Era bridges are visual beats, not narration beats.** Every bridge sentence must name a drawable object or scene.
8. **The payoff map applies per block.** No block runs more than 90 seconds without a reveal, number, or reversal.

### ORDERING RULES (5-position structure)

**Position 1 — STRONGEST OPENER.** The entry with the most dramatic, immediate, or counterintuitive hook. **NOT the most famous.** Its kill-line must land by 0:25.

**Positions 2–4 — BUILD.** Entries escalate using ONE of three patterns: severity escalation, scale escalation, or recognition descent.

**Position 5 (≈50–60% mark) — MID-VIDEO REHOOK.** Must contain at least ONE of: an explicit open loop, the most famous entry, the most ironic story, or a counterintuitive choice that makes the viewer re-evaluate earlier entries.

**Positions 6–7 — TRANSITION TO CLOSER.** Stronger than 2–4 but not the peak.

**Final Position — MOST DEVASTATING CLOSER.** The entry with the biggest final impact. **NOT necessarily the most famous — the most resonant.**

**Key principle:** When chronological order conflicts with impact structure, **impact wins**. And when either conflicts with the recognition floor for a block opener, **recognition wins**.

### Avoiding redundancy across entries

Run both checks at the OUTLINE stage.

**1. No repeat lead example.** A single battle or event can be the *primary* example for only ONE entry. Callbacks are the exception, and a good one.

**2. No entry that is just another entry's mechanic.** If entry A is really an *instance* of entry B, merge them or cut one.

### Listicle script structure

| Element | Function | Default tier (words) |
|---|---|---|
| Position 1 — OPENER | Strongest, most counterintuitive entry. Kill-line by 0:25. | HEAVY (250–320) |
| Positions 2–4 — BUILD | Escalating entries | MEDIUM default |
| Position 5 — REHOOK | Mid-video rehook at ~50–60% | HEAVY (250–320) |
| Positions 6–7 — SUSTAIN | Sustained intensity | MEDIUM/LIGHT; at least one deliberate LIGHT trough |
| Final position — CLOSER | Most resonant final impact | HEAVY (280–320) |

**Total target:** 1,600–2,000 words = **8:40–10:50** at 185 WPM. Distribute the budget UNEVENLY.

### Variable entry length

**Do not write uniform entries.**

- **HEAVY — ~250–320 words.** Retention-critical or explanation-heavy.
- **MEDIUM — ~170–220 words.** The workhorse.
- **LIGHT — ~110–160 words.** **Light means fewer words, not fewer facts.**

**Which entries get HEAVY:** the opener; the rehook; the closer; mechanically complex subjects; obscure subjects; the recontextualization entry.

**Which entries get LIGHT:** famous self-explanatory subjects; one-beat weirdness; deliberate pace-troughs.

**Budget logic (≈9-entry script, ~1,800 words):** roughly **3 HEAVY + 3–4 MEDIUM + 2–3 LIGHT**.

**Guardrails:**
- The three structural HEAVIES are fixed. Subject-driven HEAVIES capped at **2 more**.
- If a HEAVY can't fill its band with real substance, demote it rather than pad.
- Alternate weights; avoid two HEAVIES back-to-back.
- **No entry, at any tier, may exceed 90 seconds (~280 words) without an interior payoff.**

### Entry #1 special treatment (CRITICAL)

1. **Concrete sensory or specific detail in sentence 1**
2. **Counter-intuitive claim by sentence 2**
3. **Specific number by sentence 4**
4. **No abstract framing** — never start with "Throughout history..."
5. **Kill-line by 0:25** — write it first; write backwards to it.
6. **The post-payoff rule** — once the opener's peak scene has played, the entry has ~15 seconds of credit left. Spend it on ONE beat, then move.

**Reference opening (Military Units — 75.5% at 0:30, kill-line at 0:22):**
> "Sparta did not believe in a gentle childhood. Spartiate boys were taken from their mothers at age seven, underfed on purpose, and expected to steal food to survive. If they were caught, the punishment was not for stealing. It was for being bad at stealing."

44 words to the kill-line. **[v6.4] This remains the best opener the channel has ever written, and it sits on a 2.8K-view video. It is a craft model, not a subject model.**

**Note on output formatting:** script output uses NO em dashes at all.

### Two opener shapes

**Shape A — Straight reveal.** Name the subject accurately in sentence one and land the counterintuitive claim immediately.

**Shape B — Misdirect-then-deflate.** Lead with what the subject *looks like*, hold the real identity for one beat, then name it as the correction.
> "The meat grinder. A giant spinning wheel the size of a room, racing toward you on the rails, built like something out of a nightmare. It is a snowplow."

**Critical limit on Shape B:** the misdirect only works when the deflation is *surprising*, and it must stay under 15 words.

### Every entry opens on its own subject (CRITICAL)

1. **Lead with the subject** — named in sentence one or two
2. **Surprising or counter-intuitive claim about that subject**
3. **Concrete or specific detail**
4. **No backward-leaning opener**

✅ Prior entry ends: "...the men he had spent the entire battle refusing to use." → Next opens: "The Imperial Guard were the best soldiers in Europe, and Napoleon's favorite thing to do with them was nothing."

❌ "Those men were the Imperial Guard, and at the heart of the Guard stood the Old Guard..."

This applies to era blocks too. It remains inapplicable to ENTIRE History.

### Subject-type calibration: what the opening claim should be ABOUT

**[v6.4] Read §0 first. The UNITS/FORCES/WARRIORS branch below applies ONLY under a Subject-Type Law override — it is craft guidance for a class we do not normally commission, retained because the override case still needs it.**

**For TECH / SHIPS / WEAPONS (a thing): lead with the counterintuitive spec or capability.** The surprise is mechanical.
> "The trireme's weapon was not armour or artillery. It was speed."

**For UNITS / FORCES / WARRIORS (a group of people): lead with the dark or strange ORIGIN, not the kill-stats.** The surprise is human.
> (Mamluks) enslaved steppe boys who assassinated their own sultan and took Egypt on horseback.

**Quick test:** if the entry is a *who*, open on origin or cost. If it's a *what*, open on capability.

### Entry structure template (Setup-Tension-Resolution loop)

1. **Setup** — lead with the named subject AND a surprising claim
2. **Tension** — what's surprising about the obvious assumption
3. **Resolution** — the specific facts, mechanism, or proof
4. **Implicit open-loop transition** — short observation containing a contradiction

### Listicle transitions (CRITICAL for retention)

❌ **Summary kicker:** "The deadliest knife in the water got replaced by a floating fortress — because it is a lot easier to build a bigger ship than a better crew."

❌ **Announcement-style:** "The next era of warships would learn that fire travels faster than oars."

Never use "the next [entry/era/ship/tactic]" or "what came next". A bare spoken era name is an announcement transition too, capped at two per video.

✅ **Implicit open loop:** "Speed had won every battle that mattered. Until it didn't." · "But oars couldn't outrun fire."

### Templates that work
- "Speed had won every battle that mattered. Until it didn't."
- "Wood. The whole thing was made of wood."
- "But oars couldn't outrun fire."
- "Stone fell. Water didn't."
- "[Subject] had solved every problem except one — being seen."
- "It worked. For exactly as long as no one figured out the counter."

### When recognition replaces the open loop

**[v6.4] RARELY APPLICABLE — retained for the override case only.** The exception below fires on named elite units, named battles and named people, which are PEOPLE and EVENT class per §0. **Default to implicit open loops in essentially every script this channel now commissions.**

**The open-loop transition rule is load-bearing when entries are abstract or similar to each other.** Triremes, galleys, and dreadnoughts blur together.

**When every entry is a famous, visually distinct subject with its own built-in arc, the FORMAT is the open loop.**

**Decision rule:**
- Entries abstract / similar (tech, tactics, ship classes, weapons-per-era) → implicit open-loop transitions are MANDATORY. **This is now essentially every ExplainTory topic.**
- Entries famous / distinct / each with their own rise-and-fall (named elite units, named battles, named people) → a resonant summary-kicker close is acceptable. **Override case only.**

**The measured cost of getting this wrong is known.** Weapons-per-era is an abstract/similar roster wearing a chronological costume, and the era format gave it summary-style seams anyway. That is the single largest structural difference between the 41.9% videos and the 30.4% one. When in doubt, default to open loops.

### Listicle throughline thesis patterns

Listicle scripts work better with a unifying thesis observable across entries. **Don't state it.**

- "Each generation thought it had built the unbeatable version"
- "The deadliest weapon in each era was always the one nobody saw coming"
- "Every clever move was someone else's blueprint for the counter"
- "What looked like an upgrade was actually the seed of obsolescence"

### Vary outcome TYPE, not just content

Map each entry's outcome type at the outline stage (fell / endured / surprise success / almost / countered / never-fixed) and force at least **1–2 entries that break the expected arc**.

---

## ENTIRE History FORMAT

### Structure overview
- **7 eras** (Origin → First Evolution → The Twist → Peak → Crisis → Late Stage → The End)
- **No hook, no overview** — drop straight into Era 1
- **No outro**
- **Mandatory mid-video twist** around 40–55%
- **Target runtime:** 18–22 minutes (~3,300–4,000 words at 185 WPM)
- The 25-second kill-line, the 75-second payoff map, and the post-reveal logistics ban all apply.
- **[v6.4] Class check per §0.2 before commissioning.** Prefer object-spine subjects (a weapon, a ship class, a fortification system) over institution or civilization arcs.

| Section | Function | Target share |
|---|---|---|
| Era 1 / Origin | Set up the original system | ~10% |
| Era 2 / First evolution | The first major upgrade | ~13% |
| Era 3 / The Twist | The reform that creates the next problem | ~14% |
| Era 4 / Peak | The system at maximum power | ~13% |
| Era 5 / Crisis | The cracks begin | ~9% |
| Era 6 / Late stage | Adaptation and decline | ~11% |
| Era 7 / The End | Resolution | ~7% |

Each era break uses an **open-loop transition** (irony + question that the next era's first line answers).

---

## VOICE CALIBRATION (Both formats)

The voice is **casual but restrained dry-wit** — NOT full bar-friend casual.

### Reference voice
Someone genuinely interested in the topic, who has spent real time learning it, explaining it to a friend who's smart but doesn't know the subject. Not performing humor — but they have observations, and occasionally one is dry or ironic.

### Humor density
- Aim for 1 dry observation per 250–300 words
- Cluster strongest punchlines around entry/era transitions
- Never two casual lines back-to-back
- The humor should *land harder because it's rare*

**This is the BASE density.** See OVERLAY RECONCILIATION below.

### OVERLAY RECONCILIATION [REWRITTEN v6.5] — the three voice states

**[v6.5] The overlay now runs in two modes, so there are three voice states, not two.** v6.3 described only base and overlay-active, which is why drafting sessions offer "base or dry wit" and never surface the dramatic option.

**Ask the channel owner which state, in the same turn as the WRITE MODE question:**

> Voice state — base, dry wit, or dramatic?

| State | What it is | When |
|---|---|---|
| **BASE** | No overlay. The Humor density block above governs: ~1 dry observation per 250–300 words. | Default for straight explainers where the subject carries itself. |
| **DRY WIT** | Overlay loaded, **Mode 1**. Entries are fact clusters with faster rhythm and restrained dark humor. This was the only overlay state before v1.1. | Punchier narration without changing entry architecture. |
| **DRAMATIC** | Overlay loaded, **Mode 2**. Each entry is built as a small tragedy — a want stated first, a named responsible party, a sincere-belief beat, the governing assumption named and broken at the reversal, then a cold exit. | Mixed in by position, not run script-wide. |

**Mixed is a legitimate answer and usually the right one.** DRAMATIC entries run heavier than the same facts as a fact cluster and don't stack — a few per script, never adjacent. Default placement is **Position 1, the Position 5 rehook, and the closer**, which are already the three structural HEAVIES. Everything else runs DRY WIT or BASE. That placement is a starting assumption, not a measured result.

**Load the right file: `claude/explaintory-punchy-dark-wit-overlay-skill-v1_1.md`.** Not `...-v1.md`, which predates both modes, the fact guard, and the narrator section.

**Conflict 1 — humor density. The overlay wins, explicitly.** When the overlay is active in either mode, its density guidance supersedes the Humor density block above, **and nothing else**. Everything else in this file still outranks the overlay, including every retention rule, the tonal restraint test, the punchline patterns to AVOID, the pattern repetition thresholds, and the fact-density floor. **[v6.4] And §0, which outranks both files.**

**Conflict 2 — spoken era headers. This file wins.** Fix 2 caps spoken era headers at two per video and the cap holds. Read the overlay's transition rule as: *payoff → hard cut → on-screen era card → new subject acts immediately*, with the spoken header appearing only at the two seams Fix 2 licenses.

**[v6.5] Conflict 3 — the scale of the fact floor. The overlay wins on scale, not on amount.** The Authenticity section below requires a checkable fact roughly every 2–3 sentences. When the overlay is loaded, that density is held **across the entry** rather than sentence by sentence, and three positions may carry no new fact at all: the sincere-belief beat, the payoff breath, and the entry exit. **The per-section minimums do not move** — every section still carries ≥1 date, ≥1 named individual and ≥1 hard number.

Rationale: read at sentence scale the floor doesn't forbid the strongest lines, it makes them feel like violations while drafting, and it collides directly with letting a payoff breathe. The amount of research a script carries is unchanged; only where it's allowed to sit changes.

**Where they already agree:** "exit after the real payoff" IS Fix 5; "open on the object, action, or consequence" IS doctrine #3; "name the grip early" IS doctrine #5; the no-em-dash rule, the tonal restraint test, and the 185 WPM audit figure are the same rules stated twice.

**One gap the overlay does not cover:** it has no opener deadline. Its note that "the first minute may carry slightly more personality" is the one line in it that can actively cost AVD. **Fix 1 outranks it.** In the first 78 words, personality is permitted only in the kill-line itself. **[v6.5] This applies to DRAMATIC too — a want-first opening still has to reach its kill-line inside 78 words, and if it can't, that entry is wrong for Position 1.**

### Sentence rhythm (Gary Provost principle)
Vary sentence length deliberately. After 2–3 long explanatory sentences, drop a punchy short one.

### Punchline patterns that work

| Pattern | Example |
|---|---|
| Understatement | "Strong motivation." |
| Dry observation | "He had a point." |
| Modern analogy | "Like when a company gets acquired and they keep all the staff." |
| Ironic factual sting | "Nineteenth century medicine couldn't beat first century Rome." |
| Compressed truth | "Rome didn't just conquer territory. They paved it." |
| Deadpan absurdity | "Being emperor of Rome during this period had a worse life expectancy than working in a coal mine." |

### The comprehension analogy

A second, separate use of analogy whose job is **clarity, not a laugh**. Anchor an unfamiliar subject to one concrete familiar image: "giant metal giraffe," "flying donut," "a giant pizza cutter rolling through the earth."

- One per unfamiliar or abstract entry, placed right as the subject is introduced
- Restrained and on-register
- Does not count against humor density
- **In a low-recognition block, mandatory on the first subject**

### Real quotes and exchanges as beats
> (Austerlitz) Napoleon asks Soult how long his men need to take the Pratzen Heights. "Less than twenty minutes." It was enough.

Use sparingly (one or two per script), keep them short, and only use quotes you can actually source.

### Punchline patterns to AVOID
- "Welcome to the army, kid." (too sitcom)
- "Capitalism, baby. Ancient edition." (too meme)
- "Classic Rome." (filler)
- "Yeah, no" (too casual)
- "Honestly, it's kind of metal." (too casual)

### Tonal restraint test
*Would this line work if read by a serious documentary narrator with a slightly raised eyebrow?* If yes, keep it. If it requires a comedian's delivery, cut it.

---

## PATTERN REPETITION THRESHOLDS

| Word/Pattern | Max uses | Notes |
|---|---|---|
| "basically" | 3 | Cuts to 2 are better |
| "genuinely" | 2 | Often unnecessary qualifier |
| "actually" | 4 | Watch for sentence-starting use |
| "literally" | 2 | Only when it adds force |
| "honestly" | 1 | Almost always cuttable |
| "Here's [reveal]" pattern | 3 | Cumulative |
| "Which is/was" aside-opener | 2 | Vary structure instead |
| Single punchline word | 1 | Loses impact when reused |
| "And then" as transition | 0 | Always replace with But/Therefore |
| **Spoken era-name header** | **2** | Per video, across the whole script |
| **Era-closing thesis line** | **2** | Never on a block with a silent seam |

### Verification commands (run after writing)

```bash
# Run from script's directory. Replace script.md with actual filename.
echo "basically:" && grep -o -i "\bbasically\b" script.md | wc -l
echo "genuinely:" && grep -o -i "\bgenuinely\b" script.md | wc -l
echo "actually:" && grep -o -i "\bactually\b" script.md | wc -l
echo "literally:" && grep -o -i "\bliterally\b" script.md | wc -l
echo "honestly:" && grep -o -i "\bhonestly\b" script.md | wc -l
echo "Here's pattern:" && grep -c -i "here's" script.md
echo "Which is/was:" && grep -o -i "which is\|which was" script.md | wc -l
echo "And then:" && grep -o -i "and then" script.md | wc -l
echo "Announcement transitions:" && grep -o -i "the next \(era\|weapon\|tactic\|ship\|entry\)\|what came next" script.md | wc -l
echo "Words before first kill-line marker:" && sed -n '1,/\[KILL-LINE\]/p' script.md | wc -w
echo "Word count:" && wc -w script.md
```

**Mark the opener's kill-line with a `[KILL-LINE]` tag** so the word count before it can be checked mechanically. It must read **78 or fewer**. Strip the tag before TTS.

### Sentence-starting words (acceptable variation)
- "And ___" — up to 12 uses · "But ___" — up to 8 · "So ___" — up to 6 (each functional, not filler)

---

## RETENTION MECHANICS (Channel-specific)

### Retention targets and checkpoints

| Checkpoint | Target | Ceiling seen | Why it matters |
|---|---|---|---|
| 0:30 | **74%+** | 78.2% | Already solved. Do not spend effort here. |
| 1:00 | **58%+** | 63.7% | **The real diagnostic.** Below 55% means the opener overran — apply Fix 1. |
| 1:30 | **53%+** | 57.9% | Confirms the opener repair held. |
| Survivors kept | **40%+** | 44.9% | Body health. Below 40% means apply Fixes 2, 4, 5. |
| AVD | **36–40%** | 41.9% | The honest planning range. |
| Watch time per viewer | **4:30–5:00** on a 12-minute video | 4:41 | Algorithmic distribution driver. |

**45% is not a target.** It has never been reached on this channel.

**Diagnostic logic:**
- 0:30 strong, 1:00 below 55% → **the opener overran its kill-line.** Fix 1.
- 1:00 healthy, survivors-kept below 40% → **the body has no payoff mechanics.** Fixes 4 and 5.
- Visible stair-steps at regular intervals → **the seams are announcing themselves.** Fix 2.
- One block far below the video's relative-performance average → **that block opened on something nobody recognises.** Fix 3.
- **[v6.4] Retention healthy across the board and views still flat → the problem is not in this section at all. Check §0.**

### The principle that matters most
"NEVER close a loop without immediately opening a new one." For **listicle format** this matters even more than ENTIRE History — because each entry naturally feels self-contained.

### The four mid-video lifts
Every script must contain at least 4 distinct "lift" moments at roughly the 25%, 45%, 65%, and 85% marks. **These are the floor, not the plan. The 75-second payoff map (Fix 4) is the plan; on a 12-minute video it produces roughly nine payoffs, not four.**

**The counter-example lift.** One of the strongest lifts available is a deliberate limit or failure case: the one time the pattern broke.

### The mid-video twist
Every script should contain ONE central twist around the **40–55% mark**.

**For ENTIRE History (mandatory):** a reform or innovation that creates the next problem.
**For Listicle (strongly recommended):** a recontextualization — something that makes the viewer reconsider earlier entries.

---

## AUTHENTICITY REQUIREMENTS

### Fact-checking checklist (run before final draft)
- All named individuals are real and correctly identified
- All relationships are accurate
- All numbers are sourced or clearly framed as estimates
- All dates are correct
- Inflated stats are softened
- Unverifiable claims are removed or qualified
- Each entry uses the canonical or strongest illustration of its specific mechanic

### Required uniqueness signals (all 7)
1. **Original research** — specific stats not in the top Google/Wikipedia results
2. **Unique angle** — a cause-and-effect framing other videos don't use
3. **Editorial voice** — dry observation and personality throughout
4. **Specific sourcing** — named individuals, exact dates, technical specs per major section
5. **Non-obvious connections** — at least one "I never thought of that" link per entry/era
6. **Original structure** — section order or framing that isn't the default
7. **Human review evidence** — conversational asides, voice consistency, hand-written feel

### Fact density (CRITICAL — both formats)

**Minimum load per section:**
- **At least one exact date or year**
- **At least one named individual** — never leave the other side anonymous
- **At least one hard number or technical spec**

**Density target:** a specific, verifiable fact roughly every 2–3 sentences. **[v6.5] When the overlay is loaded, this is held across the entry rather than sentence by sentence — see OVERLAY RECONCILIATION Conflict 3. The minimums above do not move.**

**Rules:**
- **Soften uncertain numbers** with "around," "close to," "roughly."
- **No fake density.** Three sentences restating the same fact is not density.
- **Reach past page one.**
- **Density never buys a payoff.** A dense paragraph with no reveal still counts as a gap under Fix 4. Facts are the armor; payoffs are the pull.

**Staging caveat:** the floor above is a minimum. See "Fact staging: one scene per entry" for the ceiling.

---

## POST-WRITE AUDIT CHECKLIST

### The v6.4 zero (run this FIRST — it is cheaper than everything below)
- [ ] **§0 SUBJECT CLASS** — the topic is OBJECT or SYSTEM, or a written override is on file
- [ ] **Roster collision** — the entry list does not overlap a currently-surging video on this channel

### The v6.2 five (run these next — they carry the most AVD)
- [ ] **Fix 1** — opener's `[KILL-LINE]` tag sits at 78 words or fewer; no historian attribution, date tangent, or mechanism explanation before it
- [ ] **Fix 1b** — no entry anywhere runs more than 40 seconds (~124 words) before its own payoff
- [ ] **Fix 2** — at most TWO spoken era-name headers; every other seam silent with an implicit open loop; kept headers marked for J-cut
- [ ] **Fix 3** — every block/section opens on its most recognisable subject
- [ ] **Fix 4** — payoff map drawn on a timeline; no gap longer than 90 seconds; target spacing 75 seconds
- [ ] **Fix 5** — no funding figure, programme name, or procurement detail immediately after a reveal

### Structure (Listicle)
- [ ] No extracted hook section — drops straight into Position 1
- [ ] Position 1 is the most counterintuitive entry (NOT the most famous)
- [ ] Position 1 hits all 4 beats
- [ ] Opener shape chosen deliberately; if Shape B, misdirect under 15 words and the deflation genuinely surprising
- [ ] EVERY entry opens on its own subject, named by line 1–2, NO backward-reference opener
- [ ] Subject-type opener correct: TECH/SHIPS/WEAPONS open on counterintuitive spec
- [ ] Positions 2–4 use ONE consistent escalation pattern
- [ ] Position 5 (REHOOK) at ~50–60% contains explicit open loop OR most famous entry OR most ironic story
- [ ] Final position is the most devastating, not necessarily the most famous
- [ ] 8–12 entries total
- [ ] No repeat lead example; no entry is merely a re-description of another's mechanic
- [ ] Outcome TYPE mapped per entry; at least 1–2 break the expected arc
- [ ] Word count 1,600–2,000; entry lengths VARIED by tier
- [ ] Every entry built around ONE scene; 4–6 fact units, ≤2 date anchors, one measurement cluster, ≤1 attribution verb
- [ ] No outro

### Structure (From Every Era variant)
- [ ] Era blocks, not one-weapon entries
- [ ] ≤2 spoken era headers; the rest on-screen cards only
- [ ] Each block opens on its most recognisable weapon
- [ ] ≤2 era-closing thesis lines, none on a silent seam
- [ ] Opening block reaches its kill-line by 0:25
- [ ] Every bridge sentence names a drawable object or scene
- [ ] No block runs 90 seconds without an interior payoff

### Structure (ENTIRE History)
- [ ] No hook, no overview — drops straight into Era 1
- [ ] 7 eras · 3,300–4,000 words · mandatory mid-video twist at 40–55% · no outro

### Transitions (Both)
- [ ] Every inter-section transition is an open loop
- [ ] No announcement-style transitions, no bare spoken era name beyond the two-per-video cap
- [ ] Each section's first line resolves the previous section's open loop by leading with its own subject
- [ ] No "and then" transitions

### Voice (Both)
- [ ] **[v6.5] Voice state was ASKED, not assumed** — base, dry wit, or dramatic, and per-position if mixed
- [ ] Humor density ~1 dry observation per 250–300 words, **or overlay density if the overlay is loaded**
- [ ] **[v6.5] DRAMATIC entries: a want stated first, a named party, a sincere-belief beat, the assumption broken at the reversal, a cold exit — and never two adjacent**
- [ ] Each unfamiliar/abstract entry has one restrained comprehension analogy
- [ ] No back-to-back casual lines · No sitcom-voice punchlines · Sentence rhythm varied

### Pattern repetition
- [ ] All thresholds respected (run the grep commands)

### Retention
- [ ] 0:30 mechanics confirmed (4-beat check)
- [ ] Payoff map drawn; at least 4 lifts at ~25/45/65/85%, 75-second spacing as the plan
- [ ] No exit points — viewer always has an unanswered question
- [ ] Mid-video twist lands at 40–55%

### Authenticity & density
- [ ] All 7 uniqueness signals present
- [ ] All facts verified · every section has ≥1 date, ≥1 named individual, ≥1 hard number
- [ ] A checkable fact every 2–3 sentences (**held across the entry when the overlay is loaded**) · uncertain numbers softened · no fake density

---

## DEFAULT PROMPT TEMPLATES

### Listicle prompt (default)
```
Write a script for ExplainTory.

Topic: [user provides]
Subject class: [OBJECT / SYSTEM — or state the override]
Voice state: [BASE / DRY WIT / DRAMATIC — or mixed, by position]
Entries (optional): [if user lists them]
```

### ENTIRE History prompt
```
Write a script for ExplainTory.

Topic: The ENTIRE History of [X]
Subject class: [OBJECT / SYSTEM — or state the override]
Voice state: [BASE / DRY WIT / DRAMATIC — or mixed, by position]
```

---

## QUICK REFERENCE

### The 6 rules that matter most [v6.4]
0. **Subject class first.** OBJECT or SYSTEM. The channel is 5-for-5 on things and systems, 0-for-3 on people and events. High AVD is not a green light.
1. **Kill-line by 0:25.** Write the payoff first, write backwards to it, 78 words maximum in front of it.
2. **No extracted hook. No outro.**
3. **Open loops at every seam** — never summary kickers, never announcement transitions, never more than two spoken era names.
4. **A payoff every 75 seconds.** Map them before recording.
5. **Listicle is default.** It is the only structure that has ever produced 40%-class AVD on this channel.

### The two questions to ask before drafting
- **WRITE MODE** — section-by-section or full draft? (doctrine #10)
- **[v6.5] VOICE STATE** — base, dry wit, or dramatic? Mixed by position is a legitimate answer and usually the right one.

### The 4 things that kill retention
1. **An opener that runs past 25 seconds without a payoff** — 17 points in one 7-second bucket
2. Summary kickers, announcement-style transitions, or spoken era headers at every seam
3. **Payoff gaps longer than 90 seconds in the body** — the slow-bleed signature
4. Hooky openings ("Today we're explaining...") and pattern repetition

### The 1 thing that kills views [v6.4]
**Choosing a PEOPLE or EVENT subject.** Nothing in the retention section can rescue it. Military Units holds the channel's best AVD and did 2,800 views.

### Format selection
- Topic is a list of items? → **Listicle**
- Topic is a 500+ year chronological arc? → **ENTIRE History**
- Unclear? → **Default to Listicle**

### Retention checkpoints
- 0:30 → 74%+ (already solved) · 1:00 → 58%+ (the real diagnostic) · 1:30 → 53%+
- Survivors kept → 40%+ · AVD → **36–40%**, ceiling 42%. **45% is not a target.**

---

**ExplainTory Channel Skill v6.5** — Rewrites OVERLAY RECONCILIATION for the overlay's three voice states, adds the fact-floor scale carve-out, and adds VOICE STATE to the pre-draft questions and the prompt templates. No doctrine, Fix, format rule or threshold is changed from v6.4. Calibrated from four videos of lifetime retention data (2026-07-27), the full ten-video view catalogue (2026-08-05), the retention-coaching diagnostic framework, FacelessOS principles, and competitor analysis across a 25-channel roster. Supersedes v6.4. Reuse for every script.

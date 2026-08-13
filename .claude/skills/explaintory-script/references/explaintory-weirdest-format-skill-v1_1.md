---
name: explaintory-weirdest-format
description: ExplainTory listicle sub-format for "The Weirdest [X] Ever Made / Ever Used" videos. Reverse-engineered from Uncivil Engineer's top-5 outliers (565K / 361K / 298K / 219K / 199K views), a 7.9K-sub engineering channel whose entire breakout is this one title formula. Use whenever the topic is a collection of strange/bizarre military objects (weapons, armor, war machines, fortifications, vehicles). Inherits the ExplainTory channel skill and the Listicle format; this file overrides them only where the "Weirdest" engine differs. Apply on top of explaintory-channel-skill-v6.3.md, never instead of it.
---

# ExplainTory — "The Weirdest [X] Ever Made" Format

> **v1.1:** repointed to channel skill v6.3 (was v5.7); VO rate corrected to the measured 185 WPM; **NEVER-SAY-WEIRD rule** added below.

## THE NEVER-SAY-WEIRD RULE [v1.1]

The narration must never call the subject weird, strange, bizarre, odd, insane or incredible. The title already made that promise; repeating it in the body spends credibility instead of building it, and hands the viewer a verdict they should be reaching alone.

The per-entry **paradox hook states a CONTRADICTION, never a VERDICT.**

- Right: "Warships do not have roofs. The geobukseon had a roof, and the roof was covered in iron spikes."
- Wrong: "The turtle ship was one of the strangest warships ever built."

The first shows and lets the viewer conclude. The second tells, and reads as a script that does not trust its own subject to land. The strongest possible delivery of "weirdest" is a script that never once says it and leaves no other conclusion available.

Only exceptions: quoting a source, or judging the historical record rather than the subject. Enforced mechanically by `explaintory-lint-v3.py`, which flags every hit for review rather than auto-failing, because the exceptions are real.

A spectacle-listicle sub-format. It is still a Listicle (8–12 distinct entries, no extracted hook, no outro), but the selection logic and per-entry hook are different from the deadliest/rise-and-fall listicle. This file captures what makes the format travel, then bolts ExplainTory's voice, fact-density, and no-outro rules on top.

> **Load order:** `explaintory-channel-skill-v6.3.md` (channel rules) → `faceless-scripts-os-master.md` + `retention-mechanics-skill.md` (core) → this file (format overlay). When this file conflicts with the generic Listicle guidance, this file wins for "Weirdest" topics only. When it conflicts with the v6.3 channel skill's voice/density/authenticity rules, **v6.3 wins** — those are non-negotiable.

---

## WHY THIS FORMAT WAS PROVEN

Source channel: **Uncivil Engineer** (~7.9K subs). Before this format (roads, sewage, "construction myths"): 350–2,600 views per video. After switching to "Weirdest [X] Ever Made Explained," every upload cleared 100K. The title formula is the channel.

| Rank | Video | Views | Length | Entries |
|---|---|---|---|---|
| 1 | Weirdest Trains Ever Made Explained | 565K | 11:13 | 9 |
| 2 | The Weirdest Machines Ever Built Explained | 361K | 7:27 | 8 |
| 3 | Weirdest Airplanes Ever Made Explained | 298K | 8:15 | 9 |
| 4 | Weirdest Buildings Ever Made Explained | 219K | 9:20 | 9 |
| 5 | The Weirdest Machines Ever Built Explained (Pt 2) | 199K | 7:38 | 8 |

It also runs as a **franchise**: Machines Pt 1 & 2, Airplanes Pt 1 & 2. Once an episode hits, the sequel is a near-guaranteed follow-up.

### The engine (do not break this)
The weirdness has to be **visual**. Every specimen is a physical object that thumbnails — something a scrolling viewer sees and thinks "what *is* that." Trains, machines, planes, buildings all share this. So does ancient/military hardware: a urumi, a macuahuitl, a war-wagon, a multi-barrel organ gun. The format collapses the moment the subject is abstract (this is why "Weirdest Tactics" is a weak fit — a tactic has no single arresting image; "Weirdest Weapons/Armor/War Machines" is a strong fit).

**Topic fit test (run before committing a "Weirdest" title):**
1. Can each entry be shown as one bizarre object in a thumbnail? If no → wrong format.
2. Are there 12–16 genuinely strange candidates so the final 9–10 are all strong? If no → wrong topic.
3. Is the strangeness *immediate* (you get it in one glance) rather than requiring explanation? If it needs a paragraph to seem weird, it's a mid entry, not an opener.

---

## THE PER-ENTRY TEMPLATE (5 beats, identical across all 5 outliers)

Every entry, with no exceptions, runs these five beats in order:

1. **NAME** — the specimen's name or nickname, spoken cold. Doubles as the on-screen header. ("Spider excavator." "Coleopter." "The Sphere." "Railplane.")
2. **PARADOX HOOK** — one sentence that states the contradiction. This is the whole entry's curiosity gap and it lands in the first breath:
   - *negation:* "This thing doesn't roll. It doesn't use tracks. It literally walks."
   - *not-what-it-looks-like:* "No, this is not a science-fiction spaceship. It was a real aircraft from the 1950s."
   - *shouldn't-but-did:* "This might be the most useless fast train ever built, but it still broke speed records."
   - *looks-wrong-works-anyway:* "It looks deeply wrong, like an airplane that loaded in incorrectly. But somehow it actually flew extremely well."
3. **VISUAL SIMILE** — anchor the look with a concrete comparison. This is the format's signature move and it's in nearly every entry: "giant metal giraffe," "flying donut," "cruise ship crossed with a bookshelf," "giant pizza cutter rolling through the Earth," "construction robot." For ExplainTory, the simile is also where a dry line can live.
4. **MECHANISM + ONE HARD NUMBER** — how it actually works, plus a spec: tons, mph, gradient, year, cost, range. (Trireme weighs / Beluga carries / Schienenzeppelin hit 230 km/h / Sphere cost $2.3B.)
5. **OUTCOME + KICKER** — what happened to it (failed / almost worked / surprise success / still in use), closed on one dry line. No transition sentence. Hard-cut to the next NAME.

---

## EXPLAINTORY OVERRIDES (where to beat the source channel)

Uncivil Engineer's structure is excellent. His *writing* is beatable. Apply these:

**1. Fact density = use the Airplanes/Trains model, never the Machines model.**
The Machines video (361K) uses zero dates and zero named people — pure spectacle. It works for an engineering-curiosity audience, but ExplainTory's audience comes to *learn*. Use the Airplanes/Trains density instead: every entry carries **at least one date/year, one named individual (inventor, commander, smith, engineer), and one hard number** — exactly the v5 fact-density bar. The Airplanes video proves you can be the funniest *and* the most fact-dense at once.

**2. Voice = ExplainTory dry-wit, not meme voice.**
The source channel reaches for meme similes ("that one SpongeBob episode," "spinning dinner plate"). Keep the *structure* of the simile, drop the meme register. Run every line through the v5 tonal-restraint test: would it work read by a serious narrator with a slightly raised eyebrow? "Parallel parking, except you're falling out of the sky" passes. "SpongeBob episode" fails. Humor density stays at ~1 dry observation per 250–300 words.

**3. No outro. Cut his CTA entirely.**
Every Uncivil Engineer video ends with "become the Uncivil Mastermind, click the video on screen." ExplainTory has **no outro** — the final entry's last sentence is the script's last sentence. Strip the CTA.

**4. Transitions = hard cut or summary kicker, NOT forced open loops.**
This is the one place the generic ExplainTory open-loop rule relaxes, and it's allowed by the v5 "when recognition replaces the open loop" clause. Weird, distinct, visual specimens are self-contained; the format itself is the open loop ("what's the next weird one"). Do not manufacture a dangling thread between a war-scythe and a repeating crossbow. End each entry on a clean dry kicker and hard-cut to the next name. (You may still use a light implicit loop when two entries genuinely connect, but it is optional here, not mandatory.)

**5. Outcome variety is mandatory.**
Do not let all nine entries be "it failed / it was abandoned." The source channel's best episode (Airplanes) deliberately mixes: spectacular failures (Caproni Ca.60 flew for a minute then exploded), things that *almost* worked (BV 141, "almost became standard"), and surprise successes still respected (Beluga, Flying Pancake — "actually flew incredibly well"). Map your outcome type per entry at the outline stage and force at least 2–3 "surprise success" entries among the failures. This is the single biggest anti-monotony lever.

---

## OPENER CALIBRATION (Position 1)

Same rule as v5: the opener is the **most visually shocking** specimen, **not the most famous**. Across all four source videos the opener is the one that hits hardest in a single image:
- Trains → Rotary Snowplow ("a giant spinning wheel the size of a room… built by a super villain"), deflated to "really just a snowplow."
- Machines → Spider Excavator ("it literally walks").
- Airplanes → Coleopter ("not a science-fiction spaceship").
- Buildings → The Sphere ("giant glowing ball… $2.3 billion").

For a weapons build, that means the opener is the weapon that looks most impossible at a glance (a urumi whip-sword, a multi-bladed katar, a scythed chariot), not the most historically important one. The opener still has to satisfy the v5 four-beat 30-second check: concrete detail in sentence 1, counter-intuitive claim by sentence 2, hard number by sentence 4, no abstract framing.

---

## STRUCTURE & ORDERING (maps onto the v5 five-position model)

| Position | Function | "Weirdest" specifics |
|---|---|---|
| 1 — OPENER | Most visually shocking specimen | Carries the 0:30 retention load. The "what is that" image. |
| 2–4 — BUILD | Escalation | Escalate on **strangeness/spectacle**, not severity. Mix outcomes (failure / almost / success). |
| 5 — REHOOK (~50–60%) | Mid-video re-engage | Put the single most jaw-dropping or most counterintuitive specimen here (the surprise success that "shouldn't have worked," or the one with the wildest number). |
| 6–7 — SUSTAIN | Keep intensity | The specimens that need a little setup to land their weirdness. |
| Final — CLOSER | Most resonant, not most famous | Source channel uses its longest, most reflective entry here (Trains → GM Aerotrain gets ~2 min and a built-in "genius or mistake?" debate). Give your closer extra room and a resonant final image. No outro after it. |

**Length for ExplainTory (synced to channel skill v6.3):** total **1,600–2,000 words (~8:40–10:50)** at the measured VO rate of 185 WPM (2,000 words ≈ 10:50). Source entries average ~120–180 words; the source channel's total runtime (8–11 min) is actually close to this target, so don't inflate it. **Do not write uniform entries** — allocate the budget by explanatory load using the v6.3 HEAVY / MEDIUM / LIGHT tiers:
- **HEAVY (~250–320):** opener, rehook, closer, plus any specimen that's mechanically complex (needs a comprehension analogy or a how-it-works beat), obscure (no viewer schema), or carries the mid-video twist.
- **MEDIUM (~170–220):** a recognizable specimen with a clean arc.
- **LIGHT (~110–160):** famous/self-explanatory specimens, one-glance weirdness, and deliberate pace-troughs. Light still clears the fact-density floor (≥1 date, ≥1 named person, ≥1 hard number) — trim explanation, never evidence.

Run **9 entries** (≈3 heavy + 3–4 medium + 2–3 light) or **10** with more lights, summing to the band. Cap subject-driven heavies at ~2 on top of the three structural ones or you blow past 2,000. Don't pad the source's lean entries — a heavy entry earns its length with a real second fact, not filler.

**Mid-video twist (recommended):** the v5 recontextualization beat fits naturally here as a counter-example or category turn around the 45–55% mark — e.g., after several "weird and useless" entries, the one that was weird *and* changed warfare. That flips the viewer's assumption and re-engages.

---

## TITLE FORMULA & FRANCHISE

Base formula: **The Weirdest [X] Ever Made, Explained** (keep "Explained" — it's the channel signature and the source channel's proven suffix).

Strong military fits (each can spawn a Pt 2):
- The Weirdest Ancient Weapons Ever Made, Explained
- The Weirdest Weapons Ever Made, Explained *(broader ceiling, more competition)*
- The Weirdest Armor Ever Made, Explained
- The Weirdest War Machines Ever Built, Explained
- The Weirdest Siege Weapons Ever Built, Explained
- The Weirdest Military Vehicles Ever Made, Explained

Weak fits (abstract — do NOT use this format):
- Weirdest Tactics / Strategies / Battles — no single arresting image. Use the standard deadliest/rise-and-fall listicle instead.

**Franchise rule:** if a "Weirdest" episode performs, the Pt 2 is the next obvious upload. Hold back 4–6 strong candidates from the first build to seed the sequel.

---

## THUMBNAIL (the format lives or dies here)

The whole format is thumbnail-driven. Pick the **single most visually insane specimen** as the bait image — not the most important one. Big, isolated object; high contrast; one or two words of text max. For an ancient-weapons build, the bait is the weapon that makes someone stop scrolling (urumi, macuahuitl, scythed chariot), even if it sits at Position 1 or the rehook rather than being the "best" entry. Match the specimen you thumbnail to an entry strong enough to pay it off early.

---

## WORKED REFERENCE — "Weirdest Trains Ever Made" decoded

Full structure of the #1 outlier, so the template is concrete:

1. **Rotary Snowplow** (OPENER) — "The meat grinder." Hook: looks like a super-villain weapon → reveal it's "just a snowplow." Visual simile = meat grinder. Spec: 100+ years old, can't move on its own. Kicker: the terrifying machine is really just a snowplow.
2. **Railroad Omnibus** — bus/train hybrid. Hook: "looked like a great idea. So why didn't it take over the world?" Germany, 20th c. Outcome: too expensive, faded.
3. **Hamster Wheel Train** (Stoosbahn) — Hook: "the weirdest ideas are actually the best ones." Spec: 110% gradient, steepest funicular on Earth, rotating barrel cabins. Outcome: surprise success, still runs.
4. **Jet Train** (M-497 Black Beetle) — Hook: "sounds completely insane, and honestly it kind of was." 1966, New York Central, two jet engines, 180+ mph. Outcome: data-only experiment.
5. **Railplane** (Bennie) — Hook: "tried to float above the tracks like a plane, and it actually got built." 1930s, George Bennie, Glasgow, propeller-driven. Outcome: prototype only, funding died.
6. **Monorail** (Brennan) — Hook: "balanced a train on one rail… seemed to ignore the laws of physics." 1907, Louis Brennan, two gyroscopes. Outcome: worked perfectly, too complex, lost out.
7. **Train Zeppelin** (Schienenzeppelin) — the *most famous*, placed deep not as opener. Hook: "most useless fast train ever built, but it still broke speed records." 1931, Franz Kruckenberg, 230 km/h, rear propeller. Outcome: too dangerous for normal use.
8. **Rail Truck** (Galloping Goose No. 7) — Hook: underdog, "more interesting than the biggest locomotives." 1936, Rio Grande Southern, car-tech railcar. Outcome: surprise success, kept a railroad alive.
9. **Aerotrain** (GM, CLOSER) — longest entry (~2 min), built-in debate "ahead of its time, or badly designed?" 1955, GM, "rode like a shopping cart with one bad wheel." Outcome: famous almost-success. Resonant close: "remembered not for what it became, but for what it tried and failed to be."

Note the pattern: opener = most shocking image; most famous specimen buried at #7; closer = most resonant + reflective, not most famous; outcomes deliberately mixed (failures, surprise successes, almost-rans); zero transitions, pure hard cuts.

---

## OUTLIER REFERENCE LOG (proven titles tracked for this channel)

| Title | Channel | Subs | Views | Format | Why it traveled |
|---|---|---|---|---|---|
| Weirdest Trains Ever Made Explained | Uncivil Engineer | 7.9K | 565K | Weirdest-[X] spectacle listicle | Visual specimens + repeatable franchise |
| Weirdest Machines / Airplanes / Buildings Explained | Uncivil Engineer | 7.9K | 199–361K | Same | Same engine, different category |
| Every Major Battle That Was Won by Complete Luck | Bart Ender | 200 | 53.7K | "Every-[X]" negation listicle | Title-level negation (skill is supposed to win → luck) |

The Bart Ender video is a *different* engine (title-level negation, not visual-specimen spectacle) — logged here as a separate reskin lane, not part of this format.

---

## QUICK CHECKLIST (run before drafting a "Weirdest" script)

- [ ] Topic passes the visual test — every entry is a showable object
- [ ] 12–16 candidates gathered so the final 9–10 are all strong; weakest cut
- [ ] Opener = most visually shocking specimen, NOT most famous; passes v5 four-beat 30s check
- [ ] Every entry runs the 5 beats: name → paradox hook → visual simile → mechanism+number → outcome+kicker
- [ ] Fact density = Airplanes/Trains model: each entry has ≥1 date, ≥1 named individual, ≥1 hard number
- [ ] Outcomes mixed: at least 2–3 "surprise success / almost worked" among the failures
- [ ] Rehook (~50–60%) = most jaw-dropping specimen or the recontextualizing twist
- [ ] Closer = most resonant, longer, reflective; NOT necessarily most famous
- [ ] Transitions = hard cuts / dry kickers; no forced open loops, no "the next one…"
- [ ] Voice = dry-wit restraint; similes kept, meme register cut; tonal-restraint test passed
- [ ] No outro, no CTA — final entry's last line ends the script
- [ ] 1,600–2,000 words total (~9.5–12 min); entry lengths VARIED by tier (heavy/medium/light), not uniform; opener, rehook, closer HEAVY; lights still clear the fact-density floor
- [ ] Thumbnail specimen chosen (most insane object) and matched to an early strong entry
- [ ] 4–6 candidates held back to seed Pt 2

# THE SUBJECT-TYPE LAW — v1.0
## ExplainTory doctrine. 2026-08-05.

> **What this doc does.** It establishes a channel-level law about *what kind of thing* a video can be about, records the audit that produced it, lists the contradictions it resolves in existing docs, and specifies the exact patches to fold into `explaintory-channel-skill` (next bump) and `explaintory-title-scan-sop` (next bump).
>
> **Origin.** Sapro identified this from the shape of the channel's own catalogue after the 2026-08-05 roster expansion recommended a people-format engine. The recommendation was wrong and this doc supersedes it.

---

## 1. THE LAW

**ExplainTory converts on THINGS and SYSTEMS. It does not convert on PEOPLE or EVENTS.**

Every video the channel has published, sorted by subject type:

| Subject type | Videos | Views | Verdict |
|---|---|---|---|
| **Objects / hardware** | Deadliest Weapons · Deadliest Warships · Weirdest Weapons | 512K · 137K · 111K | **3 for 3** |
| **Systems / tactics** | Roman Battle Tactics · Napoleon Battle Tactics | 145K · 52K | **2 for 2** |
| **People** | Deadliest Military Units · How Every Legendary Warrior in History Died | 2.8K · 2.7K | **0 for 2** |
| **Events** | Deadliest Battles From Every Era | 1.3K | **0 for 1** |

*(Two videos sit outside the split and are explained by existing rules: Most Feared Military Weapons of WW2, 6.4K — an object, killed by the modern-only red line. Every Advanced Tech of the Roman Empire, 2.5K — an object, killed by capability framing and a civilian-tech subject.)*

Five for five on things and systems. Zero for three on people and events. **No overlap between the two groups — the worst thing/system video outperforms the best people/event video by 19×.**

### 1.1 The reason it was missed for so long

The previously-held explanation for the death-roster flop was **roster quality** — that "legendary warriors" is a vague set and a famous, finite roster like gladiators or pharaohs would have worked.

**That theory is dead.** Deadliest Military Units had a famous, finite, visually distinct roster — Spartans, Mamluks, Soviet Guards — and did 2.8K, 0.44× median. Roster fame is not the variable. Subject type is.

### 1.2 The finding that makes it airtight — retention and views are INVERSELY ranked

This is the part that matters most, and it is why the law was invisible to every prior audit.

| Video | Subject type | AVD | Views |
|---|---|---|---|
| Deadliest Military Units | People | **41.9%** (channel best) | **2,800** (near-worst) |
| Napoleon Battle Tactics | Systems | 39.1% | 52,000 |
| Weirdest Weapons | Objects | 30.4% | 111,000 |
| Deadliest Weapons | Objects | **27.9%** (channel worst) | **512,000** (channel best) |

**Perfect inverse rank correlation across all four videos with retention data.** The higher the AVD, the fewer the views, monotonically.

That is not a coincidence and it is not a paradox. It means:

- **Subject type governs the CLICK.** Objects and systems get served and clicked; people and events do not.
- **Structure governs RETENTION.** People subjects retain beautifully because recognition carries the seams for free — that is real, measured, and unchanged.
- **The channel has been optimising the variable that does not gate views.**

Military Units posted the best AVD and the best survivors-kept in channel history and did 2.8K views. Its failure was never a content or retention failure. It was a click-and-distribution failure, and no amount of retention work would have fixed it.

### 1.3 Why the distribution layer enforces this

Confirmed independently by the 2026-08-05 suggested-traffic pull. `get_similar_videos` on the breakout returns weapons listicles, weapons compilations and "Every [Hardware] Explained" format-siblings — including subject-agnostic ones about planets and diseases. **The adjacency graph ExplainTory sits inside is shaped like hardware.** A people video would be orphaned from the cluster the channel already owns, which is exactly what 2.8K and 2.7K look like.

### 1.4 This law is a generalisation, not a new invention

SOP G5 already contains a special case of it: *"Not a 'Deadliest Battles' / 'Military Units' retread."* That line names the two corpses without naming the property they share. This doc names it.

---

## 2. THE LAW AS AN OPERATIONAL GATE

**Before any other gate, classify the candidate's subject:**

| Class | Definition | Verdict |
|---|---|---|
| **OBJECT** | A physical thing that can be drawn and that did something — weapon, ship, machine, fortification, substance, vehicle | **GO** |
| **SYSTEM** | A repeatable method or structure — tactic, formation, doctrine, logistics, engineering principle | **GO** |
| **PEOPLE** | A roster of humans or human groups — units, warriors, commanders, ranks, dynasties, roles | **STOP** — 0 for 2, needs a written override |
| **EVENT** | A thing that happened — battles, sieges-as-events, campaigns, invasions | **STOP** — 0 for 1, needs a written override |

**The override test, if a people/event candidate is ever advanced:** it must carry a hardware or system spine — the video must be *about a thing*, with the people present as operators of it. "Every Rank in a Medieval Army" is people. "Every Piece of Kit a Medieval Soldier Carried" is objects with the same research. The second one is the shape that ships.

**Note on sieges.** A siege as an *event* ("Every Failed Siege in History") is EVENT class and carries the Battles risk. A siege as *hardware* ("Every Siege Engine Explained") is OBJECT class and is clean. The word is the same; the class is not. Check which one the title actually promises.

---

## 3. AUDIT — CONTRADICTIONS FOUND IN EXISTING DOCS

### 3.1 `explaintory-channel-skill-v6.3.md` — the AVD tier table ⚠ ACTIVELY MISLEADING

Current text:

> | Famous, distinct, human subjects (elite units, named people) | **39–42%** | Channel ceiling. Recognition carries the seams for free. |

This labels the people class the **channel ceiling** and offers no counterweight. The table was built purely from four `audienceWatchRatio` curves on 2026-07-27 and **was never cross-checked against view counts**. As written, the skill recommends — on retention grounds — the one subject class that has never converted on this channel.

**Patch:** append to that row and to the section beneath it:

> **[v6.4] Retention ceiling, distribution floor.** This class posts the channel's best AVD (41.9%) and its worst views (2,800). AVD and views are inversely ranked across all four benchmarked videos. Use this row to calibrate *structure targets*, never to choose a *subject*. See the Subject-Type Law.

### 3.2 `explaintory-channel-skill-v6.3.md` — "When recognition replaces the open loop" ⚠ NEAR-DEAD RULE

Current text licenses a resonant summary-kicker close for *"named elite units, named battles, named people."* The rule is correct, but it only ever fires on subject classes we should not be commissioning.

**Patch:** mark it **rarely applicable — retained for the override case only**. Default remains implicit open loops.

### 3.3 `explaintory-channel-skill-v6.3.md` — "Subject-type calibration" ⚠ MISLEADING BY SYMMETRY

The section gives equal billing to *"For UNITS / FORCES / WARRIORS (a group of people): lead with the dark or strange ORIGIN"*, implying people subjects are a normal choice.

**Patch:** keep the craft guidance verbatim, prepend: *"the UNITS/FORCES/WARRIORS branch applies only under a Subject-Type Law override."*

### 3.4 `claude/retention-fix-era-format-v1.md` and `claude/retention-test-weirdest-weapons-v1.md` ⚠ READ WITH CARE

Both correctly instruct benchmarking against the listicle family, with Military Units (41.9%) as the model. Both are right about **retention mechanics** and both risk being read as *"make more videos like Military Units."*

**Patch:** add a one-line header to each: *"Military Units is the retention model and the distribution corpse. Copy its structure; never copy its subject class."*

### 3.5 `explaintory-title-scan-sop-v1_2.md` — G5 contains the special case, not the rule

G5's *"Not a 'Deadliest Battles' / 'Military Units' retread"* names two instances of a general property.

**Patch (SOP v1.3):** add **G0 SUBJECT TYPE** as the first gate, per §2 above. It runs before G1 because it is the cheapest possible rejection and it disqualifies candidates that would otherwise pass all seven on packaging.

### 3.6 No contradiction found

`agent-flappy-teardown-v1.md`, `browse-thumbnail-rule-v1.md`, `explaintory-suggested-traffic-sop-v1.md`, the VO docs, `hook-playbook-companion-note-v5.6.md`. The Flappy teardown's roster advice (§4 item 5, "adopt a concrete roster and rotate attributes against it") is compatible — its own suggested rosters are *every major war* and *every empire*, and the law simply adds that the rotated attribute must land on a thing, not a person.

---

## 4. SLATE RECLASSIFICATION

Applying G0 to everything currently on the board:

| Candidate | Class | Verdict |
|---|---|---|
| The Weirdest Warships Ever Built Explained | OBJECT | ✅ GO — unchanged, still #1 |
| 1 Hour of the Deadliest Weapons in Military History | OBJECT + SYSTEM | ✅ GO — compiles 3 hardware + 2 tactics videos |
| **Every Failed Weapon in History Explained** | **OBJECT** | ✅ **GO — strengthened by this law** |
| Every Drug Used in War Explained | OBJECT (substances) | ✅ GO |
| Ancient War Machines We Still Can't Explain | OBJECT | ✅ GO |
| Armor (deferred) | OBJECT | ✅ GO when it comes up |
| Naval Tactics (deferred) | SYSTEM | ✅ GO when it comes up |
| **Every Rank in a Medieval Army Explained** | **PEOPLE** | ⛔ **STOP — this is the Military Units shape** |
| The ENTIRE History of the Mongol Empire in 15 Minutes | PEOPLE/EVENT | ⚠️ **DEMOTE — civilization narrative** |
| Montgisard (hold) | EVENT | ⛔ STOP |
| Roman daily life (displaced) | PEOPLE | ⛔ STOP — drop entirely |
| Cavalry (watch) | MIXED | ⚠️ reframe to hardware/system or drop |
| How Every [Roster] Died | PEOPLE | ⛔ **STOP — not our lane. Withdrawn.** |

### 4.1 Medieval Army Ranks — the most consequential reclassification

It has sat on the slate at SHIP NORMAL for four consecutive scans. It is a hierarchy of military roles, which is people, and on this channel that class is 0-for-2. Its subject demand was already flagged UNVALIDATED in every scan. Deep Cee's 160K Roman rank video is real but it is *their* audience and *their* adjacency graph, not ours.

**Verdict: STOP.** If the research is worth keeping, reframe to the object version — **Every Piece of Kit a Medieval Soldier Carried Explained** — which uses the same reading and lands in the GO class.

### 4.2 Mongol Empire — demote, do not kill

A single-civilization chronological arc is people-and-events by construction. The engine proof is genuinely strong and accelerating (Iran anchor 273K at 2.02K subs). But it asks this channel to do the thing it has never done. **Demote below every OBJECT candidate.** If it ships, it ships as a deliberate, named experiment with the risk stated, not as a routine slate item.

---

## 5. WHAT THIS CHANGES ABOUT ENGINE SELECTION

The 2026-08-05 roster expansion ranked eleven new title engines. Re-sorted under the law:

**In lane — commission freely**

| Engine | Proofs | Best evidence |
|---|---|---|
| `Every [Category] Explained` | 7 channels | Cowball, Every Type of Gun Magazine Explained — 538K @26.9× |
| `Every Failed / Every Banned [X]` | 15+ channels, 10+ niches | Mil Gear, Every Failed M4 Replacement Attempt — 882K |
| `Every Hidden [Advantage/Weakness] of Each [X]` | 1 at scale | Swords Explained — 394K @35.8× |
| `Why [Institution] Rejected The World's Best [X]` | 1 | Weapon Programs Explained — 122K @ 3.65K subs, 93.8× |
| `Every [X] Ranked By [Unexpected Metric]` | 4 channels | Paint Skool — 320,637 @ **888 subs** |
| `The 7 Levels of [Hierarchy]` | 5 channels | rising, off-niche so far |
| `Every [X] in [N] Years` | 3 channels | Mil Gear — 317K |

**Out of lane — do not commission without an override**

| Engine | Why |
|---|---|
| `How Every [Roster] Died` | PEOPLE. Highest multiple in the research (205.8×) and still not our lane. |
| `The [Person] Who [Consequence]` | PEOPLE. Ravelin's engine is Washington, Lafayette, traitors. |
| `Every War Crime Explained` | EVENTS. 2.7M and 2.6M proofs, still the wrong class. |
| `[N] Years of [X] History in [N] Minutes` | Civilization arc — same class problem as Mongol. |

**The uncomfortable but correct consequence: the single highest-multiple engine in the entire competitive set is now off the board.** 8.03M at 205.8× median, proven at 1,670 subscribers, and we are not going to run it. That is what a real law costs. A rule that only ever agrees with the most attractive option is not a rule.

---

## 6. THE ONE-LINE VERSION

**Pick the subject class first. Objects and systems only. Then apply the retention fixes.**

Retention work is still worth doing — the 2026-08-05 analytics pull shows relative retention below the peer median for the entire runtime of the breakout, which is capping suggested placement, and the 0:45→0:52 cliff (66% → 51%) is still the highest-value single edit available. But retention is the second decision. Subject class is the first, and until now it was not a decision at all.

---

## CHANGE LOG

**v1.0 (2026-08-05)** — Created after Sapro rejected the roster-expansion doc's recommendation of the `How Every [Roster] Died` engine on the grounds that it is not the channel's lane. Audit confirmed the objection, found the inverse AVD/views correlation that explains why the pattern was invisible, and identified five contradictions in existing docs. Supersedes §1 of `claude/explaintory-roster-expansion-2026-08-05.md`.

**Pending, requires Sapro's go-ahead:** `explaintory-channel-skill-v6.4.md` with patches 3.1–3.3 baked in; `explaintory-title-scan-sop-v1_3.md` with G0 added as the first gate.

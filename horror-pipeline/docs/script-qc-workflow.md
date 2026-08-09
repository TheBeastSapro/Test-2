# Script QC Workflow (run when owner pastes a title + script [+ section structure])

When the owner pastes a video title and a full script (usually ChatGPT-drafted) and asks for script QC ("QC this script"), run this exact pass. If the owner ALSO pastes a section structure / outline, QC the script AGAINST THAT provided structure — do not impose the house structure over it. The owner's supplied structure is the target; the house rules are the craft standard applied within it.

House rules live in `automatic-scriptwriter-system-v5.md` (style DNA, banned moves, 6-beat anatomy, runtime calibration) and `claude/competitor-intel.md` (watchlist). Creature image/canon truth lives in the editor-materials doc for that video if one exists.

## ACCOUNTABILITY — standing rule (owner-requested 2026-07-24)
The owner will NOT remember every check. It is Claude's job to run the ENTIRE pass (all 11 steps below) proactively on every QC and to REPORT a checklist status at the end — green / fixed / still-open — without waiting to be asked. Do not skip the editability (7) and stageability (8) passes just because the prose reads well; those are exactly the checks the owner won't think to request. Never say "stageability looks fine" as a blanket line — actually run steps 7 and 8 sentence by sentence and show the result. If a check can't be completed (e.g. Fandom blocked for a canon claim), say so explicitly and list it as an OPEN item the owner must close before recording, rather than letting it pass silently. End every QC with the checklist so the owner can see nothing was dropped.

## Inputs the owner may provide

- **Title** (always).
- **Full script** (always).
- **Section structure / outline** (sometimes). WHEN PROVIDED: treat it as the authoritative structure. Check that the script follows it (right sections, right order, right beats per section), flag any drift FROM the owner's structure, and do NOT substitute the default house structure. WHEN NOT PROVIDED: fall back to Step 0 calibration + the v5 6-beat house structure.

## The pass, in order

1. **Structure conformance (if owner gave a structure): does the script match the provided outline?** Right sections present, correct order, each section hitting the beats the outline specifies. Flag additions, omissions, reordering, or a section that drifts from its assigned outline beat. This check REPLACES imposing the house structure — the owner's outline wins.
2. **Step 0 calibration:** identify the closest competitor video(s) for this title; check creature count, per-section word counts, structure against the v5 runtime table. If the owner gave a structure, calibrate WITHIN it (are the sections the right length?) rather than proposing a different roster/structure.
3. **Per-section 6-beat anatomy check:** name-as-opener; second-person or dramatized hook; reveal pivot (flag if the formula mixes M Simplified and Ficknime styles unintentionally); dense confident physical description (numbers only if source-checked); lore/unknown hook; single dry closer with the fear left under the surface. Hard cut between creatures, no transition sentences, no through-line.
4. **Banned-move scan (v5 list):** rhetorical setups, emotion labels/directives, echo openers, time-marker template reuse ("One night…" max once per video; also flag exact opener repeats like "after midnight" across two sections), em-dash/ellipsis abuse, trailer-voice test ("would M Simplified's narrator say this?").
5. **Hedge-word sweep:** flag confidence-weakening words (reliably, perhaps, somewhat, might, "mean very little" type hedges). Confident register is house style.
6. **Canon check:** every physical claim against the creature's wiki/creator sources (or the materials sheet if present). No invented numbers; corrections-of-the-niche allowed 1–2 per video max. If a source is unreachable (Fandom often 402/403), mark the claim UNVERIFIED and list it as an open item — do not silently pass it.
7. **EDITABILITY CHECK (learned from editor round):** flag any passage of 2+ sentences with no concrete image in it. Abstract passages become editing dead zones (all three test editors independently stalled on the same imageless 7 seconds of the Long Horse section). Every 3–4 seconds of narration needs something showable. NOTE: the "verdict" / closer beat is imageless by design in most formats — don't rewrite it, but tell the editor brief to hold on the creature (beauty shot / title card) for every verdict line.
8. **STAGEABILITY CHECK — "creature in a scene, not in a void" (learned 2026-07, root cause of slideshow editing):** This is the lever that makes editors composite (Vu look) instead of slideshow (creature-on-white). For every creature-DESCRIPTION passage, ask: is the creature *acting in a concrete environment*, or described standing in a void? A void description ("It stands 40 ft tall, arms hang to the ground, speakers where a head should be") forces the editor to paste the creature on white canvas and list parts. Rewrite it as the SAME facts happening in a place ("It unfolds from between the telephone poles at the roadside, forty feet of rusted body, arms dragging near the asphalt"). Now there are 3 layers to composite (road + poles + creature emerging) instead of one isolated PNG. RULE: every creature reveal and description beat should stage the creature IN a scene doing something. Flag void-descriptions and supply a staged rewrite. (Pure lists — e.g. "it imitates radio, sirens, conversations, help" — are legitimately icon/list beats; don't force those into scenes.)
9. **Humor density:** owner's register is jokier-Fickyep; 1–2 dry jokes per section max, each must be gag-able by an editor (visual gag possible). Flag jokes that can't be illustrated.
10. **CTA placement:** mid-roll after creature 3 (~3 min) unless the owner's structure places it elsewhere; outro CTA; near-verbatim house phrasing per v5. CTAs must be custom/woven/unlabeled if the assignment sheet says so — flag any generic "like and subscribe."
11. **Word-count report:** real counts per section (no round numbers), total, projected runtime at ~190 wpm vs the title's promised length.

## Delivery format

- Verdict summary first (what's strong, keep untouched).
- If a structure was provided: a short conformance line up top (does the script follow your outline, yes/no, what drifted).
- Weak areas: numbered list, each with section name, quoted problem line, WHY it fails (which rule), and a ready-to-use revised line.
- Stageability rewrites called out separately (they improve the EDIT, not just the script).
- Full revised script only if the owner asks; default is surgical fixes so the owner keeps control.
- Suggestions: roster order (only if no structure given), escalation, thumbnail-moment check (does one section contain the thumbnail image?).
- **END WITH A CHECKLIST STATUS covering all 11 steps** (green / fixed / open), so the owner can see nothing was skipped. List OPEN items (unverified canon, editor-brief notes) explicitly.
- No em dashes in anything meant to be pasted onward.

## Why stageability matters (editor-round evidence)

Editors: Vu Le (cinematic layered composites — creature PNG dropped into built scenes, animated) and Abel Mulu (Ficknime-native — clean, but places finished images / creature-on-white + icons). Root-cause finding: layered creature storytelling depends FIRST on the script staging the creature in a scene. Where the Siren Head script staged the creature ("waits among the poles until one of them has joints, then it moves"), it was composite-able; where it isolated the creature ("it stands 40 ft tall, arms hang down"), editors defaulted to slideshow. Owner wants the Vu cinematic look channel-wide, so the script must feed it. Fix upstream in QC, not just in editor notes.

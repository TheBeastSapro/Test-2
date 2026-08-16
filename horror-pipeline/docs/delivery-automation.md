# Delivery Automation — Mandatory Steps at Every Script Delivery

*Created 2026-07-23. This doc is the standing ops checklist that runs at the moment a script is delivered. It supplements `automatic-scriptwriter-system-v5.md` (the creative pipeline) and `claude/script-qc-workflow.md` (the QC pass). When a script is finished and handed to the owner, these steps are NOT optional — run them every time, in this order.*

## The four automations (what's now wired up)

1. **Weekly competitor radar (scheduled).** A recurring scheduled task runs every **Monday ~09:00 IST** and appends a fresh dated entry to the "Weekly Radar Log" in `claude/competitor-intel.md` — breakouts vs each channel's norm, live waves, and 2–3 recommended titles, all from live NexLev data. It runs on its own; no action needed at delivery. If a Monday passes with no new radar entry, the task may have failed — re-run it manually by asking for "this week's competitor radar."
2. **Auto-QC / audit skill.** The `horror-script-qc` skill runs the full QC pass on any pasted draft ("audit" / "reaudit" / /audit). Run it (or the equivalent in-session pass from `claude/script-qc-workflow.md`) before any script is considered delivered.
3. **Drive filing at delivery** — see below.
4. **Rotation-log auto-append at delivery** — see below.

## STEP A — Run QC before delivery (non-negotiable)
No script is "delivered" until it has passed the QC/audit pass (`horror-script-qc` skill or the workflow doc). A draft that hasn't been audited does not proceed to Steps B–C.

## STEP B — Rotation-log auto-append (MANDATORY, do not rely on memory)
Immediately after a script is delivered, append a full entry to `claude/rotation-log.md` using the template in that doc — **without being asked.** This is a hard delivery step, not a "when you remember" step. The pipeline already produced everything the entry needs, so populate every field from the delivered script:

- Date + final video title + version.
- Mode (A / B / blend).
- Creatures in our order.
- Opening pattern per section.
- Characters used · Settings used · Closers/jokes used (quote each punchline).
- Competitor overlap (which competitor videos cover the same roster + how our order/incidents/openers differ).
- Notes for next script (what's now on cooldown).

Read the last 2–3 entries **before** writing (for the anti-repetition check) and append the new one **after** delivery. The point of the auto-append is that the anti-repetition guard can never silently go stale from a forgotten update.

## STEP C — File the finished script to Google Drive (editor handoff)
After QC and the rotation-log append, push the delivery to the shared Drive folder so the editors (Vu Le, Abel Mulu) get the handoff without a manual export.

- **Target folder:** `Horror Scripts — Editor Handoff` (top level of the owner's Drive). If it does not exist yet, create it. *(As of 2026-07-23 the Google Drive connector needs re-authorization before this can run — see the note below.)*
- **What to file, per video:** create a dated sub-folder `YYYY-MM-DD — [Video Title]` and upload both deliverables into it:
  1. the final script (narration + creature headings + per-section word counts + mid/outro CTAs + source sheet + total word count), and
  2. the separate editor-materials file (canon image links, per-section shot-type tags 🎬/⚡, design notes, fan-art warnings).
- Keep the project copy as the source of truth; the Drive copy is the editor's working copy. When a script version bumps (v2, v3…), upload the new version alongside the old — never overwrite silently, matching the versioning rule in the master system doc.
- Confirm the Drive path back to the owner in plain language after filing.

### ⚠️ Google Drive re-auth needed (2026-07-23)
The Drive connector's token has expired, so Step C can't run yet. To enable it, the owner re-authorizes the Google Drive connector in their claude.ai connector settings. Until then, deliver the script + editor-materials in-conversation as files and note that Drive filing is pending re-auth.

## Order recap
QC pass → rotation-log append → Drive filing → confirm to owner. The weekly radar runs on its own schedule and needs no delivery-time action.

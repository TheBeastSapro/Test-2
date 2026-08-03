"""The skills library as two tools, because a skill nobody loads is a note in a folder.

`forgecast/skills.py` stores the operator's instruction documents and the Skills page
edits them. Until these two tools existed, nothing read them at run time: the craft was
written down, versioned, argued over — and then the agent wrote the hook from its own
instincts anyway. That is the whole gap this file closes.

## Why two tools rather than one

Listing carries `when_to_use` and a word count; loading carries the body. Handing every
body over on the first call would put the entire library into the transcript to answer a
question one document covers, and a tool that floods the context is one the model stops
reaching for. Two calls is the price of the agent choosing which documents apply.

## Why the descriptions are long

A tool is only ever called because its description made the case. "List skills" is true
and gets called never, because nothing in it says the listing is worth a turn before
writing. So each description below names the moment to call it and what goes wrong when
it is skipped — the same reason the system prompt is written the way it is.
"""

from __future__ import annotations

LIST_SKILLS = "list_skills"
LOAD_SKILL = "load_skill"

# Both of these open a markdown file and hand back what it says. Nothing here writes,
# spends or renders, so they sit in the pre-allowed read-only set: a check the agent has
# to ask permission for is a check it quietly stops making, and an unread skill is
# indistinguishable from one that was never written.
READ_ONLY: tuple[str, ...] = (LIST_SKILLS, LOAD_SKILL)

LIST_DESCRIPTION = (
    "The studio's skills: instruction documents the operator wrote, each listed with "
    "the situation it applies to and its length. Call this BEFORE you write or rewrite "
    "a script, a hook, an opening, a title, a caption, a thumbnail brief or a shot "
    "list, and before you review one. A skill that covers the task is house craft and "
    "it outranks your own defaults — it was written down precisely so nobody has to "
    "repeat it to you every week, and a hook written from instinct while a document "
    "about hooks sat unread is work that gets done twice. Bodies are not returned: read "
    "the when_to_use lines, then call load_skill on each slug that matches. Read-only "
    "and cheap. Say which skill you followed."
)

LOAD_DESCRIPTION = (
    "The full text of one skill, by the slug from list_skills. Follow it for the rest "
    "of the task and name it in your reply — a document you loaded silently cannot be "
    "checked against what you produced. An unknown slug comes back with the slugs that "
    "do exist, so ask for the right one rather than guessing at the content."
)


def build(studio) -> list:
    """The two skill tools, bound to one studio.

    Returned as a list for `tools.build_server` to splice into its own, so the MCP
    server stays a single registration. `_text` is borrowed from that module rather
    than reimplemented: it is what sets `is_error` on a returned `{"error": ...}`, and
    a second copy that forgot to would make "no such skill" read to the model as a
    successful call that happened to mention a problem.
    """
    from claude_agent_sdk import tool

    # Imported here rather than at the top: `tools` imports this module to build its
    # allowed-tool lists, and a pair of module-level imports would be a cycle.
    from .tools import _text

    @tool(LIST_SKILLS, LIST_DESCRIPTION, {})
    async def list_skills(args):
        return _text(studio.list_skills())

    @tool(LOAD_SKILL, LOAD_DESCRIPTION, {"slug": str})
    async def load_skill(args):
        return _text(studio.load_skill(args.get("slug") or ""))

    return [list_skills, load_skill]

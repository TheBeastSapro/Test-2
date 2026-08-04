"""Research: turn a topic into cited claims a script can safely use.

The house rule in the script prompts is "never invent statistics, quotes, or
citations". That rule is unenforceable if the script has nothing real to draw on — a
model asked for a documentary about deep-sea cables with no sources will produce
numbers, because the shape of the genre demands them. This package exists so there is
something true to say instead.

The shape of the pipeline:

    plan queries -> search -> fetch pages -> extract claims -> verify -> brief

Two rules do the work:

1. **Every claim carries a source URL and a supporting quote from that page.** A claim
   whose quote cannot be found in the fetched text is dropped, not softened. That check
   is mechanical, so it cannot be talked around.
2. **Unsupported is a valid, reportable outcome.** A research brief that says "no
   source found for the market-size figure" is far more useful than one that supplies a
   plausible number, because the first can be acted on and the second ships.

The research *desk* — `sources`, `outliers`, `synthesis` — is the other half of this
package and runs on the same second rule. `synthesise` is exported here because it is
the pass that answers the question a multi-channel fetch was actually asking: not what
each video did, but what the ones that won have in common, and on how many different
channels. Its `not_assessed` list is the "no source found" of that side of the desk.
"""

from .brief import Claim, ResearchBrief, Source
from .engine import research_topic
from .synthesis import Finding, Synthesis, synthesise

__all__ = [
    "Claim",
    "Finding",
    "ResearchBrief",
    "Source",
    "Synthesis",
    "research_topic",
    "synthesise",
]

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
"""

from .brief import Claim, ResearchBrief, Source
from .engine import research_topic

__all__ = ["Claim", "ResearchBrief", "Source", "research_topic"]

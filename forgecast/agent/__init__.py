"""The agent: Claude, holding this studio's operations as tools.

Modules, in the order they matter:

* `auth`       — is Claude connected, and if not, exactly what is wrong
* `studio`     — every operation the app has, as plain methods
* `tools`      — those operations wrapped as MCP tools the agent can call
* `connectors` — outside services (NexLev and friends) that add more tools
* `prefs`      — which model answers, and how much it may do unasked
* `assistant`  — the turn loop, streamed, with the conversation resumed each time
"""

from .studio import Studio, parse_link

__all__ = ["Studio", "parse_link"]

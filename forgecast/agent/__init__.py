"""The agent: Claude, holding this studio's operations as tools.

Modules, in the order they matter:

* `auth`       — is Claude connected, and if not, exactly what is wrong
* `studio`     — every operation the app has, as plain methods
* `tools`      — those operations wrapped as MCP tools the agent can call
* `connectors` — outside services (NexLev and friends) that add more tools
* `prefs`      — which model answers, and how much it may do unasked
* `assistant`  — the turn loop, streamed, with the conversation resumed each time
"""

# Deliberately no eager `from .studio import ...` here. `studio` imports SQLAlchemy, and
# the desktop launcher asks `auth` whether the Claude CLI is present *before* it has built
# the virtualenv — on the system interpreter, where SQLAlchemy does not exist. An eager
# import made `import forgecast.agent.auth` fail with `No module named 'sqlalchemy'` and
# took the whole launcher down on the first run of a fresh install, which is the one run
# that has to work.
#
# `Studio` and `parse_link` stay importable from this package for every existing caller;
# they are just resolved on first use rather than at import.

__all__ = ["Studio", "parse_link"]


def __getattr__(name: str):
    if name in __all__:
        from . import studio

        return getattr(studio, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

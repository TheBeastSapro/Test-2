"""Forgecast as a local desktop application.

`launcher.py` at the repository root is the entry point. Everything here supports it:

* `bootstrap` — prepares the machine (virtualenv, dependencies, secrets). Standard
  library only, because it runs *before* the dependencies exist.
* `supervisor` — runs the server and the worker in one process and waits for a reason
  to stop.
* `window` — puts a window in front of the operator, by whatever means the machine
  actually has.
"""

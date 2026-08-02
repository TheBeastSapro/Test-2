#!/usr/bin/env bash
# Forgecast — double-click to start (macOS and Linux).
#
# The .command extension is what makes Finder treat this as double-clickable. On Linux
# it works the same from a file manager or a terminal, given the executable bit.

cd "$(dirname "$0")" || exit 1

PY=""
for candidate in python3.13 python3.12 python3.11 python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then PY="$candidate"; break; fi
done

if [ -z "$PY" ]; then
    echo
    echo "  Python was not found."
    echo "  macOS:  brew install python@3.12"
    echo "  Linux:  apt install python3 python3-venv"
    echo
    read -r -p "  Press Enter to close… " _
    exit 1
fi

"$PY" launcher.py "$@"
status=$?

# A non-zero exit from a double-click would otherwise close the window before the
# reason could be read.
if [ "$status" -ne 0 ]; then
    read -r -p "  Press Enter to close… " _
fi
exit "$status"

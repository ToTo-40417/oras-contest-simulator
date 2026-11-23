#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1

if ! command -v python3 >/dev/null ||
   ! python3 -c 'import sys; sys.exit(sys.version_info < (3, 11))'; then
    printf '%s\n' 'Python 3.11 or newer is required.' 'https://www.python.org/downloads/'
    read -r -p 'Press Enter to close. ' _
    exit 1
fi

python3 -B -m oras_gui.server
status=$?
if (( status != 0 && status != 130 )); then
    read -r -p 'Could not start. Press Enter to close. ' _
fi
exit "$status"

"""Entry point for the self-contained Windows executable."""

import sys

from oras_contest.__main__ import main as contest_main
from oras_gui.server import main as gui_main


if __name__ == "__main__":
    if sys.argv[1:2] == ["--simulate-worker"]:
        del sys.argv[1]
        sys.stdout.reconfigure(encoding="utf-8")
        contest_main()
    else:
        gui_main()

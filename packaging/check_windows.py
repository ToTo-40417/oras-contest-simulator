"""Exercise the built EXE from outside its source directory."""

import json
import subprocess
import sys
from pathlib import Path
from urllib.request import Request, urlopen


def check(executable):
    with subprocess.Popen(
        [str(executable), "--no-browser"],
        cwd=executable.parent,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    ) as process:
        try:
            url = process.stdout.readline().strip()
            assert url.startswith("http://127.0.0.1:"), url
            for path in ("", "app.js", "style.css"):
                with urlopen(url + path, timeout=10) as response:
                    assert response.status == 200 and response.read()
            with urlopen(url + "api/options", timeout=10) as response:
                options = json.load(response)
            assert any(row["id"] == "walrein" and row["name"] == "トドゼルガ"
                       for row in options["species"])
            data = {
                "species": "walrein", "conditions": [255] * 5,
                "turns": ["roar", "giga-impact", "-", "roar", "giga-impact"],
                "category": "all", "rank": "all", "item": "none",
                "progress": "before-lisia", "hallOfFame": True, "trials": 2,
            }
            request = Request(url + "api/simulate", json.dumps(data).encode(), headers={
                "Content-Type": "application/json", "X-Contest-Token": options["token"],
            })
            with urlopen(request, timeout=60) as response:
                result = json.load(response)
            assert len(result["divisions"]) == 20
            assert result["schedule"] == ["roar", "giga-impact", None, "roar", "giga-impact"]
        finally:
            # PyInstaller one-file has a supervisor and the application process.
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           check=True, capture_output=True)
            process.wait(timeout=10)


if __name__ == "__main__":
    check(Path(sys.argv[1]).resolve())

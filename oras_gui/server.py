"""Start the local GUI with python3 -B -m oras_gui.server."""

import json
import secrets
import subprocess
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import BoundedSemaphore

from oras_contest import catalog
from oras_contest.__main__ import MEGA_ELIGIBLE

DIRECTORY = Path(__file__).resolve().parent
ROOT = DIRECTORY.parent
TOKEN = secrets.token_urlsafe(24)
PROGRESS = {"early": 0, "before-lisia": 15, "lisia": 17, "wallace": 19, "rematch": 21}
ASSETS = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
}


class LocalServer(ThreadingHTTPServer):
    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.simulation_slot = BoundedSemaphore(1)
        self.connection_slots = BoundedSemaphore(16)

    def process_request(self, request, client_address):
        if not self.connection_slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            request.settimeout(10)
            super().process_request(request, client_address)
        except Exception:
            self.connection_slots.release()
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.connection_slots.release()


def options():
    species = [
        {"id": key, "name": row["ja"], "moves": sorted(catalog.learned_moves(key) - {"struggle"}),
         "mega": key in MEGA_ELIGIBLE}
        for key, row in catalog.SPECIES.items()
    ]
    for key in sorted(catalog.FORMS):
        base = next((row for row in sorted(catalog.SPECIES, key=len, reverse=True)
                     if key.startswith(row + "-")), None)
        name = f"{catalog.SPECIES[base]['ja']}（{key[len(base) + 1:]}）" if base else key
        species.append({"id": key, "name": name,
                        "moves": sorted(catalog.learned_moves(key) - {"struggle"}), "mega": False})
    return {
        "species": species,
        "moves": {key: row["ja"] for key, row in catalog.MOVES.items()},
        "token": TOKEN,
    }


def arguments(data):
    species = data["species"]
    conditions = data["conditions"]
    turns = data["turns"]
    known = data.get("known", [])
    stage = PROGRESS[data["progress"]]
    roster_category, rank, item = data["category"], data["rank"], data["item"]
    trials = data["trials"]
    if (species not in catalog.SPECIES and species not in catalog.FORMS or
            not isinstance(turns, list) or len(turns) != 5 or
            not isinstance(known, list) or len(known) > 4 or
            any(move not in catalog.MOVES for move in known) or
            any(move not in catalog.MOVES and move != "-" for move in turns) or
            roster_category not in (*catalog.CATEGORIES, "all") or
            rank not in (*catalog.RANKS, "all") or item not in ("none", "scarf", "mega") or
            type(trials) is not int or not 1 <= trials <= 10000):
        raise ValueError("入力を確認してください。")
    catalog.intro_score("cool", conditions)
    args = ["simulate", "--npc", "cartridge", "--species", species,
            "--conditions", *map(str, conditions), "--turns", *turns,
            "--category", roster_category, "--rank", rank, "--item", item,
            "--contest-event-stage", str(stage), "--trials", str(trials)]
    if data.get("hallOfFame") is True:
        args.append("--hall-of-fame")
    if item == "scarf" and data.get("scarf") in catalog.CATEGORIES:
        args += ["--scarf-category", data["scarf"]]
    for move in known:
        args += ["--known-move", move]
    return args


class Handler(BaseHTTPRequestHandler):
    def reply(self, status, content_type, body):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; object-src 'none'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(body)

    def json_reply(self, status, value):
        self.reply(status, "application/json; charset=utf-8",
                   json.dumps(value, ensure_ascii=False).encode())

    def valid_host(self):
        return self.headers.get("Host") == f"127.0.0.1:{self.server.server_port}"

    def do_GET(self):
        if not self.valid_host():
            self.send_error(403)
        elif self.path == "/api/options":
            self.json_reply(200, options())
        elif self.path in ASSETS:
            filename, mime_type = ASSETS[self.path]
            self.reply(200, mime_type, (DIRECTORY / filename).read_bytes())
        else:
            self.send_error(404)

    def do_POST(self):
        if (not self.valid_host() or self.path != "/api/simulate" or
                self.headers.get("X-Contest-Token") != TOKEN):
            self.send_error(403)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError
            args = arguments(json.loads(self.rfile.read(length)))
        except (ValueError, KeyError, TypeError):
            self.json_reply(400, {"error": "入力を確認してください。"})
            return
        if not self.server.simulation_slot.acquire(blocking=False):
            self.json_reply(503, {"error": "別の計算を実行中です。完了してから再試行してください。"})
            return
        try:
            command = ([sys.executable, "--simulate-worker"] if getattr(sys, "frozen", False)
                       else [sys.executable, "-B", "-X", "utf8", "-m", "oras_contest"])
            result = subprocess.run(
                [*command, *args], cwd=ROOT,
                capture_output=True, timeout=120, check=False,
            )
        except subprocess.TimeoutExpired:
            self.json_reply(503, {"error": "計算が時間内に終わりませんでした。試行回数を減らしてください。"})
            return
        finally:
            self.server.simulation_slot.release()
        if result.returncode:
            self.json_reply(422, {"error": "ポケモン、技、持ち物の組み合わせを確認してください。"})
        else:
            self.reply(200, "application/json; charset=utf-8", result.stdout)


def main():
    with LocalServer() as server:
        url = f"http://127.0.0.1:{server.server_port}/"
        print(url, flush=True)
        if "--no-browser" not in sys.argv[1:]:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()

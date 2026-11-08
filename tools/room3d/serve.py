#!/usr/bin/env python3
"""Local server for the 3D viewer: serves viewer/ and writes edits made in the viewer back into the room YAML.

Usage (from the repo root):
    py -3.11 tools/room3d/serve.py [--port 8765] [--bind 127.0.0.1]

  GET  /<room>.html   the viewer; rebuilt first when rooms/<room>.yaml, apartment.yaml, the template or the builder is newer
  GET  /api/ping      lets the viewer know that saving to the server works
  POST /api/save      {"room": "kitchen-living", "changes": [{"room", "kind": "object|window|opening", "id", "set": {}, "del": []}]}
                      patches the numbers / colours of those objects in rooms/<room>.yaml (the main room, its windows
                      and openings) or apartment.yaml (the other rooms) IN PLACE: only the changed `key: value` lines are
                      touched, comments, order and layout of the file stay as they are.

No auth: bind to 127.0.0.1 unless you trust the network.
"""
import argparse
import json
import math
import re
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent                       # repo root
VIEWER = ROOT / "viewer"
LOCK = threading.Lock()                          # one save / rebuild at a time

NUMBERS = {"position", "gap", "elevation", "rotation", "width", "depth", "height", "top",
           "rails", "rail_width", "rail_thickness", "leg", "sill", "mullion", "doors", "panel", "stand"}
COLORS = {"facade", "carcass", "worktop", "color"}
LINK = re.compile(r"^=[\w\s.+\-*/()]*$")        # "=lower.height + lower.top"
HEX = re.compile(r"^#[0-9a-fA-F]{6}$")
YAML_KEY = {"sill": "sill_height"}              # viewer name -> YAML name (windows)


class BadRequest(Exception):
    pass


# ---------- in-place patching of `key: value` lines ----------
def indent_of(line):
    return len(line) - len(line.lstrip(" "))


def split_value(rest):
    """'"#fff"  # note' -> ('"#fff"', '  # note');  '12 # note' -> ('12', ' # note')."""
    rest = rest.rstrip("\r\n")
    if rest.startswith('"'):
        end = rest.find('"', 1)
        end = len(rest) if end < 0 else end + 1
        return rest[:end], rest[end:]
    m = re.search(r"\s+#", rest)
    return (rest[:m.start()], rest[m.start():]) if m else (rest.rstrip(), "")


def fmt(v, key):
    if isinstance(v, bool) or not isinstance(v, (int, float, str)):
        raise BadRequest(f"{key}: unsupported value {v!r}")
    if isinstance(v, str):
        if not (LINK.match(v) or (key in COLORS and HEX.match(v))):
            raise BadRequest(f"{key}: bad value {v!r}")
        return json.dumps(v, ensure_ascii=False)
    if not math.isfinite(v) or abs(v) > 100000:
        raise BadRequest(f"{key}: bad number {v!r}")
    return f"{v:.4f}".rstrip("0").rstrip(".") if v != int(v) else str(int(v))


def same(old_text, new_text):
    try:
        return abs(float(old_text) - float(new_text)) < 1e-9
    except ValueError:
        return old_text.strip('"') == new_text.strip('"')


def find_item(lines, lo, hi, item_id):
    """The list item `- id: <item_id>` between lines lo..hi -> (start, end, indent of the dash); end is exclusive."""
    pat = re.compile(rf'^(\s*)- id:\s*"?{re.escape(item_id)}"?\s*(#.*)?$')
    for i in range(lo, hi):
        m = pat.match(lines[i].rstrip("\r\n"))
        if m:
            ind = len(m.group(1))
            j = i + 1
            while j < hi and (not lines[j].strip() or indent_of(lines[j]) > ind):
                j += 1
            return i, j, ind
    return None


def section(lines, header, indent=0, lo=0, hi=None):
    """Lines of `header:` (a key at the given indent, searched in lo..hi) up to the next code line at that indent or less."""
    hi = len(lines) if hi is None else hi
    pat = re.compile(rf"^{' ' * indent}{re.escape(header)}:\s*(#.*)?$")
    for i in range(lo, hi):
        if pat.match(lines[i].rstrip("\r\n")):
            j = i + 1
            while j < hi and (not lines[j].strip() or lines[j].lstrip().startswith("#") or indent_of(lines[j]) > indent):
                j += 1
            return i + 1, j
    return None


def patch_item(lines, start, end, ind, key, new):
    """Set (new is not None) or delete (new is None) `key` of the item whose block is lines[start:end]."""
    field = ind + 2
    last = start
    for i in range(start + 1, end):
        line = lines[i]
        s = line.strip()
        if s and not s.startswith("#"):
            last = i
        m = re.match(rf"^{' ' * field}{re.escape(key)}:(\s*)(.*)$", line.rstrip("\r\n"))
        if m:
            eol = line[len(line.rstrip("\r\n")):]
            if new is None:
                del lines[i]
                return -1
            old, tail = split_value(m.group(2))
            if same(old, new):
                return 0
            lines[i] = f"{' ' * field}{key}:{m.group(1) or ' '}{new}{tail}{eol}"
            return 0
    if new is None:
        return 0
    eol = lines[start][len(lines[start].rstrip("\r\n")):] or "\n"
    if not lines[last].endswith(("\n", "\r")):                # the file's last line has no newline yet
        lines[last] += eol
    lines.insert(last + 1, f"{' ' * field}{key}: {new}{eol}")
    return 1


def patch_param(lines, start, end, name, new):
    """`params: {level: {value: 260, label: "..."}}` - the number of a container's own parameter."""
    for i in range(start + 1, end):
        m = re.search(rf"(\b{re.escape(name)}:\s*\{{\s*value:\s*)([^,}}]+)", lines[i])
        if m:
            if not same(m.group(2).strip(), new):
                lines[i] = lines[i][:m.start(2)] + new + lines[i][m.end(2):]
            return True
    return False


def apply_changes(room_id, changes):
    """Patch the YAML files. Returns {path: new text}; nothing is written here."""
    main_path = ROOT / "rooms" / f"{room_id}.yaml"
    apt_path = ROOT / "apartment.yaml"
    if not main_path.is_file():
        raise BadRequest(f"no such room: {room_id}")
    texts = {main_path: main_path.read_text(encoding="utf-8")}
    if apt_path.is_file():
        texts[apt_path] = apt_path.read_text(encoding="utf-8")
    lines = {p: t.splitlines(keepends=True) for p, t in texts.items()}

    for ch in changes:
        kind, item_id, rid = ch.get("kind"), ch.get("id"), ch.get("room")
        sets, dels = ch.get("set") or {}, ch.get("del") or []
        if kind not in ("object", "window", "opening") or not isinstance(item_id, str):
            raise BadRequest(f"bad change: {ch!r}")
        if kind == "object" and rid != room_id:                       # an object of another room of the flat
            if not apt_path.is_file():
                raise BadRequest(f"apartment.yaml not found for room {rid}")
            L = lines[apt_path]
            rooms = section(L, "rooms")
            r = rooms and find_item(L, *rooms, rid)
            objs = section(L, "objects", r[2] + 2, r[0], r[1]) if r else None
            if not objs:
                raise BadRequest(f"room {rid!r} has no objects in apartment.yaml")
            where = (L, objs[0], objs[1])
        elif kind == "object":
            L = lines[main_path]
            objs = section(L, "objects")
            if not objs:
                raise BadRequest(f"no objects: in rooms/{room_id}.yaml")
            where = (L, objs[0], objs[1])
        else:
            L = lines[main_path]
            sec = section(L, "windows" if kind == "window" else "openings")
            if not sec:
                raise BadRequest(f"no {kind}s: in rooms/{room_id}.yaml")
            where = (L, sec[0], sec[1])
        L, lo, hi = where
        found = find_item(L, lo, hi, item_id)
        if not found:
            raise BadRequest(f"{kind} {item_id!r} not found in the YAML of room {rid!r}")
        # keys are validated first, then patched; line numbers shift after an insert / delete, so look the item up again each time
        edits = [(k, fmt(v, k)) for k, v in sets.items()] + [(k, None) for k in dels]
        for k, new in edits:
            if k not in NUMBERS and k not in COLORS and not re.fullmatch(r"[A-Za-z_]\w*", k):
                raise BadRequest(f"bad field {k!r}")
            start, end, ind = find_item(L, lo, hi, item_id)
            ykey = YAML_KEY.get(k, k) if kind == "window" else k
            if k in NUMBERS or k in COLORS:
                shift = patch_item(L, start, end, ind, ykey, new)
                hi += shift
            elif new is not None and not patch_param(L, start, end, k, new):
                raise BadRequest(f"{item_id}: no parameter {k!r}")
    out = {p: "".join(ls) for p, ls in lines.items()}
    for p, t in out.items():
        try:
            yaml.safe_load(t)
        except yaml.YAMLError as e:
            raise BadRequest(f"the patch would break {p.name}: {e}")
    return {p: t for p, t in out.items() if t != texts[p]}


def write_atomic(path, text):
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8", newline="")
    tmp.replace(path)


# ---------- the viewer is rebuilt whenever its sources are newer ----------
def stale(html, room_yaml):
    if not html.is_file():
        return True
    srcs = [room_yaml, ROOT / "apartment.yaml", HERE / "viewer_template.html", HERE / "build_room_3d.py"]
    return any(s.is_file() and s.stat().st_mtime > html.stat().st_mtime for s in srcs)


def rebuild(html, room_yaml):
    r = subprocess.run([sys.executable, str(HERE / "build_room_3d.py"), str(room_yaml.relative_to(ROOT)),
                        "-o", str(html.relative_to(ROOT))], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    if r.returncode:
        sys.stderr.write(r.stdout + r.stderr)
    return r.returncode == 0


class Handler(SimpleHTTPRequestHandler):
    def end_headers(self):
        self.send_header("Cache-Control", "no-cache")          # the page changes with every save
        super().end_headers()

    def log_message(self, fmt_, *args):
        if "/api/ping" not in str(args[0] if args else ""):
            super().log_message(fmt_, *args)

    def reply(self, code, obj):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/api/ping":
            return self.reply(200, {"ok": True})
        name = path.lstrip("/")
        room_yaml = ROOT / "rooms" / (Path(name).stem + ".yaml")
        if name.endswith(".html") and "/" not in name and room_yaml.is_file():
            with LOCK:
                if stale(VIEWER / name, room_yaml):
                    print(f"rebuilding {name} ...", flush=True)
                    rebuild(VIEWER / name, room_yaml)          # on failure the old file (if any) is served
        super().do_GET()

    def do_POST(self):
        if self.path.split("?")[0] != "/api/save":
            return self.reply(404, {"ok": False, "error": "not found"})
        try:
            size = int(self.headers.get("Content-Length") or 0)
            if size > 1_000_000:
                raise BadRequest("request too large")
            req = json.loads(self.rfile.read(size) or b"{}")
            room_id = req.get("room")
            if not isinstance(room_id, str) or not re.fullmatch(r"[\w-]+", room_id) or not isinstance(req.get("changes"), list):
                raise BadRequest("bad request")
            with LOCK:
                files = apply_changes(room_id, req["changes"])
                for p, t in files.items():
                    write_atomic(p, t)
            names = ", ".join(p.name for p in files) or "no changes"
            print(f"saved {len(req['changes'])} item(s): {names}", flush=True)
            return self.reply(200, {"ok": True, "files": [p.name for p in files]})
        except (BadRequest, ValueError) as e:
            return self.reply(400, {"ok": False, "error": str(e)})
        except OSError as e:
            return self.reply(500, {"ok": False, "error": str(e)})


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--bind", default="127.0.0.1")
    args = ap.parse_args()
    VIEWER.mkdir(exist_ok=True)
    srv = ThreadingHTTPServer((args.bind, args.port), partial(Handler, directory=str(VIEWER)))
    print(f"viewer: http://localhost:{args.port}/  (edits are saved into {ROOT})", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

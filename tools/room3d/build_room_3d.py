#!/usr/bin/env python3
"""Build an interactive 3D viewer (single HTML file, three.js) from a planhaus room YAML.

Usage (from the repo root):
    python3 tools/room3d/build_room_3d.py rooms/kitchen-living.yaml -o viewer/kitchen-living.html

Geometry comes from tools/planhaus/scripts/room_spatial.py --json (the same engine that
validates clearances), so the 3D model always matches what the rules engine checked.
Extra 3D-only fields are read straight from the YAML; all are optional:

  ceiling_height: 270 | {main: 270, ...}
  wall_thickness: 12                      # cm, drawn outward from the room outline
  windows[]:   sill_height (cm, default 85; 0 for type door/balcony-door/sliding-door)
               height      (cm, default 145; 210 for door types)
  openings[]:  height      (cm, default 210)
               swing: in | out            (door leaf side, default in)
               hinge: start | end         (default start = nearer the wall's first letter)
  built_ins[]: height (default 90 for kitchen, 220 otherwise), elevation (default 0),
               color ("#rrggbb"), countertop: true|false (default true for kitchen),
               upper: {depth: 35, height: 72, elevation: 145}   # wall cabinets above
  furniture[]: color, elevation (cm above floor; overrides mount/on logic)
  objects[]:   everything that stands in a room - furniture, cabinets, appliances, door leaves. The SAME format in
               every room (this YAML and `rooms[].objects` of apartment.yaml); edited in the viewer, not checked by
               the rules engine. An object stands against a wall of its room and is described by its WIDTH, DEPTH
               and HEIGHT - never by sizes along the X / Y axes (x, y, sx, sy, against, items: are rejected):
               id, label, wall, position (cm from the wall's
               first corner), width (along the wall), depth (from the wall), height, elevation (default 0),
               gap (wall to back of the object, default 0),
               rotation (degrees clockwise seen from above, about the centre of the box, default 0; the box is
                      still described against its wall - only its drawing turns), top (countertop thickness, optional), color,
               model (optional .glb, path from the repo root or the YAML's folder; embedded into the HTML;
                      its bounding box is fitted into the object's box, its front (+Z) faces the room;
                      a manufacturer's .3ds converts with tools/room3d/tds_to_glb.py),
               cutout: {in: <object id>, width, depth}   # hole of that size, centred under this object,
                      through the other object's body and worktop (a sink in a base cabinet)
               kitchen: true -> a kitchen cabinet: body in the carcass colour of the room's `type: kitchen` object,
                      a front panel in its facade colour (the side facing the room), worktop (`top`) in its worktop colour;
               kitchen: panel -> a plain board (end panel, divider) wholly in the carcass colour, no front;
               facade_side: start | end  -> the front panel on the side facing the wall's first / second corner
                      instead (a peninsula with its doors towards the kitchen run)
  INHERITANCE AND LINKS (same in every room):
               parent: <id of a `type: group` / `type: kitchen` object>  -> a container without geometry that
                      groups objects in the tree. An object that does not set height / depth / elevation / gap / top
                      takes them from its parent (and from the parent's parent...). Typical: a kitchen = one
                      `type: kitchen` object (facade / carcass / worktop colours of every `kitchen:` cabinet) with
                      parts `lower` (height, depth, top) and `upper`; every cabinet inside inherits from its part.
               params: {level: 260}  or  {level: {value: 260, label: "..."}}   own numbers of a container
               any number may be a LINK: "=<expression>" (quote it). A bare name is a property of this very object,
                      `id.name` is a property of another object / opening of the room: "=upper.level - elevation",
                      "=lower.height + lower.top", "=portal.width + 1". Operators + - * / and (); put spaces
                      around a minus (ids contain hyphens). An inherited link is evaluated for the child.
                      Openings: only `height` may be a link (position / width are read by the rules engine).
               type: kitchen -> also facade, carcass, worktop ("#rrggbb"): the palette of the room's kitchen
               type: portal  -> a П-shaped arch of `rails` identical frames spread evenly over `depth`
                      (from the wall into the room); rail_width = size of one frame along the depth,
                      rail_thickness = its profile (legs and top bar); width/height = outer size of the arch
               type: table   -> a slab (`top` thick, default 4) on four square legs (`leg` section, default 5),
                      5 cm in from the edges; height = to the top surface; kitchen: true = slab in the worktop colour

Coordinates: origin = corner A, X = east, Y = north, cm (planhaus convention).

The rest of the apartment comes from apartment.yaml (next to rooms/, or --apartment) when its
`frame:` is this room's id: per room a floor polygon, wall boxes, glass panes and `objects:`, all in this
room's coordinates (format in apartment.yaml). A room's walls for `wall:` are the edges of its floor outline,
A-B, B-C, ... in the order of `floor` (the kitchen: its own walls). The viewer lists every room, this one
included, as an equal tree node with the same parts - walls, openings, objects; the other rooms start hidden.
"""
import argparse
import base64
import json
import re
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SPATIAL = HERE.parent / "planhaus" / "scripts" / "room_spatial.py"
TEMPLATE = HERE / "viewer_template.html"

DEFAULT_HEIGHTS = {
    "sofa": 85, "armchair": 85, "coffee-table": 42, "side-table": 55,
    "dining-table": 75, "dining-chair": 85, "desk": 75, "desk-chair": 95,
    "bed": 50, "nightstand": 55, "wardrobe": 220, "dresser": 85,
    "bookshelf": 200, "tv": 65, "rug": 1, "floor-lamp": 150, "table-lamp": 45,
    "plant": 120, "kitchen": 90, "island": 90, "fridge": 200, "other": 80,
}
COLORS = {
    "sofa": "#8a9bb0", "armchair": "#9aa98a", "coffee-table": "#8b5e3c",
    "side-table": "#8b5e3c", "dining-table": "#a0703f", "dining-chair": "#6f4e37",
    "desk": "#a0703f", "desk-chair": "#555555", "bed": "#c9b8a6", "nightstand": "#8b5e3c",
    "wardrobe": "#d8cfc4", "dresser": "#d8cfc4", "bookshelf": "#b08b5e", "tv": "#111111",
    "rug": "#c7a98b", "floor-lamp": "#d4af37", "table-lamp": "#d4af37", "plant": "#4f7d4a",
    "kitchen": "#e9e6df", "island": "#e9e6df", "fridge": "#cfd3d6", "other": "#b9b0a5",
}
DOOR_TYPES = {"door", "balcony-door", "sliding-door", "french-door", "terrace-door"}


def num(v, default):
    try:
        return float(v) if v is not None else float(default)
    except (TypeError, ValueError):
        return float(default)


def by_id(items):
    return {i.get("id"): i for i in (items or []) if isinstance(i, dict)}


REMOVED = {"x": "wall + position + gap", "y": "wall + position + gap", "sx": "width / depth", "sy": "width / depth",
           "against": "wall", "group": "parent: <id of a type: group object>"}
CONTAINERS = ("group", "kitchen")                     # objects without geometry: they hold the sizes their children inherit
NUMERIC = ("position", "gap", "elevation", "rotation", "width", "depth", "height", "top")


def raw(v, default=None):
    """A number, an "=expression" (a link, evaluated by the viewer) or the default."""
    if isinstance(v, str) and v.strip().startswith("="):
        return v.strip()
    try:
        return float(v) if v is not None else default
    except (TypeError, ValueError):
        return default


def make_object(o, wall_ids, embed_model, where):
    """One room object, the same for every room. Returns None (with a message) if it cannot be placed."""
    if not (isinstance(o, dict) and o.get("id")):
        return None
    bad = [f"{k} (use {v})" for k, v in REMOVED.items() if k in o]
    if bad:
        sys.exit(f"{where}[{o['id']}]: not allowed: {', '.join(bad)}. An object has wall + position + gap and "
                 f"width (along the wall) x depth (away from it) x height")
    kind = o.get("type") if o.get("type") in ("portal", "table") + CONTAINERS else None
    if kind not in CONTAINERS and o.get("wall") not in wall_ids:
        sys.stderr.write(f"{where}[{o['id']}]: wall {o.get('wall')!r} is not a wall of this room "
                         f"({', '.join(sorted(wall_ids))}), skipped\n")
        return None
    params = {}
    for name, v in (o.get("params") or {}).items():
        params[name] = {"value": raw(v.get("value") if isinstance(v, dict) else v, 0),
                        "label": (v.get("label") if isinstance(v, dict) else None) or name}
    out = {
        "id": o["id"], "label": o.get("label") or o["id"], "type": kind, "parent": o.get("parent"), "wall": o.get("wall"),
        **{k: raw(o.get(k)) for k in NUMERIC},          # None = not set: inherited from the parent, else a default
        "color": o.get("color") or COLORS["other"], "params": params,
        "model": embed_model(o["id"], o["model"]) if o.get("model") else None,
        "cutout": o.get("cutout") if isinstance(o.get("cutout"), dict) else None,
        "kitchen": "panel" if o.get("kitchen") == "panel" else bool(o.get("kitchen")),
        "facade_side": o.get("facade_side") if o.get("facade_side") in ("start", "end") else None,
    }
    if kind == "kitchen":
        out.update({k: str(o.get(k) or COLORS["other"]) for k in ("facade", "carcass", "worktop")})
    if kind == "portal":
        out.update({"rails": raw(o.get("rails"), 6), "rail_width": raw(o.get("rail_width"), 2),
                    "rail_thickness": raw(o.get("rail_thickness"), 4)})
    elif kind == "table":
        out.update({"top": raw(o.get("top"), 4), "leg": raw(o.get("leg"), 5)})
    return out


def check_links(objects, openings, where):
    """parent ids exist and are containers, no loops, every id used in an "=expression" exists."""
    by = {o["id"]: o for o in objects}
    ids = set(by) | {h["id"] for h in openings}
    for o in objects:
        p = o["parent"]
        if p is not None and (p not in by or by[p]["type"] not in CONTAINERS):
            sys.exit(f"{where}[{o['id']}]: parent {p!r} is not a `type: group` / `type: kitchen` object of this room")
        seen, q = set(), o
        while q and q["parent"]:
            if q["id"] in seen:
                sys.exit(f"{where}[{o['id']}]: parent loop")
            seen.add(q["id"]); q = by.get(q["parent"])
    for o in [*objects, *openings]:
        vals = [o.get(k) for k in NUMERIC + ("sill",)] + [p["value"] for p in o.get("params", {}).values()]
        for v in vals:
            for ref in re.findall(r"([A-Za-z_][\w-]*)\.[A-Za-z_]", v) if isinstance(v, str) else []:
                if ref not in ids:
                    sys.exit(f"{where}[{o['id']}]: link {v!r} names {ref!r}, which is not an object or opening of this room")


def load_apartment(path, room_id, required, embed_model):
    """Other rooms of the apartment, in this room's coordinates: the same parts as the main room."""
    if not path.is_file():
        if required:
            sys.exit(f"{path}: not found")
        return []
    apt = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if apt.get("frame") != room_id:
        if required:
            sys.exit(f"{path}: frame is {apt.get('frame')!r}, not {room_id!r}")
        return []
    boxes = lambda rows, n: [[float(v) for v in r] for r in rows or [] if isinstance(r, list) and len(r) in n]

    rooms = []
    for r in apt.get("rooms") or []:
        if not (isinstance(r, dict) and r.get("id")):
            continue
        if "items" in r:
            sys.exit(f"apartment room {r['id']}: `items:` is gone - use `objects:` (wall, position, gap, width, depth, height)")
        floor = [[float(x), float(y)] for x, y in r.get("floor") or []]
        wall_ids = {f"{chr(65 + i)}-{chr(65 + (i + 1) % len(floor))}" for i in range(len(floor))}
        objects = [x for x in (make_object(o, wall_ids, embed_model, f"apartment {r['id']} objects") for o in r.get("objects") or []) if x]
        check_links(objects, [], f"apartment {r['id']} objects")
        rooms.append({
            "id": r["id"], "name": r.get("name") or r["id"], "area_m2": r.get("area_m2"),
            "floor": floor,
            "floor_color": r.get("floor_color"),             # none = the kitchen's laminate
            "walls": boxes(r.get("walls"), (4, 6)), "glass": boxes(r.get("glass"), (6,)),
            "objects": objects,
        })
    return rooms


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("room", help="room YAML (planhaus format)")
    ap.add_argument("-o", "--out", help="output HTML (default: viewer/<room-id>.html)")
    ap.add_argument("--title", help="page title")
    ap.add_argument("--apartment", help="apartment YAML with the other rooms (default: apartment.yaml next to rooms/)")
    args = ap.parse_args()

    room_path = Path(args.room)
    room = yaml.safe_load(room_path.read_text(encoding="utf-8")) or {}
    res = subprocess.run([sys.executable, str(SPATIAL), str(room_path), "--json"],
                         capture_output=True, text=True)
    try:
        spatial = json.loads(res.stdout)
    except ValueError:
        sys.stderr.write(res.stdout + res.stderr)
        sys.exit("room_spatial.py did not return JSON — fix the room YAML first (/planhaus-validate)")

    corners = spatial["corners"]
    ch = room.get("ceiling_height", 260)
    ceiling = num(ch.get("main") if isinstance(ch, dict) else ch, 260)
    thickness = num(room.get("wall_thickness"), 12)

    walls = []
    for w in room.get("walls", []):
        a, b = w["id"].split("-")
        walls.append({"id": w["id"], "a": corners[a], "b": corners[b], "length": num(w.get("length"), 0)})

    y_windows, y_openings = by_id(room.get("windows")), by_id(room.get("openings"))
    y_builtins, y_furniture = by_id(room.get("built_ins")), by_id(room.get("furniture"))

    holes, built, furn, lights = [], [], [], []
    for o in spatial["objects"]:
        t = o.get("type")
        if t == "window":
            y = y_windows.get(o["id"], {})
            wtype = o.get("window_type") or y.get("type") or "window"
            is_door = wtype in DOOR_TYPES
            holes.append({
                "kind": "window", "id": o["id"], "wall": o["wall"],
                "position": num(y.get("position"), 0), "width": num(o.get("width"), 0),
                "sill": num(y.get("sill_height"), 0 if is_door else 85),
                "height": num(y.get("height"), 210 if is_door else 145),
                "subtype": wtype,
            })
        elif t == "opening":
            y = y_openings.get(o["id"], {})
            holes.append({
                "kind": "opening", "id": o["id"], "wall": o["wall"],
                "position": num(y.get("position"), 0), "width": num(o.get("width"), 0),
                "sill": 0, "height": raw(y.get("height"), 210),
                "has_door": bool(o.get("has_door")), "swing": y.get("swing", "in"),
                "hinge": y.get("hinge", "start"), "to": o.get("to"),
            })
        elif t == "built_in" and o.get("bbox"):
            y = y_builtins.get(o["id"], {})
            kind = o.get("item_type") or y.get("type") or "other"
            is_kitchen = kind in ("kitchen", "island") or "kitchen" in o["id"]
            built.append({
                "id": o["id"], "bbox": o["bbox"], "wall": o.get("wall"),
                "height": num(y.get("height"), 90 if is_kitchen else 220),
                "elevation": num(y.get("elevation"), 0),
                "color": y.get("color") or COLORS.get(kind, COLORS["other"]),
                "countertop": bool(y.get("countertop", is_kitchen)),
                "upper": y.get("upper"), "depth": num(o.get("depth"), 60),
                "label": y.get("label") or o["id"],
            })
        elif t == "furniture" and o.get("bbox"):
            y = y_furniture.get(o["id"], {})
            kind = o.get("item_type") or "other"
            dims = o.get("dims") or {}
            h = num(dims.get("height"), DEFAULT_HEIGHTS.get(kind, 80))
            if y.get("elevation") is not None:
                elev = num(y.get("elevation"), 0)
            elif o.get("mount") == "wall":
                elev = max(0.0, num(o.get("height"), 120) - h / 2)
            else:
                elev = 0.0
            furn.append({"id": o["id"], "bbox": o["bbox"], "height": h, "elevation": elev,
                         "on": o.get("on"), "type": kind,
                         "color": y.get("color") or COLORS.get(kind, COLORS["other"]),
                         "facing": o.get("facing")})
        elif t == "light":
            lights.append({"id": o["id"], "pos": o["pos"], "mount": o.get("mount"),
                           "hang": o.get("hang_height_cm"), "layer": o.get("layer")})

    # items that sit on other items start at the base item's top
    tops = {f["id"]: f["elevation"] + f["height"] for f in furn}
    tops.update({b["id"]: b["elevation"] + b["height"] + (4 if b["countertop"] else 0) for b in built})
    for f in furn:
        if f["on"] and f["on"] in tops and y_furniture.get(f["id"], {}).get("elevation") is None:
            f["elevation"] = tops[f["on"]]

    wall_ids = {w["id"] for w in walls}
    models = {}

    def embed_model(oid, ref):
        if ref in models:
            return ref
        for p in (Path(ref), room_path.parent / ref):
            if p.is_file():
                models[ref] = "data:model/gltf-binary;base64," + base64.b64encode(p.read_bytes()).decode()
                return ref
        sys.stderr.write(f"objects[{oid}]: model {ref!r} not found, drawing a box\n")
        return None

    objects = [x for x in (make_object(o, wall_ids, embed_model, "objects") for o in room.get("objects") or []) if x]
    check_links(objects, [h for h in holes if h["kind"] == "opening"], "objects")
    if room.get("kitchen_colors"):
        sys.exit("kitchen_colors: is gone - put facade / carcass / worktop on the `type: kitchen` object in objects:")
    room_id = room.get("id") or room_path.stem

    data = {
        "objects": objects, "models": models,
        "id": room_id,
        "apartment": load_apartment(Path(args.apartment) if args.apartment else room_path.parent.parent / "apartment.yaml",
                                    room_id, bool(args.apartment), embed_model),
        "name": room.get("name") or room.get("id") or room_path.stem,
        "area_m2": (room.get("validation") or {}).get("calculated_area") or room.get("area_m2"),
        "ceiling": ceiling, "thickness": thickness, "walls": walls, "holes": holes,
        "builtins": built, "furniture": furn, "lights": lights,
        "zones": [{"id": z.get("id"), "bounds": z.get("bounds")} for z in room.get("zones") or []
                  if isinstance(z, dict) and z.get("bounds")],
        "warnings": spatial.get("warnings", []),
    }
    out = Path(args.out) if args.out else Path("viewer") / f"{room.get('id') or room_path.stem}.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    html = TEMPLATE.read_text(encoding="utf-8")
    html = html.replace("__TITLE__", args.title or f"3D: {data['name']}")
    html = html.replace("__ROOM_DATA__", json.dumps(data, ensure_ascii=False))
    out.write_text(html, encoding="utf-8")
    print(f"wrote {out}  ({len(walls)} walls, {len(holes)} openings, {len(built)} built-ins, {len(furn)} items, "
          f"{len(objects)} objects, {len(data['apartment'])} other rooms with "
          f"{sum(len(r['objects']) for r in data['apartment'])} objects)")


if __name__ == "__main__":
    main()

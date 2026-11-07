#!/usr/bin/env python3
"""Convert a 3D Studio (.3ds) model, e.g. a manufacturer's CAD download, to a binary glTF (.glb)
that the 3D viewer can embed (objects[].model in the room YAML).

Usage (from the repo root):
    python3 tools/room3d/tds_to_glb.py in.3ds -o assets/models/name.glb \
        [--scale 1] [--mat ma4=#d9dcdf:1:0.15 ...] [--copyright "..."]

What it does:
  - reads every mesh object (vertices, faces, material groups, smoothing groups) and every material
    (diffuse colour, transparency); textures are ignored (manufacturer CAD files rarely have them);
  - computes vertex normals from the 3DS smoothing groups (hard edges stay hard);
  - converts axes: 3DS is Z-up, glTF is Y-up: (x, y, z) -> (x, z, -y). So the model's -Y side
    (the front in 3DS) becomes +Z, which is the glTF "front" the viewer turns towards the room;
  - merges all objects into one mesh with one primitive per material; units are kept (--scale to change).
--mat NAME=#rrggbb:metalness:roughness overrides a material (3DS has no PBR data; e.g. chrome = :1:0.15).
"""
import argparse
import json
import math
import struct
from pathlib import Path


def parse_3ds(data):
    materials, objects = {}, []

    def cstr(o):
        e = data.index(b"\0", o)
        return data[o:e].decode("latin1"), e + 1

    def color(o, end):                      # first colour sub-chunk (0x0011 bytes or 0x0010 floats)
        while o + 6 <= end:
            cid, ln = struct.unpack_from("<HI", data, o)
            if cid == 0x0011:
                return [c / 255 for c in data[o + 6:o + 9]]
            if cid == 0x0010:
                return list(struct.unpack_from("<3f", data, o + 6))
            o += ln
        return None

    def percent(o, end):
        while o + 6 <= end:
            cid, ln = struct.unpack_from("<HI", data, o)
            if cid == 0x0030:
                return struct.unpack_from("<H", data, o + 6)[0] / 100
            if cid == 0x0031:
                return struct.unpack_from("<f", data, o + 6)[0] / 100
            o += ln
        return 0.0

    def walk(o, end, ctx):
        while o + 6 <= end:
            cid, ln = struct.unpack_from("<HI", data, o)
            body, nxt = o + 6, o + ln
            if ln < 6 or nxt > end:
                raise ValueError(f"broken chunk {cid:#06x} at {o}")
            if cid in (0x4D4D, 0x3D3D, 0x4100):
                walk(body, nxt, ctx)
            elif cid == 0xAFFF:
                m = {}
                walk(body, nxt, m)
                if "name" in m:
                    materials[m["name"]] = m
            elif cid == 0xA000:
                ctx["name"] = cstr(body)[0]
            elif cid == 0xA020:
                ctx["diffuse"] = color(body, nxt)
            elif cid == 0xA050:
                ctx["transparency"] = percent(body, nxt)
            elif cid == 0x4000:
                obj = {"name": cstr(body)[0], "verts": [], "faces": [], "groups": [], "smooth": []}
                walk(cstr(body)[1], nxt, obj)
                if obj["verts"] and obj["faces"]:
                    objects.append(obj)
            elif cid == 0x4110:
                n = struct.unpack_from("<H", data, body)[0]
                v = struct.unpack_from(f"<{3 * n}f", data, body + 2)
                ctx["verts"] = [v[i:i + 3] for i in range(0, 3 * n, 3)]
            elif cid == 0x4120:
                n = struct.unpack_from("<H", data, body)[0]
                f = struct.unpack_from(f"<{4 * n}H", data, body + 2)
                ctx["faces"] = [f[i:i + 3] for i in range(0, 4 * n, 4)]
                walk(body + 2 + 8 * n, nxt, ctx)
            elif cid == 0x4130:
                name, p = cstr(body)
                n = struct.unpack_from("<H", data, p)[0]
                ctx["groups"].append((name, struct.unpack_from(f"<{n}H", data, p + 2)))
            elif cid == 0x4150:
                ctx["smooth"] = list(struct.unpack_from(f"<{len(ctx['faces'])}I", data, body))
            o = nxt

    walk(0, len(data), {})
    return materials, objects


def sub(a, b): return (a[0] - b[0], a[1] - b[1], a[2] - b[2])
def cross(a, b): return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])
def norm(a):
    l = math.sqrt(a[0] ** 2 + a[1] ** 2 + a[2] ** 2) or 1.0
    return (a[0] / l, a[1] / l, a[2] / l)


def build_primitives(objects, scale):
    """-> {material: (positions, normals, indices)} in glTF axes."""
    prims = {}
    for ob in objects:
        V = [(x * scale, z * scale, -y * scale) for x, y, z in ob["verts"]]   # Z-up -> Y-up
        F, S = ob["faces"], ob["smooth"] or [0] * len(ob["faces"])
        fn = [cross(sub(V[b], V[a]), sub(V[c], V[a])) for a, b, c in F]     # area-weighted face normals
        at = {}
        for fi, f in enumerate(F):
            for v in f:
                at.setdefault(v, []).append(fi)
        mat_of = {}
        for name, idx in ob["groups"]:
            for fi in idx:
                mat_of[fi] = name
        for fi, f in enumerate(F):
            mat = mat_of.get(fi, "default")
            pos, nrm, ind, seen = prims.setdefault(mat, ([], [], [], {}))
            for v in f:
                if S[fi]:
                    acc = [0.0, 0.0, 0.0]
                    for g in at[v]:
                        if S[g] & S[fi]:
                            acc = [acc[k] + fn[g][k] for k in range(3)]
                    n = norm(acc)
                else:
                    n = norm(fn[fi])
                key = (ob["name"], v, round(n[0], 3), round(n[1], 3), round(n[2], 3))
                if key not in seen:
                    seen[key] = len(pos)
                    pos.append(V[v]); nrm.append(n)
                ind.append(seen[key])
    return {m: p[:3] for m, p in prims.items() if p[2]}


def write_glb(path, prims, materials, overrides, name, copyright_):
    bin_, views, accessors, gl_mats, gl_prims = bytearray(), [], [], [], []

    def add(blob, target):
        while len(bin_) % 4:
            bin_.append(0)
        views.append({"buffer": 0, "byteOffset": len(bin_), "byteLength": len(blob), "target": target})
        bin_.extend(blob)
        return len(views) - 1

    for mat, (pos, nrm, ind) in sorted(prims.items()):
        src = materials.get(mat, {})
        rgb = src.get("diffuse") or [0.8, 0.8, 0.8]
        metal, rough = 0.0, 0.6
        if mat in overrides:
            rgb, metal, rough = overrides[mat]
        lin = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb]   # glTF colours are linear
        alpha = 1.0 - src.get("transparency", 0.0)
        m = {"name": mat, "pbrMetallicRoughness": {"baseColorFactor": [*lin, alpha], "metallicFactor": metal,
                                                    "roughnessFactor": rough}}
        if alpha < 1:
            m["alphaMode"] = "BLEND"
        gl_mats.append(m)
        flat = [c for p in pos for c in p]
        pa = len(accessors)
        accessors.append({"bufferView": add(struct.pack(f"<{len(flat)}f", *flat), 34962), "componentType": 5126,
                          "count": len(pos), "type": "VEC3",
                          "min": [min(p[k] for p in pos) for k in range(3)],
                          "max": [max(p[k] for p in pos) for k in range(3)]})
        flat = [c for n in nrm for c in n]
        accessors.append({"bufferView": add(struct.pack(f"<{len(flat)}f", *flat), 34962), "componentType": 5126,
                          "count": len(nrm), "type": "VEC3"})
        big = len(pos) > 65535
        accessors.append({"bufferView": add(struct.pack(f"<{len(ind)}{'I' if big else 'H'}", *ind), 34963),
                          "componentType": 5125 if big else 5123, "count": len(ind), "type": "SCALAR"})
        gl_prims.append({"attributes": {"POSITION": pa, "NORMAL": pa + 1}, "indices": pa + 2,
                         "material": len(gl_mats) - 1})

    while len(bin_) % 4:
        bin_.append(0)
    asset = {"version": "2.0", "generator": "tools/room3d/tds_to_glb.py"}
    if copyright_:
        asset["copyright"] = copyright_
    gltf = {"asset": asset, "scene": 0, "scenes": [{"nodes": [0]}], "nodes": [{"name": name, "mesh": 0}],
            "meshes": [{"name": name, "primitives": gl_prims}], "materials": gl_mats, "accessors": accessors,
            "bufferViews": views, "buffers": [{"byteLength": len(bin_)}]}
    js = json.dumps(gltf, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    out = struct.pack("<4sII", b"glTF", 2, 12 + 8 + len(js) + 8 + len(bin_))
    out += struct.pack("<I4s", len(js), b"JSON") + js + struct.pack("<I4s", len(bin_), b"BIN\0") + bin_
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)
    return gltf


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help=".3ds file")
    ap.add_argument("-o", "--out", required=True, help="output .glb")
    ap.add_argument("--scale", type=float, default=1.0, help="multiply coordinates (3DS units -> metres)")
    ap.add_argument("--mat", action="append", default=[], metavar="NAME=#rrggbb:metal:rough")
    ap.add_argument("--copyright", default="")
    args = ap.parse_args()

    overrides = {}
    for spec in args.mat:
        name, val = spec.split("=", 1)
        col, metal, rough = (val.split(":") + ["0", "0.6"])[:3]
        col = col.lstrip("#")
        overrides[name] = ([int(col[i:i + 2], 16) / 255 for i in (0, 2, 4)], float(metal), float(rough))

    materials, objects = parse_3ds(Path(args.src).read_bytes())
    prims = build_primitives(objects, args.scale)
    gltf = write_glb(args.out, prims, materials, overrides, Path(args.out).stem, args.copyright)
    lo = [min(a["min"][k] for a in gltf["accessors"] if "min" in a) for k in range(3)]
    hi = [max(a["max"][k] for a in gltf["accessors"] if "max" in a) for k in range(3)]
    tris = sum(len(p[2]) // 3 for p in prims.values())
    print(f"wrote {args.out}: {len(objects)} objects, {tris} triangles, materials {sorted(prims)}")
    print("size (x along front, y up, z depth): " + " x ".join(f"{(hi[k] - lo[k]) * 100:.1f}" for k in range(3))
          + " cm;  bbox min " + str([round(v, 4) for v in lo]) + " max " + str([round(v, 4) for v in hi]))


if __name__ == "__main__":
    main()

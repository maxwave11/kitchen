#!/usr/bin/env python3
"""Convert a Wavefront .obj (e.g. a Configura / manufacturer download) to a binary glTF (.glb)
that the 3D viewer can embed (objects[].model in the room YAML). No dependencies.

Usage (from the repo root):
    py -3.11 tools/room3d/obj_to_glb.py in.obj -o assets/models/name.glb \
        [--scale 1] [--rotate-y 180] [--mat CET_black_2=#1c1c1c:0.2:0.5 ...] [--list]

What it does:
  - reads v / vn / f (triangles and polygons, fan-triangulated) and `usemtl` groups; one glTF primitive per material;
    normals come from the file (vn), textures (vt) and the .mtl file are ignored (it is often missing): colour every
    material with --mat (run --list first: it prints the material names, face counts and the model's size);
  - an .obj is already Y-up (glTF axes); --scale converts file units to metres (Configura exports are metres: 1);
  - the viewer turns the model's FRONT (+Z in glTF) towards the room. Many .obj files look along -Z: if the backrest /
    the front of the model is on the +Z side, pass --rotate-y 180 (about the vertical axis; 90 / 270 also work).
The model is placed anywhere in space: the viewer fits its bounding box into the object's box, so only the size matters.
"""
import argparse
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tds_to_glb as t  # noqa: E402  (write_glb is shared with the .3ds converter)


def parse_obj(path):
    V, N, groups, mat = [], [], {}, "default"
    for line in Path(path).read_text(encoding="utf-8", errors="replace").splitlines():
        p = line.split()
        if not p:
            continue
        if p[0] == "v":
            V.append(tuple(map(float, p[1:4])))
        elif p[0] == "vn":
            N.append(tuple(map(float, p[1:4])))
        elif p[0] == "usemtl":
            mat = p[1] if len(p) > 1 else "default"
        elif p[0] == "f":
            idx = []
            for c in p[1:]:
                a = c.split("/")
                v = int(a[0]); v = v - 1 if v > 0 else len(V) + v
                n = int(a[2]) if len(a) > 2 and a[2] else 0
                n = (n - 1 if n > 0 else len(N) + n) if n else None
                idx.append((v, n))
            for k in range(1, len(idx) - 1):
                groups.setdefault(mat, []).append((idx[0], idx[k], idx[k + 1]))
    return V, N, groups


def build(V, N, groups, scale, rot):
    c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
    turn = lambda x, y, z: (x * c + z * s, y, -x * s + z * c)          # about Y
    prims = {}
    for mat, faces in groups.items():
        pos, nrm, ind, seen = [], [], [], {}
        for tri in faces:
            a, b, d = (V[tri[i][0]] for i in range(3))
            fn = t.cross(t.sub(b, a), t.sub(d, a))                     # face normal when the file has no vn
            for v, n in tri:
                key = (v, n)
                if key not in seen:
                    seen[key] = len(pos)
                    pos.append(turn(*(x * scale for x in V[v])))
                    nrm.append(turn(*t.norm(N[n] if n is not None else fn)))
                ind.append(seen[key])
        prims[mat] = (pos, nrm, ind)
    return prims


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help=".obj file")
    ap.add_argument("-o", "--out", help="output .glb")
    ap.add_argument("--scale", type=float, default=1.0, help="file units -> metres (default 1)")
    ap.add_argument("--rotate-y", type=float, default=0.0, help="degrees about the vertical axis (180 = front to the other side)")
    ap.add_argument("--mat", action="append", default=[], metavar="NAME=#rrggbb:metal:rough")
    ap.add_argument("--list", action="store_true", help="only print materials and size")
    ap.add_argument("--copyright", default="")
    args = ap.parse_args()

    V, N, groups = parse_obj(args.src)
    prims = build(V, N, groups, args.scale, args.rotate_y)
    lo = [min(p[k] for pos, _, _ in prims.values() for p in pos) for k in range(3)]
    hi = [max(p[k] for pos, _, _ in prims.values() for p in pos) for k in range(3)]
    for m, (pos, _, ind) in prims.items():
        print(f"  {m}: {len(ind) // 3} triangles")
    print("size (x along front, y up, z depth): " + " x ".join(f"{(hi[k] - lo[k]) * 100:.1f}" for k in range(3)) + " cm")
    if args.list or not args.out:
        return
    overrides = {}
    for spec in args.mat:
        name, val = spec.split("=", 1)
        col, metal, rough = (val.split(":") + ["0", "0.6"])[:3]
        col = col.lstrip("#")
        overrides[name] = ([int(col[i:i + 2], 16) / 255 for i in (0, 2, 4)], float(metal), float(rough))
    t.write_glb(args.out, prims, {}, overrides, Path(args.out).stem, args.copyright)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Convert a native 3ds Max scene (.max, e.g. a CAD / free-model download) to a binary glTF (.glb)
that the 3D viewer can embed (objects[].model in the room YAML).

Usage (from the repo root):
    py -3.11 tools/room3d/max_to_glb.py in.max -o assets/models/name.glb \
        [--scale 0.0254] [--mat mat0=#d9dcdf:0:0.9 ...] [--min-faces 100] [--list]

A .max file is an OLE2 container of gzip streams; this reads only what a viewer needs (needs `pip install olefile`):
  - every "Editable Mesh" object of the `Scene` stream: vertices (chunk 0x914), triangles + smoothing groups +
    material ids (0x912, 20 bytes per face: a, b, c, smoothing group, flags | material_id << 16);
  - the node's Position / Rotation (quaternion) / Scale (chunks 0x96a / 0x96b / 0x96c), applied to its mesh.
    Node parenting (links) is NOT followed: fine for a model whose parts are not linked, check the result in the viewer;
  - NOT read: real material names / colours / textures (a .max keeps them in a format not decoded here). Faces carry only
    a material id, so the materials are called mat<ID> (mat0, mat1, ...): pick colours with --mat, run --list first.
Meshes with fewer than --min-faces faces (helpers, dummy boxes) are skipped.
Axes and the front side are handled like in tds_to_glb.py (Z-up -> Y-up, the -Y side of the model is its front).
--scale: units of the file -> metres (the unit of a .max is not in the part we read: guess from the proportions
 (inches 0.0254, cm 0.01, mm 0.001) and ask the owner for one real dimension).
"""
import argparse
import gzip
import struct
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import tds_to_glb as t  # noqa: E402  (write_glb, build_primitives: shared with the .3ds converter)


def chunks(d, off, end):
    while off + 6 <= end:
        cid, ln = struct.unpack_from("<HI", d, off)
        hdr, cont = 6, bool(ln & 0x80000000)
        ln &= 0x7FFFFFFF
        if ln == 0:
            ln, hdr = struct.unpack_from("<Q", d, off + 6)[0], 14
        if ln < hdr or off + ln > end:
            raise ValueError(f"broken chunk {cid:#x} at {off}")
        yield cid, cont, off + hdr, off + ln
        off += ln


def read_scene(path):
    try:
        import olefile
    except ImportError:
        sys.exit("pip install olefile  (py -3.11 -m pip install olefile)")
    return gzip.decompress(olefile.OleFileIO(str(path)).openstream("Scene").read())


def quat_matrix(q):
    x, y, z, w = q
    return [[1 - 2 * (y * y + z * z), 2 * (x * y + w * z), 2 * (x * z - w * y)],
            [2 * (x * y - w * z), 1 - 2 * (x * x + z * z), 2 * (y * z + w * x)],
            [2 * (x * z + w * y), 2 * (y * z - w * x), 1 - 2 * (x * x + y * y)]]


def parse_max(d):
    """-> list of {"name", "verts", "faces", "groups", "smooth"} in the same shape as tds_to_glb.parse_3ds objects."""
    (_, _, b, e), = list(chunks(d, 0, len(d)))
    meshes, nodes = [], []

    def walk(off, end):
        for cid, cont, bb, ee in chunks(d, off, end):
            if not cont:
                continue
            if cid == 0x8FE:                                    # Editable Mesh data
                m = {}
                for c2, _, b2, e2 in chunks(d, bb, ee):
                    if c2 == 0x914:
                        n = struct.unpack_from("<I", d, b2)[0]
                        m["V"] = [struct.unpack_from("<3f", d, b2 + 4 + 12 * i) for i in range(n)]
                    elif c2 == 0x912:
                        n = struct.unpack_from("<I", d, b2)[0]
                        m["F"] = [struct.unpack_from("<5I", d, b2 + 4 + 20 * i) for i in range(n)]
                if "V" in m and "F" in m:
                    meshes.append(m)
            elif cid == 0x15:                                   # scene node
                nodes.append({c2: d[b2:e2] for c2, _, b2, e2 in chunks(d, bb, ee)})
            walk(bb, ee)

    walk(b, e)
    return meshes, nodes


def to_objects(meshes, nodes, min_faces):
    objs = []
    for i, m in enumerate(meshes):
        if len(m["F"]) < min_faces:
            continue
        node = nodes[i] if i < len(nodes) else {}               # node i holds mesh i (same order in the file)
        name = node.get(0x962, b"").decode("utf-16le") or f"mesh{i}"
        p = struct.unpack("<3f", node[0x96A]) if 0x96A in node else (0, 0, 0)
        q = struct.unpack("<4f", node[0x96B]) if 0x96B in node else (0, 0, 0, 1)
        s = struct.unpack("<3f", node[0x96C][:12]) if 0x96C in node else (1, 1, 1)
        R = quat_matrix(q)
        V = []
        for x, y, z in m["V"]:
            x, y, z = x * s[0], y * s[1], z * s[2]
            V.append((R[0][0] * x + R[1][0] * y + R[2][0] * z + p[0],
                      R[0][1] * x + R[1][1] * y + R[2][1] * z + p[1],
                      R[0][2] * x + R[1][2] * y + R[2][2] * z + p[2]))
        groups = {}
        for fi, f in enumerate(m["F"]):
            groups.setdefault(f"mat{f[4] >> 16}", []).append(fi)
        objs.append({"name": name, "verts": V, "faces": [f[:3] for f in m["F"]],
                     "groups": list(groups.items()), "smooth": [f[3] for f in m["F"]]})
    return objs


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("src", help=".max file")
    ap.add_argument("-o", "--out", help="output .glb")
    ap.add_argument("--scale", type=float, default=1.0, help="multiply coordinates (file units -> metres)")
    ap.add_argument("--mat", action="append", default=[], metavar="mat<ID>=#rrggbb:metal:rough")
    ap.add_argument("--min-faces", type=int, default=100, help="skip meshes with fewer faces (default 100)")
    ap.add_argument("--list", action="store_true", help="only print meshes and material ids")
    ap.add_argument("--copyright", default="")
    args = ap.parse_args()

    meshes, nodes = parse_max(read_scene(args.src))
    objs = to_objects(meshes, nodes, args.min_faces)
    for ob in objs:
        lo = [min(v[k] for v in ob["verts"]) for k in range(3)]
        hi = [max(v[k] for v in ob["verts"]) for k in range(3)]
        print(f"  {ob['name']}: {len(ob['faces'])} faces, material ids "
              + ", ".join(f"{g}={len(ix)}" for g, ix in sorted(ob["groups"]))
              + "; bbox (file units) x %.2f..%.2f  y %.2f..%.2f  z %.2f..%.2f" % (lo[0], hi[0], lo[1], hi[1], lo[2], hi[2]))
    if args.list or not args.out:
        return

    overrides = {}
    for spec in args.mat:
        name, val = spec.split("=", 1)
        col, metal, rough = (val.split(":") + ["0", "0.6"])[:3]
        col = col.lstrip("#")
        overrides[name] = ([int(col[i:i + 2], 16) / 255 for i in (0, 2, 4)], float(metal), float(rough))
    prims = t.build_primitives(objs, args.scale)
    gltf = t.write_glb(args.out, prims, {}, overrides, Path(args.out).stem, args.copyright)
    lo = [min(a["min"][k] for a in gltf["accessors"] if "min" in a) for k in range(3)]
    hi = [max(a["max"][k] for a in gltf["accessors"] if "max" in a) for k in range(3)]
    print(f"wrote {args.out}: {len(objs)} objects, {sum(len(p[2]) // 3 for p in prims.values())} triangles, "
          f"materials {sorted(prims)}")
    print("size (x along front, y up, z depth): " + " x ".join(f"{(hi[k] - lo[k]) * 100:.1f}" for k in range(3))
          + " cm;  bbox min " + str([round(v, 4) for v in lo]) + " max " + str([round(v, 4) for v in hi]))


if __name__ == "__main__":
    main()

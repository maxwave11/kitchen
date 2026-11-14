#!/usr/bin/env python3
"""Stage 0 spike: a copy of the built viewer with three.js r187 + three-gpu-pathtracer (WebGPU) and a «Рендер» button.

The viewer itself is not touched. Usage (from the repo root, after build_room_3d.py):
    py -3.11 tools/room3d/pathtrace-spike/make_test_page.py
writes viewer/pathtrace-test.html (+ viewer/pathtrace-test.js) next to viewer/kitchen-living.html; open
http://localhost:<port>/pathtrace-test.html. Delete the folder and the two files to drop the spike.
"""
import re
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
SRC = ROOT / "viewer" / "kitchen-living.html"
OUT = ROOT / "viewer" / "pathtrace-test.html"

T = "https://cdn.jsdelivr.net/npm/three@0.187.0/"
IMPORTMAP = f"""<script type="importmap">
{{ "imports": {{
  "three": "{T}build/three.module.js",
  "three/webgpu": "{T}build/three.webgpu.js",
  "three/tsl": "{T}build/three.tsl.js",
  "three/addons/": "{T}examples/jsm/",
  "three/examples/jsm/": "{T}examples/jsm/",
  "three-mesh-bvh": "https://cdn.jsdelivr.net/npm/three-mesh-bvh@0.9.18/src/index.js",
  "three-mesh-bvh/webgpu": "https://cdn.jsdelivr.net/npm/three-mesh-bvh@0.9.18/src/webgpu/index.js",
  "three-gpu-pathtracer/webgpu": "https://cdn.jsdelivr.net/npm/three-gpu-pathtracer@0.0.28/src/webgpu/index.js",
  "oidn-webgpu": "https://cdn.jsdelivr.net/npm/oidn-webgpu@0.6.0/dist/oidn.js"
}} }}
</script>"""

# what the render mode needs from inside the viewer's module
HANDLE = """window.__pt = { scene, controls, renderer, wallGroups, daylight, lamps, hemi, sun, MODES, envOf, R, H, LUX, GLASS, lightColor, tick,
  camera: () => camera, mode: () => lightMode, info: () => lightInfo, apply: () => applyMode(), build: () => build() };   // pathtrace spike
window.__ready = true;"""


FIXES = [
    # empty since stage 1: the viewer itself runs three r187 now (the Reflector `this` fix is in viewer_template.html)
]


def main():
    html = SRC.read_text(encoding="utf-8")
    html, n = re.subn(r'<script type="importmap">.*?</script>', lambda m: IMPORTMAP, html, count=1, flags=re.S)
    if n != 1:
        sys.exit("importmap not found in " + str(SRC))
    if html.count("window.__ready = true;") != 1:
        sys.exit("window.__ready not found")
    html = html.replace("window.__ready = true;", HANDLE)
    # extra text fixes for the copy, if a future three.js update needs any before the viewer gets them
    for old, new in FIXES:
        if old not in html:
            sys.exit(f"fix target not found: {old!r}")
        html = html.replace(old, new)
    html = html.replace("</body>", '<script type="module" src="pathtrace-test.js"></script>\n</body>', 1)
    html = re.sub(r"<title>[^<]*</title>", "<title>Рендер (тест трассировки)</title>", html, count=1)
    OUT.write_text(html, encoding="utf-8")
    shutil.copy(HERE / "pathtrace-test.js", ROOT / "viewer" / "pathtrace-test.js")
    print("wrote", OUT)


if __name__ == "__main__":
    main()

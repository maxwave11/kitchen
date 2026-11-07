---
name: kitchen-living-planner
description: End-to-end workflow for Maxim's kitchen-living room - collect measurements (walls, window, two door openings, ceiling), write rooms/kitchen-living.yaml in planhaus format, validate clearances, plan the kitchen run and living zone, and build the interactive 3D model (viewer/kitchen-living.html). Use whenever the user gives room dimensions, asks for a layout, wants to move furniture, or asks to see the room in 3D.
---

# Kitchen-living room planner

Orchestrates the other project skills for one concrete room. Talk to the user in Russian.
All geometry lives in ONE file: `rooms/kitchen-living.yaml` (planhaus room format, cm,
origin = corner A, X = east, Y = north). Everything else (2D plan, 3D model, reviews) is
generated from it. Never keep dimensions only in chat.

Run all commands from the repository root. If `import yaml` or `import matplotlib` fails,
install once: `python3 -m pip install -q -r tools/planhaus/scripts/requirements.txt`.

## 1. Measurements intake

Ask for what is missing, in one message, as a numbered list. Accept rough sketches/photos.

- Room outline: walk the walls clockwise from one corner; for each wall its length (cm) and
  direction (north/east/south/west). Name corners A, B, C... If the room is not rectangular
  (niche, column, bay), each step is its own wall.
- Ceiling height (and any lowered parts: beams, bulkheads).
- Window: which wall, distance from the wall's start corner to the window edge, width,
  sill height from floor, window height. Is there a radiator under it (width, height)?
- Each of the two door openings: wall, distance from corner, width, height, where it
  leads, is there a door leaf, which way it swings (into the room / out) and hinge side.
- Fixed things: water supply and drain, gas pipe or electric hob, ventilation duct / hood
  outlet, radiators, main outlets and switches, electrical panel. Position = wall + distance.
- Program: how many people eat daily / for guests, sofa or not, TV, desk, island wish,
  fridge type (built-in / freestanding, width), dishwasher, oven in tall unit or under hob.
- Official area from the floor plan if known (used to validate the outline).

If the user gives only overall dimensions, write a rectangle and mark unknowns as TODO in
`notes:` rather than guessing.

## 2. Write and validate the room

1. If `rooms/kitchen-living.yaml` does not exist, copy `tools/planhaus/templates/rooms/_template.yaml`
   there (and `tools/planhaus/templates/CLAUDE.md` rules are already summarised in the repo
   `CLAUDE.md`). Fill `walls`, `windows`, `openings`, `ceiling_height`, `plumbing`, `heating`,
   `outlets`. Use `openings:` for doorways, `windows:` for glazing (balcony door = window
   with `type: balcony-door`).
2. 3D-only optional fields (read by the 3D builder, ignored by the rules engine):
   `wall_thickness`, window `sill_height` / `height`, opening `height` / `swing: in|out` /
   `hinge: start|end`, built-in `height` / `elevation` / `color` / `countertop` /
   `upper: {depth, height, elevation}`, furniture `color` / `elevation`.
3. Validate geometry: `python3 tools/planhaus/scripts/room_spatial.py rooms/kitchen-living.yaml --check`
   — the trace must close and the area must match the official one within 5%. On mismatch,
   ask the user to re-measure; do not fudge lengths.
4. Show a first 3D of the empty shell (step 5) so the user can confirm walls/openings
   before any furniture.

## 3. Plan the layout (planhaus phases)

Follow the phase order from `CLAUDE.md`: `/planhaus-brief` (short, combine with intake) →
`/planhaus-concept` → `/planhaus-zone` → `/planhaus-furnish` → `/planhaus-light` →
`/planhaus-review`. Use `spatial-layout-guide` for standard furniture sizes.

Kitchen-specific rules to apply while zoning and furnishing:

- Kitchen run as `built_ins` along walls (one entry per straight run; corner = two
  entries). Base depth 60 cm, worktop 90-92 cm high (adjust to user height: elbow - 10-15),
  upper cabinets 30-35 cm deep starting 55-65 cm above the worktop.
- Wet zone first: sink as close to the drain/riser as possible (gravity: drain slope
  ~2%, so long sink-to-riser runs raise the floor or need a pump - flag it).
- Work triangle fridge - sink - hob: each leg 120-270 cm, total 400-800 cm; nothing tall
  between legs. Order along the run: fridge → landing → sink → main prep (≥ 60-90 cm) →
  hob → landing (≥ 30-40 cm). Hob not under a window, not next to a door, not in a corner
  (≥ 30 cm to tall unit or wall). Dishwasher next to the sink.
- Aisles: KIT-01 from the rules engine (counter to opposite counter/island); island at
  least 90 cm all round, 120 cm when two cooks.
- Doors: no door swing into the working aisle or onto the fridge door (DOOR-01); keep
  the route between the two doorways clear (declare it in `circulation:` with CIRC-01).
- Window: keep the WIN-01 approach; a sink under the window is fine, a tall unit is not.
- Living part: sofa backs onto a wall or acts as the divider facing away from the kitchen;
  TV distance TV-01; dining table between kitchen and sofa with DIN-01/DIN-02 clearances.
- Hood over hob, duct route to the ventilation outlet - note the length/bends in `notes:`.

When two layouts are both defensible (L vs U, island vs peninsula, where the sofa goes),
produce 2-3 alternatives as separate files `rooms/kitchen-living.<variant>.yaml`, build a
3D for each, and let the user choose. Keep `rooms/kitchen-living.yaml` as the chosen one.

After every change run `--check`, fix ERRORs (revise zones, not offsets), mention WARNs.

## 4. 2D plan

`python3 tools/planhaus/scripts/room_spatial.py rooms/kitchen-living.yaml --plot rooms/kitchen-living-floorplan.png`
then read the PNG and critique it (see `/planhaus-render`).

## 5. 3D model

`python3 tools/room3d/build_room_3d.py rooms/kitchen-living.yaml -o viewer/kitchen-living.html`

The output is one HTML file (three.js from cdn.jsdelivr.net, orbit controls, wall cutaway,
top view, zones and labels). To check it visually in a session without CDN access, see
`tools/room3d/README.md`. Deliver it to the user as an Artifact (publish the HTML) and also
commit it, so it can be opened from the repository. To change the viewer itself, edit
`tools/room3d/viewer_template.html` (use the `threejs-*` skills) and rebuild.

## 6. Deliver

Commit `rooms/`, `viewer/` and plan PNGs on the working branch, push, and give the user:
the 3D link, the 2D plan, the list of rule check results (ERROR/WARN in plain Russian), and
open questions. Keep a short changelog of layout decisions in `rooms/kitchen-living.yaml`
`notes:` so later threads know why things are where they are.

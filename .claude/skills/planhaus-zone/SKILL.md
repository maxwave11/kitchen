---
name: planhaus-zone
description: Zone a room before any furniture exists — inventory fixed features, pick ONE focal point, map unblockable door-to-door circulation routes, then assign functional zones with bounds. Use when planning where functions go in a room, or before /planhaus-furnish on a room without zones.
argument-hint: "<room-name>"
allowed-tools: Bash(python3:*)
---

# Zone the Room (Phase 3 — Zoning & Circulation)

Decide where functions live before any furniture is placed. NO furniture placement here.

**Reads**: `concept.yaml` (room_hierarchy + this room's `design:` block), `apartment.yaml` (adjacencies), `rooms/<room>.yaml`.
**Writes**: `focal_point:`, `circulation:`, `zones:` (optionally `sightlines:`) into `rooms/<room>.yaml`.
**Back-edge**: if no zoning satisfies circulation, the room's function list is overloaded — question the program, not the rule. Go back to `/planhaus-concept` (room_hierarchy, per-room goals) and renegotiate what this room hosts. Never shrink a circulation rule to make a zone fit.

## Steps

### 1. Inventory fixed features

```bash
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room>.yaml --json
```

List every fixed feature with coordinates: openings (+ door swings), windows (note which are
operable / balcony doors), outlets, plumbing, heating, built-ins. These are immovable;
everything else negotiates around them. Geometry must validate (trace closes, area matches) —
if not, fix geometry before zoning.

### 2. Pick ONE focal point

Candidates: a window with a view, fireplace, feature wall, the longest uninterrupted wall, an
architectural quirk. Choose exactly one and commit:

```yaml
focal_point:
  ref: balcony-door            # feature/item id
  why: "Only long view in the apartment; the seating zone orients to it."
```

### 3. Circulation FIRST (unblockable)

Map door-to-door routes between every pair of openings, plus approach to balcony doors and
operable windows. Write them before zones — zones get what's left:

```yaml
circulation:
  - id: entry-balcony
    from: hall-entry           # opening/window id
    to: balcony-door
    rule: CIRC-01              # main door-to-door route; CIRC-02 for secondary paths
```

Widths live in the rules engine — cite CIRC-01/CIRC-02, don't restate numbers.

### 4. Assign functional zones

Consider 2–3 zoning alternatives (use the `planhaus-space-planner` subagent if available).
Each zone:

```yaml
zones:
  - id: seating
    purpose: "Conversation + evening reading for 4"
    anchor: sofa               # intended anchor item — may not exist yet
    bounds: { x: [0, 300], y: [200, 490] }    # axis-aligned approx, cm
    lighting: [ambient, accent]
```

Size zones by function, not by leftover space:
- Conversation: all seats within easy talking distance of each other (SEAT-02) + circulation
  around the perimeter
- Dining: table + chair pull-out envelope (DIN-01) + DIN-02 on any side a route passes behind
- Sleeping: bed + per-side clearance (BED-01/02)
- Work: desk + chair push-back, near outlets, daylight without screen glare

Justify the chosen alternative against four criteria, one sentence each: **daylight** (which
zone earns the window), **quiet** (adjacencies from apartment.yaml — what's behind each wall),
**adjacency logic** (dining near the kitchen opening), and the **focal point** (the primary
zone faces it).

### 5. Validate

Write the fields into the room YAML, then:

```bash
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room>.yaml --check
```

The tool checks zone bounds, declared route widths (CIRC-02), and door-pair corridors
(CIRC-01). With no furniture yet this mostly confirms the routes exist; the real test comes
in `/planhaus-furnish`.

## Notes

- `zones:` / `focal_point:` / `circulation:` are optional-but-recommended fields — old rooms
  without them still validate (`--check` reports SKIP for absent data), but `/planhaus-furnish`
  needs them and will send you back here.
- Do NOT place any furniture in this phase; the `anchor:` field names an intent, not a position.
- End: suggest `/planhaus-furnish <room>`.

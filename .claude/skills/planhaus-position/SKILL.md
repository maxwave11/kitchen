---
name: planhaus-position
description: Query spatial positions, edge-to-edge gaps, and the full distance matrix for a room; interpret distances against the clearance rules
argument-hint: "<room-name> [--gap id1 id2] [--matrix]"
when_to_use: When you need exact coordinates or distances — checking a gap before placing a piece, fitting something into a slot, or interpreting clearances against the rule table.
allowed-tools: Bash(python3:*)
---

# Position / Distances

Query spatial positions and distances between items in a room.

## Modes

### Default: All positions
```bash
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room-name>.yaml
```
Shows absolute (x, y) coordinates for all items, plus footprint summary.

### Gap between two items (`--gap`)
```bash
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room-name>.yaml --gap <item1> <item2>
```
Shows edge-to-edge distance between two specific items. Both items need dimensions.

### Full distance matrix (`--matrix`)
```bash
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room-name>.yaml --matrix
```
Shows all pairwise edge-to-edge distances between furniture/built-ins, plus distances to walls. Sorted by distance (closest first).

### Rules check (`--check`) and machine output (`--json`)
```bash
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room-name>.yaml --check
```
Runs the clearance rules engine (findings as `SEVERITY RULE-ID: detail`). Add `--json` to any
mode for machine-readable output (positions, warnings, rule results) — use it when feeding
results into further computation.

## Interpreting distances

Don't eyeball numbers — cite rule IDs from `scripts/rules/clearances.yaml`, the single source
of truth for clearance values. The ones you'll use most:

- **CIRC-01** — main circulation route between openings: ideal 90 cm
- **CIRC-02** — secondary path between furniture pieces: ideal 75 cm
- **60 cm** is the hard floor below which both become ERRORs

For seating gaps, dining pull-out, bed clearance etc., run `--check` and let the engine apply
the matching rule (SEAT-01, DIN-01, BED-01, …) instead of judging raw matrix numbers yourself.

## Notes

- Coordinates: origin (0,0) at SW corner, X=East, Y=North, units=cm.
- Edge-to-edge = gap between closest edges of bounding boxes (not center-to-center).
- Items without dimensions (lights, outlets) appear in positions but not in gap/matrix.

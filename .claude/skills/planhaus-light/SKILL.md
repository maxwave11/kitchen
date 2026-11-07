---
name: planhaus-light
description: 3-layer lighting plan per zone — ambient, task, and accent with numeric lumen targets, one color temperature from the concept, pendant geometry per LIGHT-01, and outlet checks. Use when planning lighting, positioning lamps or fixtures, or when a furnished room has no lighting plan.
argument-hint: "<room-name>"
allowed-tools: Bash(python3:*)
---

# Lighting Plan (Phase 6 — Lighting)

Layer light per zone: ambient + task + accent, dimensioned in lumens, one color temperature.

**Reads**: `rooms/<room>.yaml` (zones, focal_point, furniture, outlets, ceiling_height), `concept.yaml` (`lighting.philosophy`, `color_temp_k`, `layers_required`).
**Writes**: `lighting:` items in `rooms/<room>.yaml`, each with `layer:`, `color_temp_k:`, `lumens:`, `why:` (plus position/mount/fixture per the room template).
**Back-edge**: if a zone can't receive a required task layer (no outlet in reach, no ceiling point over the table), the layout is wrong — return to `/planhaus-furnish` (move the desk to the outlet wall, shift the table under the ceiling point) or record an electrical work item. Do not skip the layer.

## Steps

### 1. Read inputs

```bash
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room>.yaml --json
```

Take `color_temp_k` and the philosophy from `concept.yaml`. If `concept.yaml` is missing (old
project), default to 2700K and recommend `/planhaus-concept`. If `zones:` are missing, treat
the room as one zone but recommend `/planhaus-zone`.

### 2. Three layers per zone

- **ambient** — every zone. General fill: ceiling fixtures, large floor lamps bounced off
  walls/ceiling.
- **task** — wherever the zone's activities need it: reading seats, desks, dining tables,
  kitchen counters, bedside.
- **accent** — on the focal point (`focal_point.ref`) and at most 1–2 other moments (art,
  plant, shelf). Accent without contrast is just more ambient.

### 3. Numeric targets

- Ambient: ~215 lm/m² of zone area (a whole living room lands around 1500–3000 lm total).
- Task: ~320 lm/m² over dining tables and counters; ~540 lm/m² at desks and reading spots.
- Accent: ≈3× the surrounding ambient level on the highlighted object — less reads as nothing.
- Color temperature: ONE value from the concept (2700–3000K residential). Never mix
  temperatures in one room.

Sum your fixtures' lumens per zone and layer, and show the math against these targets.

### 4. Geometry & power

- Pendants over tables: cite LIGHT-01 and set `hang_height_cm` so `--check` can verify it;
  center the pendant on the table, not on the room. `hang_height_cm` = the pendant's
  BOTTOM above the finished floor (cm); LIGHT-01 derives the table clearance by
  subtracting the table height (e.g. 155cm over a 74cm table → 81cm clearance).
- Floor/table lamps: set `uses_outlet: <outlet-id>`; confirm from the positions output that
  the outlet exists nearby and the cord doesn't cross a circulation route. No outlet near →
  back-edge (see above).
- Glare: no bare task source in the sightline from the main seat to the TV or focal point.

### 5. Switching

Layers must be independently switchable. Note groupings in the room `notes:` (e.g. "ambient on
dimmer; accent picture light on its own switch") — the evening scene is ambient low + task off
+ accent on.

### 6. Validate & render

```bash
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room>.yaml --check
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room>.yaml --plot rooms/<room>-floorplan.png
```

### Example item

```yaml
lighting:
  - id: dining-pendant
    position: { wall: [C-A, A-B], offset: [150, 200] }
    mount: pendant
    hang_height_cm: 155          # pendant bottom above floor → ~80cm above a 74–76cm table top
    layer: task
    color_temp_k: 2700
    lumens: 1200
    fixture: null                # open slot for /planhaus-select
    why: "Task layer over the dining table; a warm pool that defines the zone after dark."
```

## Notes

- `layer:` / `color_temp_k:` / `lumens:` are optional-but-recommended fields — old projects
  without them still validate (`--check` reports SKIP where data is absent). Add them on
  everything YOU write.
- Fixtures not yet chosen are slots for `/planhaus-select` (category pendant / floor_lamp /
  table_lamp); put the lumen and temperature targets into the slot brief.
- End: suggest `/planhaus-select` for fixture slots, then `/planhaus-review` once all rooms are lit.

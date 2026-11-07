# Casa Sol — Sample Project

A demo project for planhaus. Fictional young couple designing a ~60m² Mediterranean apartment in Málaga.

## Quick Reference

- **Brief**: `brief.yaml` — warm modern, mid-range, budget total 12 000 EUR
- **Concept**: `concept.yaml` — Mediterranean-warm: 60-30-10 palette, material master list, 2700K 3-layer lighting, budget allocation (anchor 60 / supporting 25 / accent 15), room hierarchy
- **Layout**: `apartment.yaml` — living + bedroom + minimal entry hall (adjacency map)
- **Rooms**: `rooms/living-room.yaml` (L-shaped, 6-wall trace), `rooms/bedroom.yaml`
- **Registry**: `registry/furniture/` — 10 items with extended schema

## Room YAML features demonstrated

- `zones:` / `focal_point:` / `sightlines:` blocks in both rooms; `circulation:` routes in
  the living room (the single-opening bedroom declares an explicit empty list)
- `type:` (controlled vocab) + `zone:` on every furniture item
- `layer:` / `color_temp_k:` / `lumens:` on lighting (and `hang_height_cm` on the pendant)
- Honest `validation:` block — the living room's L-shape closes and matches 25.2 m² exactly
- Accepted WARNs documented as trade-offs in each room's `notes:`

Registry items carry the extended schema: `category`, `style: [tags]`,
`palette_role`, `visual_weight`, `currency`, `mass`, plus `seat_height`
(seating) and `lumens`/`color_temp_k` (lighting). Descriptions are objective —
design reasoning lives in `concept.yaml` and the room `why:` fields.

## Commands

```
/planhaus:validate living-room        # geometry + rules engine
/planhaus:render living-room          # floorplan PNG + visual critique
/planhaus:position living-room --matrix
/planhaus:review apartment
```

Raw CLI (from the plugin repo root):

```bash
python3 scripts/room_spatial.py sample-project/rooms/living-room.yaml --check
python3 scripts/room_spatial.py sample-project/rooms/living-room.yaml --matrix
python3 scripts/room_spatial.py sample-project/rooms/living-room.yaml --plot sample-project/rooms/living-room-floorplan.png
```

Both rooms pass `--check` with zero ERRORs (exit code 0). The remaining WARN
(PROP-02 coffee table) and the deliberate `SKIP TV-01: no seating oriented
toward tv` are documented as trade-offs in the room notes.

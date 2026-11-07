---
name: planhaus-furnish
description: Place furniture anchor-first inside the room's zones — orient anchors to the focal point, run the clearance checker after every batch, then render and critique. Use when the user wants to place, arrange, move, or lay out furniture in a room.
when_to_use: After /planhaus-zone has written zones/circulation/focal_point for the room. For arranging or rearranging furniture — not for picking products (/planhaus-select) or pure geometry checks (/planhaus-validate).
argument-hint: "<room-name>"
allowed-tools: Bash(python3:*)
---

# Furnish the Room (Phase 4 — Layout)

Place furniture inside the zone map, anchor-first, with the rules engine as referee.

**Reads**: `rooms/<room>.yaml` (zones, focal_point, circulation), `concept.yaml`, `registry/` (shortlisted/purchased/installed items).
**Writes**: `furniture:` items in `rooms/<room>.yaml` — each with `type:`, `zone:`, `why:`.
**Back-edge**: if a clearance ERROR cannot be fixed by moving items within their zone, the zone map is wrong — return to `/planhaus-zone` and revise bounds or zone count. Never shrink a clearance, never silently accept an ERROR.

## Steps

### 1. Preconditions

Read the room YAML. If `zones:` / `circulation:` / `focal_point:` are missing, stop and run
`/planhaus-zone` first — placing furniture without a zone map is how layouts rot. Read
`concept.yaml` (style signals, palette roles) and the registry for real dimensions.

### 2. Anchor first

Work zones in importance order. In each zone, place the **anchor** first (sofa / bed / dining
table): oriented to the focal point (or to the zone's purpose where the focal point belongs to
another zone), proportioned to its wall per PROP-01 (cite the rule — the engine knows the numbers).

```yaml
- id: main-sofa
  registry: registry/sofas/xyz.yaml   # or inline dimensions for placeholders
  type: sofa                          # controlled vocab — see Notes
  zone: seating
  position: { wall: [B-F, A-B], offset: [80, 300] }
  facing: west
  why: "Anchors the seating zone facing the balcony focal point; carries the secondary palette role (oat boucle)."
```

The `why:` must cite design reasoning — focal point, concept signal, palette role, zone
purpose. "Placed 80cm from the east wall" is a coordinate, not a why.

### 3. Secondary pieces

Coffee table (SEAT-01, PROP-02), side tables, extra seats (SEAT-02 spacing), media (TV-01
viewing distance), rugs (RUG-01/RUG-02), storage. Cite rule IDs in your reasoning; don't
restate their numbers.

When two placements both seem defensible, delegate to the `planhaus-space-planner`
subagent: it produces 2–3 genuinely different layout alternatives, scores them against the
rules, and recommends one with trade-offs.

### 4. Check after EVERY placement batch

```bash
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room>.yaml --check
```

- **ERROR** → non-negotiable. Fix by moving/reorienting within the zone. If no position in the
  zone satisfies the rule → back-edge to `/planhaus-zone` and revise the zone map. Never
  resolve an ERROR by deciding the rule doesn't apply.
- **WARN** → designer's judgment. Fix it, or record the accepted trade-off with one sentence
  in the room `notes:`.
- **SKIP** → the tool lacks data (dims, types, heights); add the data if the check matters.

### 5. Render and critique

```bash
python3 "tools/planhaus/scripts/room_spatial.py" rooms/<room>.yaml --plot rooms/<room>-floorplan.png
```

Read the PNG and critique it as a designer, in writing: Is the focal point honored or blocked?
Is visual weight balanced, or does one corner sag? Is there negative space, or is every wall
lined? Do the circulation routes read as open on the plan? Fix, re-check, re-render.

### 6. Open slots

Items the layout needs but the registry lacks: place a placeholder with realistic dimensions
(`type:`, `zone:`, `why:` + a note "placeholder — pending selection") and list them at the end
as slots for `/planhaus-select`.

## Notes

- `type:` controlled vocab: sofa, armchair, coffee-table, side-table, dining-table,
  dining-chair, desk, desk-chair, bed, nightstand, wardrobe, dresser, bookshelf, tv, rug,
  floor-lamp, table-lamp, pendant, plant, kitchen, island, other.
- `type:` and `zone:` are optional fields (old rooms fall back to id-keyword sniffing and still
  validate) but required on everything YOU place — the rules engine targets checks by type.
- Items needing power (TV, lamps): set `uses_outlet: <outlet-id>` and verify the outlet is near.
- End: suggest `/planhaus-select` for the open slots, then `/planhaus-light <room>`.

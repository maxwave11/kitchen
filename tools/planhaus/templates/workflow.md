# Design Process

Nine phases, in order. Each produces a checkable artifact; on hard failure you loop back
one phase (the back-edge) — never patch forward.

| # | Phase | Skill | Artifact | Back-edge (on failure) |
|---|-------|-------|----------|------------------------|
| 0 | Scaffold & setup | `/planhaus-new-project`, `/planhaus-setup` | project skeleton, deps | — |
| 1 | Programming | `/planhaus-brief` + measurement (below) | `brief.yaml` (numeric budget total), validated room geometry | re-measure: area mismatch = wrong shape |
| 2 | Concept | `/planhaus-concept` | `concept.yaml` + per-room `design:` blocks | back to brief: unanswered intake questions |
| 3 | Zoning | `/planhaus-zone` | `zones:` + `focal_point:` in room YAML | back to concept: room can't serve its program |
| 4 | Circulation | `/planhaus-zone` | `circulation:` routes (CIRC-01/02) in room YAML | back to zoning: routes don't fit between zones |
| 5 | Layout | `/planhaus-furnish` | furniture placed inside zones, `--check` clean | back to zoning: hard clearance ERROR → revise the zone map, not the offset |
| 6 | FF&E selection | `/planhaus-select` | registry entries per slot (gated + scored top-3) | back to layout: nothing fits the slot envelope |
| 7 | Lighting | `/planhaus-light` | per-zone 3-layer lighting plan in room YAML | back to layout: no surface/outlet for a needed layer |
| 8 | Review | `/planhaus-review` | checklist report (pass/warn/fail + evidence, rule IDs) | back to the failing phase |

Support skills run at any phase: `/planhaus-validate`, `/planhaus-render`, `/planhaus-position`
(facts + rule IDs), and `/planhaus-search` / `/planhaus-add-item` / `/planhaus-enrich-catalog`
(catalog & registry utilities).

The rest of this file is the **measurement part of phase 1** — collecting and validating
the geometry that everything else depends on.

---

# Data Collection

## Phase 1: From Plans (Remote)

- Official room areas (m²) - ground truth
- All wall dimensions (identify which wall each belongs to)
- Room shapes (draw ASCII)
- Door/window positions
- Room adjacencies - which rooms share walls

## Phase 2: On-Site

- Outlets (position, type, height)
- Switches
- Door swing directions
- Radiators, plumbing
- Verify dimensions that were unclear in plans

---

## Floor Plan Validation

### The Problem

LLMs see `4.90` and `3.40` and assume rectangle. But the room might be L-shaped!

### The Fix

1. **Draw first** - ASCII diagram with labeled corners (A, B, C...)
2. **Map dimensions to walls** - each measurement belongs to a wall
3. **Define walls** - direction (east/north/west/south) + length
4. **Trace closes?** - last wall must return to origin
5. **Area matches?** - calculated from walls ≈ official (±5%)

```yaml
# Example: L-shaped living room
ascii: |
  E──────────F
  │  Living  │
  D          │
  │──C       │
     │Kitchen│
     A───────B

walls:
  - id: A-B
    direction: east
    length: 340
  - id: B-F
    direction: north
    length: 651
  # ... continue around perimeter

validation:
  trace_closes: true
  calculated_area: 27.79
  area_difference_pct: 0
  area_matches: true
```

---

## Time Estimates

| Size | Plans | On-site |
|------|-------|---------|
| 1+kk | 30min | 1-2h |
| 2+kk | 1h | 2-3h |
| 3+kk | 1-2h | 3-4h |

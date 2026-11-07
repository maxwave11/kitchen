# planhaus

Interior-design copilot plugin for Claude Desktop / Cowork / Claude Code.

planhaus makes the agent reason like a professional interior designer: it follows the
real design process instead of jumping straight to furniture placement, validates every
layout against a cited clearance rules engine, and selects furniture with multi-criteria
judgment rather than embedding similarity. Everything is driven by YAML specs and Python
tools — facts come from tools, judgment from the agent.

## The design process

```
brief ──► concept ──► zone ──► furnish ──► select ──► light ──► review
(intake)  (style,     (zones,  (layout in  (FF&E per  (3-layer  (adversarial
           palette,    focal    zones,      slot:      plan per   critique vs
           budget      point,   rules-      gates +    zone)      checklist)
           tiers)      routes)  checked)    scores)
```

Each phase produces a checkable artifact and loops back one phase on hard failure —
a failed clearance check revises the zone map, not just an offset. Furniture is never
placed before zones and circulation routes exist; FF&E is never selected before the
layout fixes dimensions.

## Install

In Claude Code / Cowork:

```
/plugin marketplace add pepuscz/planhaus
/plugin install planhaus
```

Or for local development: `claude --plugin-dir .`

## Quick start

1. `/planhaus:new-project my-apartment` — scaffold a project from templates
2. `/planhaus:brief` — guided client intake → `brief.yaml` (incl. numeric budget)
3. Measure rooms (see `workflow.md` in your project) and validate geometry: `/planhaus:validate living-room`
4. `/planhaus:concept` — research-driven design concept → `concept.yaml`
5. `/planhaus:zone living-room` — zones, focal point, circulation routes
6. `/planhaus:furnish living-room` — anchor-first layout, validated against the rules engine
7. `/planhaus:select living-room` — multi-criteria furniture selection per slot
8. `/planhaus:light living-room` — ambient/task/accent lighting plan
9. `/planhaus:review apartment` — adversarial design review

## Skills (16)

| Skill | Phase | Purpose |
|-------|-------|---------|
| `/planhaus:new-project` | 0 | Scaffold from templates (brief, concept, rooms, registry) |
| `/planhaus:setup` | 0 | Install optional catalog dependencies |
| `/planhaus:brief` | 1 Programming | Guided client intake interview → `brief.yaml` |
| `/planhaus:concept` | 2 Concept | Brief → researched concept: style signals, 60-30-10 palette, budget tiers |
| `/planhaus:zone` | 3 Zoning | Fixed-feature inventory, focal point, zones + circulation routes |
| `/planhaus:furnish` | 4 Layout | Anchor-first placement inside zones, validate/render loop |
| `/planhaus:select` | 5 FF&E | Multi-criteria furniture selection: gates → scored top-3 per slot |
| `/planhaus:light` | 6 Lighting | 3-layer lighting plan per zone with numeric targets |
| `/planhaus:validate` | any | Geometry + rules engine, findings cite rule IDs |
| `/planhaus:render` | any | Floorplan PNG + mandatory visual critique |
| `/planhaus:position` | any | Position / gap / distance-matrix queries |
| `/planhaus:review` | 7 Review | Forks a design-reviewer agent over the integration checklist |
| `/planhaus:search` | util | Direct catalog queries (full filter set) |
| `/planhaus:add-item` | util | Add a product to the registry (objective specs only) |
| `/planhaus:enrich-catalog` | util | LLM style/metadata enrichment of the catalog DB |
| `/planhaus:migrate` | util | Upgrade a pre-1.0 project: refresh docs, upgrade schemas, derive concept/zones, triage rule findings |

## Agents

| Agent | Role |
|-------|------|
| `design-researcher` | Researches client references and style direction on the web; returns style vocabulary, concrete signals, palette candidates, avoid-list |
| `space-planner` | Generates 2–3 zoning/layout alternatives, iterates with the spatial tool, scores against circulation/seating rules, recommends one with trade-offs |
| `furniture-curator` | Applies the selection rubric (hard gates → weighted scores → per-criterion justification) over catalog candidates; returns top-3 per slot |
| `design-reviewer` | Adversarial critic: re-runs validation, reads floorplans, checks every checklist item with pass/warn/fail + evidence |

## Rules engine

Numeric design rules (circulation widths, seating gaps, dining clearances, bed access,
TV distance, door swings, proportions, rug rules…) live in one canonical table:
`scripts/rules/clearances.yaml`. Each rule has an ID (`CIRC-01`, `SEAT-01`, `DIN-02`, …),
a `min` (below = **ERROR**) and an `ideal` (below = **WARN**), and a published source.

`room_spatial.py --check` applies the table to a room and reports findings as
`SEVERITY RULE-ID: detail` — e.g. `ERROR CIRC-01: hall-entry→balcony-door corridor 52cm < 60cm
(main route, ideal 90cm)`. Missing data is never an error: skipped checks are listed as
`SKIP RULE-ID: what's missing`. Skills and agents cite rule IDs instead of restating numbers,
so there is exactly one place where the numbers live.

A `PostToolUse` hook auto-runs the check whenever a `rooms/*.yaml` file is edited:
ERRORs block and prompt the agent to fix them; WARNs surface as context.

## Catalog & multi-criteria selection (optional)

The plugin ships catalog tooling but no product data — build your own DB from crawled
catalogs, then point the plugin at it (`catalog_db_path` plugin setting, or `CATALOG_DB_PATH`).
`build` reads `{CRAWL4AI_DIR}/<retailer>_catalog/catalog_llm.json` for the supported
retailers (sweeek, kavehome, zarahome):

```bash
pip install -r scripts/catalog/requirements.txt
CRAWL4AI_DIR=/path/to/crawls python scripts/catalog/catalog_vectordb.py build   # --force to rebuild
```

Search is semantic (embeddings) plus hard filters: price, dimensions, category, style,
color family, material, rating, source. Selection (`/planhaus:select`) goes further:

1. **Slot brief** — function, max footprint from the zone + clearance envelope, style
   vocabulary from the concept, palette role, budget line (anchor 60% / supporting 25% /
   accent 15% tiers), ergonomic band.
2. **Hard gates** — category, fit, clearances, price ≤ 1.2× line, ergonomics. Eliminate, don't score.
3. **Weighted scores** — proportion 25, style coherence 25, material/palette 20,
   ergonomics 10, quality signals 10, budget fit 10 — each with a one-line justification.
4. **Output** — top 3 per slot with per-criterion scores and one trade-off sentence each.
   Embedding similarity is never presented as a quality score.

## Upgrading from 0.x

Existing projects keep working without changes — all new fields are optional, and the
tools report missing data as `SKIP`, never as an error. To actually adopt the 1.0
workflow, run `/planhaus:migrate <project>`: it backs up the project, refreshes the
stale injected docs, upgrades schemas, then **derives** the concept and zones your
existing layout implies and triages what the rules engine finds (move-to-fix vs
documented known issue vs accepted trade-off). A v1 catalog DB needs one
`catalog_vectordb.py build --force`.

## Sample project

Open `sample-project/` ("Casa Sol") for a complete worked example: brief, concept,
two zoned rooms with circulation routes, 10 registry items, and rendered floorplans.
It passes its own validation — use it to try every skill.

## How it works

- **Rooms** are YAML: wall geometry (direction + length, trace must close), zones,
  circulation routes, furniture with wall-relative positions and explicit orientation.
- **Registry** items describe products objectively (dimensions, materials, price) — the
  WHY lives in room YAML and `concept.yaml`.
- **`scripts/room_spatial.py`** computes coordinates, detects collisions, runs the rules
  engine, and renders floorplan PNGs.
- **Design doctrine** (phase discipline, 60-30-10, validation rules) is injected into each
  project via its `CLAUDE.md`.

## License

MIT

# planhaus 1.0 — Architecture

planhaus is a Claude Desktop / Claude Code native plugin that makes the agent reason like a
professional interior designer. Version 1.0 restructures the plugin around the professional
design process (programming → concept → zoning → circulation → layout → FF&E selection →
lighting → review) instead of jumping straight to furniture placement.

This document is the **single source of truth** for schemas, rule IDs, skill responsibilities,
and conventions. Skills cite rule IDs from `scripts/rules/clearances.yaml`; they do not restate
numbers. Subjective judgment (style scoring, visual critique) lives in skill prose; numeric
checks live in the rules engine.

## Design principles

1. **Phase discipline.** Never place furniture before zones and circulation routes exist in the
   room YAML. Never select FF&E before the layout fixes dimensions. Each phase produces a
   checkable artifact and loops back one phase on hard failure (a failed clearance check revises
   the zone map, not just an offset).
2. **Research before deciding.** The concept phase researches the client's references and style
   direction; the selection phase expands queries from design intent, never from raw user
   keywords; candidates are judged per-criterion, not by embedding similarity alone.
3. **Facts from tools, judgment from the agent.** `room_spatial.py` and the catalog MCP server
   supply measurements and candidates; skills supply rubrics the agent applies with justification.
4. **Tolerate old projects.** All new YAML fields are optional. Scripts skip checks when data is
   absent and say so ("zones: not specified — run /planhaus:zone"). No hard version gate.

## Component map

```
planhaus/
├── .claude-plugin/plugin.json     # v1.0.0 manifest + userConfig (catalog_db_path)
├── .mcp.json                      # planhaus-catalog MCP server (host-side)
├── hooks/
│   ├── hooks.json                 # documented nested schema; SessionStart + PostToolUse
│   └── on_room_edit.py            # auto-validate rooms/*.yaml after Write|Edit
├── agents/                        # plugin subagents
│   ├── design-researcher.md       # style/reference research (web)
│   ├── space-planner.md           # zoning + layout alternatives
│   ├── furniture-curator.md       # gate+score candidate evaluation
│   └── design-reviewer.md         # adversarial design critique
├── skills/                        # 16 skills (see table)
├── scripts/
│   ├── room_spatial.py            # + argparse, --json, --check rules engine
│   ├── rules/clearances.yaml      # canonical, cited, severity-tiered rules
│   └── catalog/                   # + enriched metadata, filters, enrich CLI
├── templates/                     # + concept.yaml; upgraded room/registry templates
└── sample-project/                # Casa Sol — exemplary, passes its own validation
```

## Skills (16)

| Skill | Phase | New? | Responsibility |
|---|---|---|---|
| `new-project` | 0 | upgraded | Scaffold from templates (now includes concept.yaml) |
| `setup` | 0 | kept | Install optional catalog deps |
| `brief` | 1 Programming | **new** | Guided client intake interview → `brief.yaml` (incl. numeric `budget.total`) |
| `concept` | 2 Concept | **new** | Research-driven translation of brief → `concept.yaml` + per-room `design:` blocks |
| `zone` | 3 Zoning | **new** | Fixed-feature inventory, focal point, zones + circulation routes → room YAML |
| `furnish` | 4 Layout | **new** | Anchor-first placement inside zones, validate/render loop, cites rule IDs |
| `select` | 5 FF&E | **new** | Multi-criteria furniture selection: slot brief → query expansion → gates → scored top-3 |
| `light` | 6 Lighting | **new** | 3-layer lighting plan per zone with numeric targets |
| `validate` | any | upgraded | Geometry + rules engine (`--check --json`), reports rule IDs |
| `render` | any | upgraded | Floorplan PNG + **mandatory visual critique** (focal point, balance, negative space) |
| `position` | any | upgraded | Position/gap/matrix queries; cites rule IDs (no hardcoded numbers) |
| `review` | 7 Review | upgraded | Forks into `design-reviewer` agent; numeric checklist thresholds |
| `search` | util | upgraded | Thin catalog access manual (full filter set); points to `select` for design work |
| `add-item` | util | upgraded | Registry entry with extended schema (category, style tags, palette_role…) |
| `enrich-catalog` | util | **new** | LLM style/metadata enrichment of catalog DB via export/import CLI |
| `migrate` | util | **new** | Upgrade a pre-1.0 project: refresh injected docs, upgrade schemas, derive concept/zones retroactively, triage rule findings |

### Frontmatter conventions (all skills)

- `name`, `description` (capability + trigger phrasing for model invocation)
- `when_to_use` on validate/render/position/review/search/select/furnish
- `argument-hint` replaces the undocumented `args:` key everywhere
- `allowed-tools` pre-approvals: `Bash(python3:*)` for spatial skills,
  `mcp__planhaus-catalog__catalog_search`, `mcp__planhaus-catalog__catalog_stats`,
  `mcp__planhaus-catalog__catalog_get` for catalog skills
- `disable-model-invocation: true` on `new-project` and `setup` (user-triggered only)
- `review` uses `context: fork` + `agent: planhaus:design-reviewer`
- Reference scripts via `${CLAUDE_PLUGIN_ROOT}` (quoted in shell commands: `"${CLAUDE_PLUGIN_ROOT}"`)

## Subagents (`agents/*.md`)

Frontmatter per plugin spec: `name`, `description` (with "use proactively when…" phrasing),
`tools` (allowlist), `model: inherit`. Plugin agents ignore `hooks`/`mcpServers`/`permissionMode`.

| Agent | Tools | Role |
|---|---|---|
| `design-researcher` | WebSearch, WebFetch, Read, Glob | Researches client references/style; returns style vocabulary, signal list (leg styles, materials, lines, era), palette candidates, avoid-list. Used by `concept`. |
| `space-planner` | Read, Glob, Grep, Bash, Write, Edit | Generates 2–3 zoning/layout alternatives, runs spatial tool iteratively, scores against CIRC/SEAT/DIN rules, recommends one with trade-offs. Used by `zone`/`furnish`. |
| `furniture-curator` | Read, Glob, Grep, Bash + catalog MCP tools | Applies the selection rubric (gates → weighted scores → per-criterion justification) over candidates; returns top-3 comparison per slot. Used by `select`. |
| `design-reviewer` | Read, Glob, Grep, Bash | Adversarial critic: re-runs validation, reads floorplan PNGs, checks every checklist item with pass/warn/fail + evidence, cites rule IDs. Used by `review` (fork target). |

## Rules engine

### `scripts/rules/clearances.yaml` — canonical rule table

Format per rule:

```yaml
- id: CIRC-01
  name: "Main circulation route"
  applies: circulation            # circulation | pair | item | room | proportion
  min_cm: 60                      # below min → ERROR
  ideal_cm: 90                    # below ideal → WARN
  source: "Lifetime Homes 900mm; Karlen, Space Planning Basics"
```

**Adjudicated canonical numbers** (these exact values; severity: below `min` = ERROR, between
`min` and `ideal` = WARN, ranges violated = WARN unless noted):

| ID | Rule | min | ideal | Notes |
|---|---|---|---|---|
| CIRC-01 | Main circulation route (between openings) | 60 | 90 | widest free corridor between each door pair |
| CIRC-02 | Secondary path between furniture pieces | 60 | 75 | applies to declared `circulation:` routes |
| SEAT-01 | Sofa/armchair ↔ coffee table gap | 30 | 35–46 (range) | >50 WARN "out of reach" |
| SEAT-02 | Conversation seats max spacing | — | ≤300 | seat-to-seat in same zone; >360 ERROR |
| DIN-01 | Dining table edge → obstruction (seated side) | 75 | 90 | pull-out only |
| DIN-02 | Dining table edge → obstruction (circulation side) | 90 | 122 | when a route passes behind chairs |
| BED-01 | Bed side clearance (each used side) | 60 | 75 | queen ideal 76, king ideal 91 |
| BED-02 | Bed foot clearance (if passage) | 60 | 90 | |
| TV-01 | TV viewing distance vs diagonal | 1.0× | 1.2–2.5× (range) | 4K default; needs `screen_diagonal_in` on the TV item |
| KIT-01 | Kitchen work aisle (counter-facing) | 91 | 107 | |
| DOOR-01 | Door swing arc clear | — | — | `has_door: true` openings, radius = width, both hinges tried; ERROR when both swings blocked, WARN when one (hinge side undeclared) |
| WIN-01 | Access to operable windows/balcony doors | 60 | 75 | clear approach in front |
| HEAT-01 | Radiator not blocked | 15 | 30 | WARN only |
| LIGHT-01 | Pendant above table surface | 76 | 76–91 (range) | only if `hang_height_cm` given |
| PROP-01 | Sofa length vs its wall | 50% | 60–75% (range) | >85% WARN "wall overloaded" |
| PROP-02 | Coffee table vs sofa length | 40% | 55–75% (range) | |
| RUG-01 | Living rug bare-floor border to walls | 20 | 30–60 (range) | only if rug has dimensions |
| RUG-02 | Dining rug extends beyond table | 50 | 61 | chairs stay on rug |
| ZONE-01 | Zone bounds contain member bboxes | — | tolerance 10 | WARN-only; overflow beyond tolerance |
| SIGHT-01 | Focal point visible from openings | — | blocker height 75 | WARN-only; tall items interrupt the sightline |
| GEOM-01 | Geometry validity | — | — | collisions / out-of-bounds from the base validator, surfaced as ERROR findings under `--check` |

### `room_spatial.py` upgrades

- `argparse` CLI (keep all existing flags working: positional yaml, `--view x,y [--facing d]`,
  `--gap a b`, `--matrix`, `--plot [out]`), add `--check` (run rules engine) and `--json`
  (machine-readable output of positions, warnings, rule results).
- Item **type detection**: explicit `type:` field on furniture/built-ins (controlled vocab:
  `sofa, armchair, coffee-table, side-table, dining-table, dining-chair, desk, desk-chair, bed,
  nightstand, wardrobe, dresser, bookshelf, tv, rug, floor-lamp, table-lamp, pendant, plant,
  kitchen, island, other`), fallback to id-keyword sniffing (current behavior).
- Rule engine consumes `clearances.yaml` (resolve path relative to the script:
  `Path(__file__).parent / "rules" / "clearances.yaml"`), applies rules by type pattern using
  existing primitives (`bbox_to_bbox_distance`, `segment_to_segment_distance`).
- New checks: pairwise clearances (SEAT/DIN/BED/KIT), door-swing arcs (DOOR-01: quarter-circle
  polygon vs bboxes via SAT/sampling), window access (WIN-01), TV distance (TV-01, between TV bbox
  and the nearest seat of type sofa/armchair facing it), proportions (PROP-01/02), rug rules,
  and **corridor analysis** (CIRC-01): rasterize the room at 5 cm, mark furniture/built-in bboxes
  (floor-standing only) as obstacles, and for each pair of openings binary-search the largest
  clearance radius for which a path exists (BFS on eroded free space). Report per-pair widths.
- Zone/circulation awareness: if `zones:`/`circulation:`/`focal_point:` present — check zone
  bounds contain their members' bboxes (WARN), check each declared route's achieved width
  (CIRC-02), check sightline from openings to `focal_point.ref` is not blocked by items taller
  than 75 cm (needs `height` from dims; skip if unknown).
- Output convention for findings: `ERROR CIRC-01: hall-entry→balcony-door corridor 52cm < 60cm
  (main route, ideal 90cm)` — always `SEVERITY RULE-ID: detail`.
- Missing data is never an error: report `SKIP <RULE-ID>: <what's missing>` in a "skipped checks"
  section so the agent knows what it can't see.

## Catalog upgrades

### Metadata (flat, filterable; written by normalizers at build time)

`width_cm, depth_cm, height_cm` (parse sweeek `specifications`, kavehome `details`, zarahome
description text; set `dims_estimated: true` when inferred from text), `category` (controlled:
`sofa, armchair, dining_table, dining_chair, coffee_table, side_table, bed, nightstand, wardrobe,
dresser, bookshelf, rug, floor_lamp, table_lamp, pendant, mirror, decor, outdoor, other` — mapped
from breadcrumbs/collection/name keywords), `primary_material` (oak, walnut, pine, rattan, metal,
glass, boucle, linen, velvet, leather, marble, ceramic, other), `color_family` (white, cream,
beige, grey, charcoal, black, brown, natural_wood, green, blue, terracotta, pink, yellow,
multicolor), `style` (empty until enriched; controlled: scandinavian, midcentury, modern,
industrial, rustic, traditional, coastal, japandi, mediterranean, bohemian, eclectic),
`seat_height_cm` (seating only, nullable), plus existing `source, name, price, rating, url,
colors` (JSON string) and `full_product` (JSON string, kept).

- Collection created with `metadata={"hnsw:space": "cosine"}`; report similarity as cosine.
  Stamp `db_version: 2` in a `db_meta.json` inside the DB dir; `query()` warns when the stamp is
  missing/old ("rebuild with: python catalog_vectordb.py build --force").
- `query()` filters: `source, max_price, min_price, min_rating, category, style, color_family,
  material, max_width, max_depth, max_height` (chromadb `$and` of `$eq/$lte/$gte`); plus
  over-fetch (`n*3` candidates) and Python-side post-filtering where metadata is missing
  (missing dims pass dimension filters but get flagged `dims_unknown`).
- New `enrich` CLI: `catalog_vectordb.py enrich export --missing style --out pending.jsonl`
  (id, name, category, description excerpt) and `enrich import --in enriched.jsonl` (id → style,
  optionally color_family/primary_material overrides; updates metadata in place, no re-embedding).

### MCP server (`mcp_server.py`)

- `catalog_search`: mirror the full filter set above; `db_path` becomes **optional** — resolution
  order: explicit param → `CATALOG_DB_PATH` env (set via `.mcp.json` from
  `${user_config.catalog_db_path}`) → `./catalog_vector_db` under cwd. Clear JSON error listing
  the resolution attempts when not found.
- New `catalog_get(ids: list[str])`: returns full product data for shortlisted ids (so the
  curator judges from rich data without re-querying).
- `catalog_stats`: add price ranges + category/color facets.
- `_ensure_deps` stays (Cowork hook execution context is unverified) but must fail fast with a
  clear JSON error if pip fails, not hang.

## Selection rubric (encoded in `select` skill + `furniture-curator` agent)

**Slot brief** (built from room YAML + concept.yaml before any query): function/category, max
footprint from the zone + clearance envelope (via `room_spatial.py --check`), style vocabulary
(from concept), palette role (dominant/secondary/accent + color families), budget line, ergonomic
band (e.g. sofa seat height 43–48, dining seat 45–50 under 71–76 table).

**Budget lines** derived as: room budget × tier share / items in tier, with tiers
**anchor 60% / supporting 25% / accent 15%** (anchor: sofa, bed, dining table; supporting:
coffee table, chairs, rugs, lighting, storage; accent: decor, cushions, plants).

**Stage 1 — hard gates** (eliminate, don't score): category matches; footprint fits zone AND
leaves rule-table clearances; price ≤ 1.2× budget line (1.0–1.2× flagged "stretch");
ergonomic bounds for seating.

**Stage 2 — weighted scores** (0–100, per-criterion one-line justification required):
proportion & dimensional fit **25** (2/3-rule targets vs wall/adjacent pieces), style coherence
**25** (signal-level: legs, materials, lines, era; adjacent styles per compatibility map score
partial — e.g. scandinavian≈japandi≈midcentury), material & palette fit **20** (color family
correct for the slot's 60-30-10 role = 12; material repeats an existing room material = 8),
ergonomics **10**, quality/construction signals **10** (kiln-dried hardwood, 8-way hand-tied,
HD foam, solid wood), budget fit **10** (peak at 0.8–1.0× line; taper to 0 at 1.2×; mild penalty
< 0.5× for anchor slots).

**Output**: top 3 per slot in a comparison table with per-criterion scores, total, and one
trade-off sentence each. Shuffle candidate order before judging (position-bias mitigation).
Never present embedding similarity as a quality score.

## Project format additions (all optional — tolerate-missing)

### `concept.yaml` (project root; written by `/planhaus:concept`)

```yaml
# DESIGN CONCEPT — the designer's translation of the brief. One per project.
narrative: ""                  # 2-3 sentences: the story of this home
style:
  primary: ""                  # controlled vocab (see catalog `style`)
  secondary: []
  signals: []                  # concrete: "tapered light-wood legs", "curved lines", "linen + boucle"
  avoid: []                    # from brief HATE + research
palette:                       # 60-30-10 with explicit role assignment
  dominant:   { share: 60, colors: [], materials: [], applications: "" }
  secondary:  { share: 30, colors: [], materials: [], applications: "" }
  accent:     { share: 10, colors: [], materials: [], applications: "" }
materials: []                  # 3-5 master list, each: {name, role, rooms}
lighting:
  philosophy: ""
  color_temp_k: 2700           # consistent across rooms (2700-3000 residential)
  layers_required: [ambient, task, accent]
budget:
  total: 0
  currency: EUR
  allocation: { anchor: 60, supporting: 25, accent: 15 }   # % per tier
  rooms: {}                    # room-id: amount
room_hierarchy: []             # ordered, most important first, each: {room, emphasis, why}
references: []                 # researched: {url, takeaway}
```

### Room YAML additions

```yaml
zones:                         # written by /planhaus:zone, BEFORE furniture
  - id: seating
    purpose: ""
    anchor: sofa               # item id (may not exist yet at zoning time — name the intended anchor)
    bounds: { x: [0, 300], y: [200, 490] }    # axis-aligned approx, cm
    lighting: [ambient, accent]
focal_point:
  ref: balcony-door            # feature/item id
  why: ""
circulation:                   # door-to-door routes that must stay clear
  - id: entry-balcony
    from: hall-entry           # opening/window id
    to: balcony-door
    rule: CIRC-01              # which rule applies (CIRC-01 main, CIRC-02 secondary)
sightlines:
  - from: hall-entry
    toward: focal_point
    keep_clear: true
# furniture items gain: type (controlled vocab), zone (zone id). `why:` stays required.
# lighting items gain: layer: ambient|task|accent, color_temp_k, lumens (all optional).
```

### Registry item additions (`templates/registry/_template.yaml`)

`category` (controlled vocab as catalog), `style: []` (tags), `palette_role:
dominant|secondary|accent`, `visual_weight: light|medium|heavy`, `mass:` (kg), `seat_height:`
(seating), `lumens:`/`color_temp_k:` (lighting), `currency:` next to numeric `price:`,
`rejected_reason:` (for status: rejected). Descriptions stay objective (WHAT, not WHY).

## Hooks (`hooks/hooks.json` — documented nested schema)

```json
{
  "hooks": {
    "SessionStart": [
      { "hooks": [
        { "type": "command", "command": "<core deps check/install, quoted vars>",
          "statusMessage": "Checking planhaus core dependencies" },
        { "type": "command", "command": "<mcp deps stamp pattern, quoted vars>",
          "statusMessage": "Preparing catalog search dependencies" }
      ]}
    ],
    "PostToolUse": [
      { "matcher": "Write|Edit",
        "hooks": [ { "type": "command",
          "command": "python3 \"${CLAUDE_PLUGIN_ROOT}/hooks/on_room_edit.py\"" } ] }
    ]
  }
}
```

`on_room_edit.py`: reads stdin JSON; if `tool_input.file_path` matches `rooms/*.y(a)ml` and the
file exists, runs `room_spatial.py <file> --check --json`, then: geometry/collision **ERRORs** →
stdout JSON `{"decision": "block", "reason": "<findings>"}` (PostToolUse "block" prompts Claude
to address it); WARNs only → `{"hookSpecificOutput": {"hookEventName": "PostToolUse",
"additionalContext": "<findings>"}}`. **Any exception (missing yaml lib, bad stdin, script
failure) → exit 0 silently** — the hook must never break editing, and must be safe whether it
executes on host (no pyyaml) or in the Cowork VM.

## plugin.json (v1.0.0)

`name, version: "1.0.0", displayName: "planhaus", description, author {name}, license, homepage,
repository, keywords`, and `userConfig`:

```json
"userConfig": {
  "catalog_db_path": {
    "type": "string", "title": "Catalog database path", "required": false,
    "description": "Absolute path to your catalog_vector_db/ directory (host). Leave empty if you don't use catalog search."
  }
}
```

`.mcp.json` gains `"CATALOG_DB_PATH": "${user_config.catalog_db_path}"` in env.

## Sample project (Casa Sol) — must be exemplary

- Model the living room's real L-shape (6 walls) so `area_matches: true` — the framework's own
  STOP rule must pass in its flagship example.
- Add `concept.yaml`, `zones/circulation/focal_point` to both rooms, `type:`/`zone:` on furniture,
  `layer:` on lighting; resolve the `to: hall` opening (model the hall in apartment.yaml or
  re-point it).
- Strip design reasoning from registry descriptions (e.g. sofa "works as 60% element" → move to
  concept.yaml); add new registry fields to all 10 items.
- Regenerate floorplan PNGs; `--check` must produce zero ERRORs (document any WARNs as accepted
  trade-offs in room notes).

## Migration (0.x → 1.0)

Old projects keep working untouched — that is the tolerance principle above. Beyond
tolerance, `/planhaus:migrate` provides the guided scenario, modeled on the Casa Sol
rebuild. It is **re-thinking, not re-formatting**:

1. **Inventory & mode** — detect 0.x markers; classify the project as *paper* (nothing
   bought → full re-think allowed) or *furnished home* (purchased/installed items →
   derive, don't redesign; moves are free, replacements are flagged costs). Back up first.
2. **Refresh injected docs** — the project's CLAUDE.md / design-checklist.yaml /
   workflow.md were copied at scaffold time and carry pre-1.0 doctrine (hardcoded
   clearance numbers, no phase discipline). Replace if unedited, merge if edited — never
   drop user text.
3. **Mechanical schema upgrade** — brief `budget:` prose → `{total, currency, notes}`;
   registry `category`/`currency`/`style` list; `type:` on furniture; `screen_diagonal_in`
   / `hang_height_cm` from real product data (turns SKIPs into checks).
4. **Re-think** — derive `concept.yaml` and per-room zones/focal point/circulation from
   the *existing* layout and purchases (reverse-engineering mode: contradictions between
   brief and reality are findings for the user, not things to paper over); then run
   `--check` and triage: fixable-by-moving → propose the move; baked-into-a-purchase →
   documented known issue with remediation cost; WARN → accept-with-note or fix.
5. **Report** — backup location, doc/schema changes, derived concept, findings triage
   table, next steps.

The catalog DB migrates separately: incremental `build` refuses to stamp v2 over a v1
database and instructs `build --force`; the MCP tools return rebuild warnings/errors when
they detect a v1 stamp.

## Versioning & release

- This release: **1.0.0** (project format additions + new workflow contract).
- Release checklist additions: `claude plugin validate . --strict`, run `--check` on
  sample-project rooms, smoke-test in Cowork (hooks fire, MCP tools appear, forked review runs).
- CHANGELOG.md maintained from this release on.

## Known runtime caveats (test in Cowork before merging to main)

1. Hook execution context (host vs VM) in Cowork is not officially documented — `on_room_edit.py`
   and both SessionStart commands are written to degrade silently wherever they run.
2. Plugin `agents/` + `context: fork` support in Cowork is documented for Claude Code; verify the
   forked `review` works in Cowork, else it falls back to inline instructions (the skill body
   must stand alone).
3. `userConfig` prompting in Cowork unverified — the MCP server's db_path fallback chain covers it.

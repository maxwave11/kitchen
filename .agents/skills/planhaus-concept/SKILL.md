---
name: planhaus-concept
description: Research-driven design concept — analyze the client's references and style direction, then write concept.yaml (style signals, 60-30-10 palette, materials, lighting philosophy, numeric budget allocation) plus per-room design goals. Use after the brief is complete, or when the user asks for a style direction, moodboard, or design concept.
argument-hint: "[project-dir]"
---

# Design Concept (Phase 2 — Concept)

Translate the brief into the project's design contract: `concept.yaml`. Research first, decide second.

**Reads**: `brief.yaml`, `apartment.yaml` (room list + adjacencies), existing `rooms/*.yaml`.
**Writes**: `concept.yaml` (project root) + a `design:` block (goal + objectives) in each room YAML.
**Back-edge**: if `brief.yaml` is missing or lacks mood, LOVE/HATE, or a numeric `budget.total`, stop and run `/planhaus-brief` — never invent client preferences. (Old projects may have a free-text `budget:` block — ask the client for the number rather than guessing.)

## Steps

### 1. Research (do not skip)

Launch the `planhaus-design-researcher` subagent with: the brief's reference URLs, mood
adjectives, and LOVE/HATE lists. If subagents are unavailable, do the same research inline
with web search/fetch.

The deliverable is **concrete style signals, not a style label**:
- leg styles (tapered, hairpin, plinth, turned), line quality (curved vs. rectilinear),
  materials and finishes, era references, palette candidates with named colors
- if the client named a style you can't define precisely (e.g. "japandi", "wabi-sabi"),
  research what actually defines it before using the word
- an avoid-list derived from the HATEs plus research (e.g. "glossy lacquer", "chrome + cool white")
- per reference URL: one takeaway sentence — what specifically to borrow

### 2. Write concept.yaml

Exactly this schema (every downstream skill reads these paths):

```yaml
narrative: ""                  # 2-3 sentences: the story of this home
style:
  primary: ""                  # controlled vocab: scandinavian, midcentury, modern, industrial, rustic, traditional, coastal, japandi, mediterranean, bohemian, eclectic
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
  color_temp_k: 2700           # one value for the whole home (2700-3000 residential)
  layers_required: [ambient, task, accent]
budget:
  total: 0                     # = brief budget.total
  currency: EUR
  allocation: { anchor: 60, supporting: 25, accent: 15 }   # % per tier
  rooms: {}                    # room-id: amount — must sum to total
  statement_pieces: []         # splurge exceptions: {item, room, amount} — excluded from tier-line math
room_hierarchy: []             # ordered, most important first, each: {room, emphasis, why}
references: []                 # researched: {url, takeaway}
```

While filling it:
- Palette roles are assignments, not suggestions: dominant = walls/floors/large anchor surfaces;
  secondary = upholstery, large textiles, secondary furniture; accent = decor, art, one bold piece.
- Budget: copy the total from the brief; split per room weighted by `room_hierarchy` and the
  brief's splurge/save list. The 60/25/15 tiers (anchor/supporting/accent) are how
  `/planhaus-select` later derives per-item budget lines — keep them numeric.
- If the brief names splurge items ("statement pendant"), encode each as a
  `statement_pieces` entry with its own amount — otherwise the tier math caps it at a
  save-tier line and the splurge silently never happens.
- `room_hierarchy` decides where the money and statement pieces go; `emphasis` says what kind
  of moment each room gets.

### 3. Per-room design blocks

For each room YAML, write `design:` — `goal` (1 sentence) + `objectives` (5–10 bullets), each
grounded in the concept (cite a signal, a palette role, or the room's hierarchy emphasis —
not generic advice).

### 4. Client sign-off

Present the concept as a narrative: story, palette with roles, style signals, avoid-list,
lighting philosophy, budget split per room. Ask for explicit sign-off and record adjustments
before moving on.

## Notes

- `concept.yaml` is the contract: zone, furnish, select, light, and review all cite it.
  Changing it mid-project means re-checking every downstream decision (zone purposes, furniture
  `why:`s, selections, lighting temps) — say this to the client when presenting.
- All concept fields are optional for old projects: skills that find no `concept.yaml` fall back
  to `brief.yaml` but should recommend running `/planhaus-concept`.
- End: suggest `/planhaus-zone <most-important-room>` per the hierarchy.

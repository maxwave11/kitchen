---
name: planhaus-add-item
description: Add a product to the project registry from a URL, a /planhaus-select pick, or a description
argument-hint: "<url-or-description>"
allowed-tools: WebFetch, mcp__planhaus-catalog__catalog_get
---

# Add Item to Registry

Register a product as a candidate in `registry/`. All new fields below are optional —
old registry entries without them stay valid.

## Steps

1. Gather the data, depending on the source:
   - **URL provided**: fetch the product page with **WebFetch** (it runs host-side).
     Do **NOT** use `curl`/`wget` in Bash — the Cowork VM blocks arbitrary egress.
     Extract: name, price + currency, dimensions (W × D × H cm), materials, colors, finish.
   - **From `/planhaus-select`**: carry over the catalog metadata from the picked
     candidate (category, style tags, color_family, primary_material, dimensions, price,
     url, image urls) — use `catalog_get` if you only have the id. Set
     `status: shortlisted` (the user already chose it over alternatives).
   - **Text description**: use it as the basis; ask the user for missing critical info
     (dimensions, price).

2. Save the main product image to `registry/<folder>/<item-name>.jpg` when the
   environment allows downloads; otherwise record the image URL in the `image:` field.

3. Create `registry/<folder>/<item-name>.yaml` (folders are broad buckets:
   `furniture/`, `lighting/`, `accessories/`, `textiles/`, …):

   ```yaml
   name: "<Product Name>"
   url: "<source URL>"
   price: <number>            # numeric only
   currency: EUR

   status: considering        # considering | shortlisted | rejected | purchased | installed
   rejected_reason: ""        # only when status: rejected

   category: ""               # controlled vocab (same as catalog): sofa, armchair,
                              # dining_table, dining_chair, coffee_table, side_table, bed,
                              # nightstand, wardrobe, dresser, bookshelf, rug, floor_lamp,
                              # table_lamp, pendant, mirror, decor, outdoor, other

   dimensions:
     width: <cm>
     depth: <cm>
     height: <cm>
   mass:                      # kg, if known
   seat_height:               # cm — seating only
   lumens:                    # lighting only
   color_temp_k:              # lighting only

   materials: [<list>]
   colors: [<list>]
   finish: "<finish>"
   style: []                  # tags, controlled vocab: scandinavian, midcentury, modern,
                              # industrial, rustic, traditional, coastal, japandi,
                              # mediterranean, bohemian, eclectic
   palette_role:              # dominant | secondary | accent (60-30-10 role)
   visual_weight:             # light | medium | heavy

   description: |
     <Objective description of form, proportions, visual weight,
      texture, materials, craftsmanship. NO recommendations.>

   image: "<folder>/<item-name>.jpg"

   notes: |
     <date>: Discovered at <source>
   ```

4. Default `status: considering` — the designer evaluates fit later. The lifecycle is
   unchanged: `considering → shortlisted → rejected | purchased → installed`. When
   rejecting, keep the entry and fill `rejected_reason:`.

## Notes

- Registry entries describe **WHAT the item IS**, not where it goes or why.
- Keep descriptions objective: form, proportions, visual weight, texture, materials,
  craftsmanship. Design reasoning ("works as the 60% element") belongs in `concept.yaml`
  and room YAML, never here.
- Do NOT include: certifications, load capacity, assembly instructions, delivery info.
- `palette_role` and `visual_weight` are the designer's classification of the item itself
  (what role it CAN play), not a placement decision.

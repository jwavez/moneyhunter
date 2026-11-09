# Detail-slot allocation decision (Task 7)

## Decision

**Option B refined** — keep `detail_limit_per_scan = 4`. Allocate those four getItem slots with category rotation across the primary lanes, exclude fragrance from the primary rotation, and prefer near-publish identities inside each primary category.

This is **not** Option C (raising the per-scan cap). Option C is deferred until Task 13 measures a week of `total_getitem_used` against the shared daily pool.

## Why Option B refined

Task 6 showed tools identities (for example DGA452Z) can starve when early slots go to a single category or to fragrance/watchlist traffic, even though tools/trainers/tech all want lookups in the same scan. Raising the cap without measuring quota headroom would burn the shared Browse budget. Fair rotation at the existing 4-slot cap fixes cross-category starvation without weakening publication gates.

## Allocation rules (implemented)

1. **Demanding** = exact identity AND not `not_risky_lowest` / `inspect_skip` AND not already served by a fresh cache hit. Cache reuse is free and does not consume a slot. Enrich dedup before allocation is unchanged.
2. **Primary rotation** = `tools → trainers → tech` (repeat). Fragrance is excluded from primary rotation.
3. **Phase 1 (near-publish priority):** within each primary category, identities that already have a viable research model and are missing only the detail check (`detail_check_pending`) are ordered first; remaining identities keep existing order.
4. **Floors, not maxima:** `tool_slots_reserved = 2` and `non_tool_slot_cap = 2` are **minimum floors inside the 4-slot cap**. Implementation grants up to 2 tools and up to 2 trainers+tech (trainers/tech round-robin) first, then continues `tools → trainers → tech` round-robin for any remaining slots. Either floor can therefore be exceeded within the 4-slot cap when the other side has no demand.
5. **Phase 3 leftover:** any slots still free after all primary-rotation demand is served go to fragrance in existing order. Other categories (`lego` / `gaming` / `other`), if they ever demand, are treated the same as fragrance leftovers (no separate reservation existed in prior code).
6. Caps unchanged: `detail_limit_per_scan = 4`; shared daily Browse budget remains 800.

## Shared daily pool (getItem vs Browse search)

`research_budget.reserve(state, when, purpose)` increments one shared `browse_usage.calls` counter with `DAILY_LIMIT = 800`.

Both of the following call that same reserve:

- Browse **item_summary/search** paths (asking enrich lanes, watchlist refresh, discovery acquisition) with purposes such as `asking-tools`, `asking-affordable`, `asking-watch`, `persistent-research`, `acquisition`.
- Browse **getItem** detail checks with purpose `item-details`.

So getItem and Browse searches **do share** the 800/day pool in the actual code. Task 13 must measure combined `total_getitem_used` / `browse_usage.calls` before any cap raise.

## Diagnostic label fixes shipped with this decision

- `supported_estimate_value` → `research_model_value`; add `publication_estimate_value` (non-null only when publication-qualified).
- Split `exact_item_details_unverified` into `detail_check_pending` (no getItem / awaiting budget / cache pending) and `detail_check_failed` (getItem ran, check failed). Both remain non-publishing.
- Per-category `requested` → `wanted`; add `considered`; separate `denied_not_risky_lowest`; `slot_summary` gains `total_wanted` / `total_granted`.

## Roadmap honesty

| Task | What | Status |
|------|------|--------|
| 7 | Rotation + labels + tests | this change |
| 8 | DGA452Z `detail_check_failed` once it gets a slot | next |
| 9 | Cache TTL starvation review | later |
| 10–11 | Trainers / tech identity lane expansion | later |
| 12 | P3 sold-evidence verification | later |
| 13 | Measure daily getItem usage; reconsider cap 5 (Option C) | deferred |

Do not treat this document as permission to raise `detail_limit_per_scan` or the 800/day cap, or to weaken publication gates.

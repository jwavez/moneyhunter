# Task 15 — Unpriced Discord delivery audit

**Date:** 2026-11-09 (Europe/London)  
**Verdict: Scenario A — no leak. No code change.**

## Part A

Traced the post-scan offer inventory from `origin/state` (`deals.json` review queue + deals, 228–231 unique URLs). Every unpriced / none / approximate row classified to **`internal-hold`** with **`would_deliver=false`**.

| estimate_type | count | Discord destination |
| --- | ---: | --- |
| exact (publication.allowed) | 6 | held (LEGO `publishable()` image gate) |
| approximate (model, not publication-qualified) | 22 | internal-hold |
| unpriced / none | 200+ | internal-hold |
| **leaks** | **0** | — |

Full compact per-offer log: `docs/task15_partA_unpriced_trace.json`.

### Python scan path

- `hub.route` filters to `publishable(r) and publication.allowed(r)` before any channel send.
- `discord.build_payload` is the final serializer gate (`valid_proof` required).
- `hub.digest` filters near-misses with `publication.allowed`.
- Regression already present: `tests.test_evidence_routing.EvidenceRouting.test_unpriced_all_paths_held_without_name_policy_or_ack`.

### Worker interactive path (ephemeral “Only you can see this”)

Code read + existing worker tests:

- `filterDeals` / `dealView` / `researchView` require `priced()`.
- `policyView` / `planView` / `priceView` return `pending()` when unpriced.
- `guardData` replaces invalid product embeds with `pending()`.
- Worker test: `unpriced or expired calculation cannot become a named target card`.

Dead code after `return pending()` in `priceView` still contains a legacy `"Not priced: uncertain match"` string but is **unreachable**.

### Why the user still sees “not priced” cards

Guide §12 / Task 7: existing alerts are not deleted when formatting/gates change. Cards posted **before** Task 7 remain in Discord history. New cards from the current gates do not ship unpriced product embeds.

Options: delete/archive old channel messages manually; ignore history.

## Part B

**No leaks → no code change.** No new regression tests added (existing coverage sufficient).

## Part C

See `docs/task15_partC_scan_report.txt`. Zero unpriced in opportunities / research-watch / category-hot / trending / price-drops / price-errors / fast-movers / digest / near-misses. `seen.json` unchanged under dry-run/no-publish semantics.

Temporary `MH_TASK15_TRACE` hub instrumentation was used offline for classification then **reverted** (Scenario A).

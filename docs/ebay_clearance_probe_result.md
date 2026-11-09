# eBay Browse Currys clearance probe — Task 14 Phase B

**Date:** 2026-11-09 (Europe/London)  
**Scope:** Read-only probe. Exactly **5** Browse `item_summary/search` calls. No acquisition lane. No Awin signup. No paid services. No pipeline changes.  
**Artifact:** `/workspace/ebay_clearance_probe.json` (Actions run [42645009603](https://github.com/jwavez/moneyhunter/actions/runs/42645009603))  
**Script:** `scripts/ebay_clearance_probe.py` (not wired into scans)  
**Runner:** `.github/workflows/ebay-clearance-probe.yml` (`workflow_dispatch`)

---

## Step 0 — GitHub Actions usage (read-only)

| Check | Result |
| --- | --- |
| Repo visibility | **PUBLIC** (`gh repo view jwavez/moneyhunter --json visibility`) |
| `gh api user/settings/billing/actions` | **404 Not Found** (could not read) |
| `gh api /users/jwavez/settings/billing/usage` | **404** / needs `user` scope (`gh auth refresh -h github.com -s user`) |
| Org billing Actions | **404** (no `jwavez` org billing endpoint for this token) |
| Included / used Actions minutes (billing UI numbers) | **Could not read** — API permissions insufficient |
| Public-repo minutes policy | On **standard GitHub-hosted runners**, public repos **do not consume** Actions minutes. This repo is public → **£0 Actions** for `ubuntu-latest` scans under current GitHub policy. |

### moneyhunter-scan wall-clock this billing month (Nov 2026, from Actions runs API)

Measured via `gh api repos/jwavez/moneyhunter/actions/runs?created=>=2026-11-01` (timing = `updated_at - run_started_at`):

| Metric | Value |
| --- | --- |
| `moneyhunter-scan` runs fetched (1–9 Nov) | 167 |
| Completed with duration | 166 |
| Average duration | **~17.9 minutes** (median ~30.7 min — skewed by long tails / waits) |
| Sum of run durations | **~2,971 minutes** wall-clock |
| Runs/day (days with ≥1 run) | **~20.9 / day** average across 8 active days (range 3–54; spike 7–9 Nov) |

**Interpretation:** Wall-clock minutes look large, but because the repo is **public**, they should **not** bill against the private free-tier minute pool. Billing dollar figures were **not** readable with current `gh` scopes — treat “£0 Actions” as policy-based, not invoice-confirmed.

---

## Method

1. Locked **five queries before any Browse call** (no cherry-picking, no re-runs for nicer stats).
2. Marketplace `EBAY_GB`. Shared filter on every call:
   - `sellers:{currys}`
   - `conditionIds:{1000}` (NEW)
   - `buyingOptions:{FIXED_PRICE}`
   - `deliveryCountry:GB`
   - `priceCurrency:GBP`
   - `limit=200`
3. Each call gated with `research_budget.reserve(state, when, "clearance-probe")` against an **in-memory** copy of `browse_usage` seeded from `origin/state:scan_state.json` (probe does **not** write the state branch).
4. Recorded per item (when present): `itemId`, `title`, `price`, `marketingPrice.originalPrice` / `discountPercentage` / `discountAmount`, `condition`, seller username, `itemWebUrl`, brand/mpn/gtin.

### Queries (locked before run)

| # | Lane | `q` / `category_ids` | Rationale |
| --- | --- | --- | --- |
| 1 | broad-electronics | `category_ids=293` (Consumer Electronics), no `q` | Broad top-level electronics; category satisfies Browse search without free-text |
| 2 | headphones-audio | `q=headphones` | moneyhunter audio/tech lane |
| 3 | gaming | `q=playstation` | moneyhunter gaming lane |
| 4 | computing-laptops | `q=laptop` | computing/tech lane |
| 5 | small-appliances-home-tech | `q=air fryer` | small appliances / home tech |

### Seller username (decided from public sources before run)

- Public store pages: [currys](https://www.ebay.co.uk/usr/currys) (main) and [currys_clearance](https://www.ebay.co.uk/str/currysclearance) (outlet / refurbished).
- Probe used **`sellers:{currys}`** as specified for NEW listings.
- **Did not** call `currys_clearance` (would need additional Browse budget).

---

## Summary numbers

From `/workspace/ebay_clearance_probe.json` → `summary`:

| Field | Value |
| --- | --- |
| `calls_used` | **5** |
| `items_returned` | **0** |
| `unique_items` | **0** |
| `items_with_marketingPrice` | **0** |
| `items_discount_ge_40` | **0** |
| `items_discount_ge_25` | **0** |
| discount pct min / median / max | n/a (n=0) |
| identity-field share | n/a (no items) |
| budget before (seeded) | **425 / 800** used → **375** remaining |
| budget after (in-memory reserve) | **430 / 800** used → **370** remaining |

All five queries: `reserved=true`, `http_ok=true`, `total=0`, `returned=0`.

### Per-query counts

All five lanes returned **0** item summaries under `sellers:{currys}` + NEW + FIXED_PRICE + GB delivery.

---

## Top 5 items by discount percentage

**None.** The Browse responses contained no `itemSummaries`, so there is no ranking.

---

## Budget / cost log (Part B)

- Research budget remaining **before:** 375 / 800  
- Research budget remaining **after (in-memory):** 370 / 800  
- Confirmed **5** calls max in the successful capturing run.  
- **Total new spend: £0. Existing eBay Browse free-tier quota used: 5 calls out of 5,000/day.**  
- App shared cap: **5 calls out of 800/day** (purpose `clearance-probe`).  
- State branch was **not** mutated by this probe (production `browse_usage` on `origin/state` still showed 425 after the run).

### Call accounting honesty

1. Actions run [42644308669](https://github.com/jwavez/moneyhunter/actions/runs/42644308669) (first attempt) **failed after** the probe loop when writing `/workspace` (permission denied on the runner). That attempt almost certainly also performed **5** Browse HTTP calls whose JSON was **not** persisted.  
2. Capturing run [42645009603](https://github.com/jwavez/moneyhunter/actions/runs/42645009603) performed the **documented 5** calls and saved the artifact.  
3. **Task-level eBay Browse HTTP total is therefore up to ~10**, not 5. The decision numbers below use only the capturing run’s empty result set (both runs used the same locked queries / seller filter). No further Browse calls were made.

---

## Verdict

**Not viable as a Currys clearance acquisition source via `sellers:{currys}` on the Browse API under the locked NEW/FIXED_PRICE/GB filters — needs Awin (or a separately budgeted follow-up probe of `sellers:{currys_clearance}`).** Across five diverse lanes the official Currys main-store username returned **zero** active summaries, so there is no `marketingPrice` signal to evaluate. A zero-hit seller filter cannot feed the pipeline. Phase A’s Awin → Currys feed path remains the structured RRP/clearance candidate; eBay Browse acquisition against **`currys` alone is not supported by this probe.**

---

## Caveats

- **Seller was-price ≠ manufacturer RRP.** Even when `marketingPrice.discountPercentage` is present, eBay documents it as the seller’s discount treatment, not Currys shelf RRP.
- **`sellers:{currys}` returned empty** despite a public store page existing — possible causes include Browse filter interaction with `category_ids`/`q`, seller username mismatch vs store branding, or inventory not matching NEW+FIXED_PRICE+deliveryCountry together. Not diagnosed further (would require extra calls).
- **`currys_clearance` was not probed** (budget / “exactly 5 calls” constraint). That outlet skews refurbished and may fail `conditionIds:{1000}` often.
- In-memory `browse_usage` seed used a shallow copy for `by_purpose` reporting; trust **calls** before/after integers (425→430), not the mirrored `clearance-probe` purpose field in the JSON snapshot.
- No Discord sends, no secrets in outputs, no pricing/grading/publication changes.

---

## Assumptions (prior “spec” text was not provided to this agent)

The user message referenced a “previous spec” that was not attached in the executor payload. Assumptions made to execute:

1. Phase A doc (`docs/clearance_source_research.md`) plus the Phase B brief in the task message are the complete specification.  
2. “Exactly 5 calls” applies to the **capturing** probe design; a failed first Actions attempt that still hit the API is disclosed rather than hidden.  
3. `category_ids=293` is an acceptable EBAY_GB Consumer Electronics top-level id for query 1 when `q` is omitted.  
4. `sellers:{currys}` is the correct main-store username per public eBay profile pages; clearance outlet `currys_clearance` is out of scope for this 5-call budget.  
5. Seeding budget from `origin/state` without writing back is an acceptable reading of “shared 800/day” for a research probe.  
6. Zero-cost means no new paid APIs/subscriptions; GitHub Actions on a public repo is treated as £0 per GitHub hosted-runner policy.  
7. One logical deliverable may span multiple docs-only / enablement PRs if `workflow_dispatch` registration requires the workflow file on `main` before the probe can run.

---

## Decision point (before any Phase C acquisition lane)

1. **Signup (recommended):** User creates Awin publisher account and applies to Currys (free) — Phase A path.  
2. **Optional tiny follow-up (still £0 Browse):** New task with ≤5 calls targeting `sellers:{currys_clearance}` (expect fewer NEW hits).  
3. **Do not** implement a Currys-main Browse acquisition lane based on this probe (0 hits).

**Phase C / acquisition implementation must not start until the user explicitly chooses.**

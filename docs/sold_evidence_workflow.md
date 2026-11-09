# Sold-evidence workflow (PR 25 path) — code audit

Read-only audit of the production Discord → Worker KV → Python scan path.
Citations use `file:line` from `main` at Task 13 audit time. No gate/fee/routing changes.

There are **two** Discord surfaces that look like “sold price”:

| Surface | Entry | Storage | Reaches grading? |
|---|---|---|---|
| **Evidence workspace (PR 25)** | `/menu` → **Evidence / Private outcomes**, or panel button **Submit sold price** (`sc:open` → `EV.panel()`) | KV `ev2:record:{guild}:{id}` | **Yes**, after human approve, via `/api/reviewed-evidence` → `review_bridge` |
| **Legacy `/soldprice` + `/review`** | Slash commands in `worker/src/index.js` | KV `comp:{timestamp}:{userId}` | **No** — inbox only; no bridge |

**This document and the manual test use the Evidence workspace only.**

---

## 1. Submission schema

### Sold observation (kind `sold`)

UI flow (`worker/src/evidence.js`):

1. Panel button **Sold observation** → category select → identity modal → **Enter observation details** terms modal.
2. Identity modal fields (`identityModal`, L32): `match`, `condition` (`new` / `used` / `refurbished`), `variant`, `attrs` (`key=value; …` per category), `source` (public HTTPS URL).
3. Terms modal fields (`termsModal` sold branch, L34): `amount` (sold item GBP excl buyer fees), `shipping` (buyer-paid shipping GBP, `0` if included), `sold` (`YYYY-MM-DD`), `listed` (optional `YYYY-MM-DD`), `observed` (`YYYY-MM-DD`).

Category attribute keys (`keys`, L3):

| Category | Required `attrs` keys |
|---|---|
| gaming | `platform`, `edition`, `format` |
| trainers / sportswear | `sku`, `size`, `gender` |
| fragrance | `concentration`, `ml` |
| lego | `set_number` |
| tools | `model`, `contents` |
| tech | `model`, `capacity` |

Persisted `terms` object on submit (`submit` terms/`sold`, L64):

```text
url            = identity.source (sold listing URL)
sold_at        = YYYY-MM-DD
observed_at    = YYYY-MM-DD
listed_at?     = YYYY-MM-DD
item_price     = amount
shipping       = shipping
price          = item_price + shipping
currency       = "GBP"
kind           = "sold"
identity       = { condition, variant, …category attrs }
```

Validation at submit: listing ≤ sold ≤ observed chronology (L64); GBP money parser (L21); HTTPS allow-listed URL params only (L20); duplicate sold source key rejected while pending/approved (L68, `sourceKey` L26).

**Not in schema (vs informal checklist):** no separate `seller` field; no separate `platform` field — platform is implied by the source URL host. Do not invent them.

### Cash floor (kind `cash`)

Terms modal (`termsModal` cash, L35): `amount` (CASH GBP, not voucher), `cost` (exit/testing/postage GBP), `observed` (**ISO timestamp with timezone**), `cash` (`CASH` or `CASH; PHYSICALLY ACCEPTED`), `conditions` (exact quote/acceptance/testing text).

Persisted terms (L65): `{ amount, exit_cost, currency:"GBP", kind:"cash", observed_at, url, identity }`, plus record flags `physically_accepted`, `conditions`.

Submit-time rules (L65): cash method must be one of the two strings above; quote age must be **&lt; 24 hours** at submit; conditions required.

### Velocity / offer / private outcome

Also implemented (`velocity`, `offer`, private `outcome`) but out of scope for the Task 13 sold+cash manual test except where they affect export grouping (see §7).

---

## 2. Review schema / validation

Review entry: Evidence panel → **Review queue** (`ev:review:0`, `reviewView` L40).

Permission: Manage Server **or** Administrator (`reviewer()`, L12 — Discord permission bitfield `& 40n`).

For each pending record, reviewer opens **Review & approve** / **Reject** / (if already approved) **Revoke**. Modal (`component` L52):

| Field | Approve | Reject / Revoke |
|---|---|---|
| `checks` | must equal exactly `CHECKED` | must equal `REJECT` / `REVOKE` |
| `note` | required, ≥ 3 chars after trim | same |

On approve (`submit` decision, L71–77):

1. Re-check reviewer permission.
2. Require `status === "pending"` and no terminal veto key.
3. `validateCandidate(x)` (L84) — full schema re-validation.
4. Sold: reject if same `sourceKey` already approved.
5. Stamp `reviewed_at`, `reviewer` (Discord user id), `review_note`; set `status` to `approved` / `rejected` / `revoked`; write KV; audit log.

`validateCandidate` cash extras (L84): observed age still &lt; 24h; **`physically_accepted === true`** (so submit method must have been `CASH; PHYSICALLY ACCEPTED`); conditions must **not** match `/not physically accepted|testing pending|subject to testing|acceptance unknown|uninspected|untested/i`.

---

## 3. Storage path

| What | KV namespace / key |
|---|---|
| Binding | Cloudflare Worker binding **`env.MH`** (same KV as community XP/flips) |
| Prefix | `ev2:` (`PREFIX`, L2) |
| Record | `ev2:record:{guildId}:{32-hex-id}` (L27–28, L60, L69, L77) |
| Terminal veto | `ev2:terminal:{guildId}:{id}` = `rejected` / `revoked` (L73–76) |
| Audit | `ev2:audit:{guildId}:{recordId}:{uuid}` (L29) |
| Home guild | `ev2:home` (L15–16) **or** env `EVIDENCE_GUILD_ID` (L14) |
| Private outcomes | `ev2:outcome:{guildId}:{ownerId}:{id}` (L80) — never exported |
| Bound | max `LIMIT=400` records listed (L2, L27, L58) |

Legacy (not PR 25 grading path): `comp:{timestamp}:{userId}` in `worker/src/community.js` L58.

Statuses: `draft` → `pending` → `approved` | `rejected` | `revoked`.

---

## 4. Approval path (pending → usable comps / evidence.json)

```text
Discord Evidence UI
    → KV status=approved  (evidence.js L74–77)
    → GET /api/reviewed-evidence
         = EV.publicFacts(env)   (index.js L423–424; evidence.js L86–89)
    → Python review_bridge.load()
         fetches …/api/reviewed-evidence
         (review_bridge.py L30–54; URL derived from MONEYHUNTER_CAPTURE_URL host)
    → evidence.load(records=…) builds Comp rows
    → cli prepends bridge comps: review_bridge.load(comps) + comps  (cli.py L158–159)
```

### What `publicFacts` exports

- Only `status === "approved"` and **not** terminal-vetoed (L86).
- Re-runs `validateCandidate` (stale cash &gt;24h dropped here).
- Groups by stable `{category, identity, match}`; **skips groups with zero sold observations** (`if(!sales.length)continue`, L88) — cash/velocity/offer alone never create a bridge record.
- Emits schema `human_reviewed_public_facts` with `community_{sha256…}` ids and `record_revisions`.

### What does **not** happen automatically

- **No write to `data/evidence.json`.** Durable file updates are manual: `python -m moneyhunter.cli import-evidence <file>` (`cli.py` L583–587) then commit to `main`. Runtime state cannot silently overwrite main’s reviewed file (`docs/EVIDENCE_PIPELINE.md`).
- Pending / draft / rejected never enter `publicFacts`.
- Legacy `comp:` submissions never enter this path.

### Does a no-send scan (`dry_run=true`, `publish_state=false`) see approved evidence?

**Yes, in memory for that run**, if the bridge is healthy:

- Workflow sets `MONEYHUNTER_CAPTURE_URL` for the scan step (`.github/workflows/scan.yml`), including dry-run.
- `review_bridge.load` does not require state publish.
- Dry-run does **not** persist `seen.json` / state (`scan --dry-run`); artifact `public/deals.json` still carries `stats.sources.reviewed_bridge` and any matched `evidence_type` / `evidence_record_id` fields.

**But today the live endpoint returns empty** with `status: "awaiting_home_guild_binding"` until home guild is bound (see §7). Until that is fixed by opening Evidence once in the sold-prices/flip-log channel (or setting `EVIDENCE_GUILD_ID`), **no-send and live scans alike see zero community records**.

---

## 5. Consumption path (`comps.py` / grading)

1. `comps.load` (`comps.py` L38–51): loads legacy `data/comps.csv` (reference-only) then `evidence.load(evidence_path)` from `data/evidence.json`.
2. Scan prepends live bridge comps (`cli.py` L158–159).
3. `evidence.load` (`evidence.py` L157–186):
   - Drops sold observations older than `C.MAX_COMP_AGE_DAYS` (30).
   - If no fresh solds remain, skips the record.
   - Target = lower quartile of fresh prices; stretch = median.
   - Cash floor attached only if observed age &lt; **86400 seconds** (L171); else `floor=None`.
   - Builds `Comp` with `evidence_type="sold"`, `source_urls`, optional floor/velocity/offers.
4. Matching: `matching.find` / identity guards (`matching.py`); LEGO requires set number in title, etc.
5. `build_deal` (`cli.py` L45–63): copies sold evidence flags, floor ages, `offer_verified` via `checked_offer` (offer URL+price match and age &lt; `MAX_OFFER_AGE_DAYS`).
6. `grading.grade` (`grading.py` L36–107): 16 gates; A needs all; B needs money + reviewed sold + offer/delivery/online/availability subset. One observation cannot satisfy `Sold comps >= 5` (`MIN_COMPS=5`, `config.py` L35).

Fresh vs stale:

| Signal | Fresh definition | Where enforced |
|---|---|---|
| Sold comps | observation `sold_at` within 30 days; `comp_age_days` from oldest supporting sale | `evidence.py` L162; `grading.py` L61, L88 |
| Cash floor | &lt; 24h at load **and** `floor_age_days ≤ MAX_FLOOR_AGE_DAYS` (1) **and** `age_hours &lt; 24` | `evidence.py` L171; `config.py` L87; `grading.py` L43–46, L91 |
| Velocity | `velocity_age_days ≤ MAX_VELOCITY_AGE_DAYS` (7) | `config.py` L88; `grading.py` L48, L92 (not stripped at load) |
| Reviewed offer | `age_hours/24 &lt; MAX_OFFER_AGE_DAYS` (1) | `cli.py` L38–40; `config.py` L89 |

---

## 6. Expiry clocks (with enforcement sites)

| Clock | Limit | Enforced? | Evidence |
|---|---|---|---|
| Sold observations | 30 days | **Yes** | `config.py:46` `MAX_COMP_AGE_DAYS`; `evidence.py:162` filter; `grading.py:61,88` gate |
| Cash floors | 1 day / 24h | **Yes** (multiple layers) | Submit &lt;24h `evidence.js:65`; approve re-check `evidence.js:84`; load drop `evidence.py:171`; grade `grading.py:43–46` + `config.py:87` |
| Velocity | 7 days | **Partial** | Grade gate `grading.py:48,92` + `config.py:88`. **Not** dropped inside `evidence.load` — stale velocity can still sit on the `Comp` while the gate fails |
| Reviewed offers | 1 day | **Yes** | `cli.py:38–40` `checked_offer`; `config.py:89` `MAX_OFFER_AGE_DAYS` |

---

## 7. Known gaps (specific; do not invent)

1. **Home guild unbound on production API (blocking for bridge).** Live `GET /api/reviewed-evidence` currently returns `status: "awaiting_home_guild_binding"` and `records: []` because `publicFacts` → `home(env)` with no interaction and no `EVIDENCE_GUILD_ID` / `ev2:home` yields empty (`evidence.js:13–18,86–87`). Until Evidence is opened once in the configured sold-prices/flip-log channel (or env is set), **approved KV records never reach Python scans**. Manual test step 0 must bind home first.

2. **No automatic `evidence.json` materialisation.** Approval updates KV only. Durable `data/evidence.json` needs `import-evidence` + commit (`cli.py:583–587`). Bridge comps are ephemeral per scan. Step 8 of the manual test must inspect scan/bridge output; do not assume `evidence.json` changed.

3. **Cash-only identities never export.** `publicFacts` skips groups with zero solds (`evidence.js:88`). A cash floor alone cannot appear in comps; cash must share identity with ≥1 approved sold.

4. **Cash approve rejects typical “subject to testing” CeX wording.** `validateCandidate` forbids those phrases and requires `physically_accepted === true` (`evidence.js:84`). Placeholder text in the cash modal (`Subject to testing; …`, L35) would itself fail approval if pasted into `conditions`. CeX 403 / no automated quote bypass remains; user must obtain a real cash figure in a browser and phrase conditions without banned tokens **only if** the quote was physically accepted.

5. **Legacy `/soldprice` + `/review` are a dead-end for grading.** They still write `comp:` pending rows (`community.js:55–58`; `index.js:348,366–370`) with **no** path into `publicFacts` / `review_bridge`. Using them will not exercise PR 25.

6. **No `seller` / `platform` fields** in the sold schema (URL-only provenance). Not a bug relative to code; note for operators who expect them.

7. **Velocity staleness not stripped at load** (`evidence.py` L169–183 vs `grading.py` L48) — gate-only. Non-blocking for sold/cash manual test.

8. **One observation ≠ A/B.** `MIN_COMPS=5` (`config.py:35`) plus offer/delivery/floor/velocity gates (`grading.py:80–93`). Expected Outcome 1 after a successful first sale: bridge shows a fresh sold comp; grade still REJECT / research-only.

**PR 25 Evidence workspace itself is implemented end-to-end in code** (submit → pending → human approve → `publicFacts` → `review_bridge` → comps/grading). Gaps above are integration/ops constraints, not missing Discord review UI.

---

## Outcome expectation (pre–manual test)

- After binding home guild + approving one real sold for a priced LEGO/tool identity, the next scan (including no-send) should show `stats.sources.reviewed_bridge.status == "ready"` (or equivalent) and the identity’s `evidence_type == "sold"` when matched.
- Pending twin must not appear.
- Cash floor only visible when attached to that sold identity and &lt;24h / physically accepted.
- No BUY from a single observation.

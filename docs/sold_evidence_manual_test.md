# Sold-evidence manual test (Task 13 Part B)

**You (the user) run Discord steps. Grok Bot runs the no-send scans after you paste confirmations.**
Do **not** invent sold listings or CeX quotes. Do **not** use the legacy slash `/soldprice` / `/review` path — that inbox does **not** reach grading.

Primary path (as implemented): Discord **Evidence workspace** in `worker/src/evidence.js`, opened via:

* `/menu` → button **Evidence / Private outcomes** (`ev:home`), **or**
* Control-panel / comps-panel button **Submit sold price** (`sc:open` → same Evidence panel).

Review requires **Manage Server** or **Administrator** in the Evidence home guild (`reviewer()` bitfield).

### Candidates from latest scan (pick one; find a *real* eBay sold for it)

From scan artifact / state around 2026-11-09 (Europe/London), publication-supported LEGO identities include:

1. **`LEGO 21586`** — *LEGO Minecraft The Pale Garden 21586* (publication-qualified in recent scan; category `lego`).
2. **`LEGO 75347`** — *LEGO Star Wars TIE Bomber 75347* (publication-qualified; category `lego`).

Optional tool (priced with ask model, not publication-qualified this scan): **`DeWalt DCF887N bare tool 18V`** (attrs `model=DCF887N; contents=bare tool`).

For LEGO submissions use exact identity attributes:

* Category: `lego`
* `match`: e.g. `LEGO 21586`
* `condition`: `new` (only if the sold listing is new/sealed as claimed)
* `variant`: e.g. `standard` (or the exact boxed/sealed wording you verified)
* `attrs`: `set_number=21586` (matching the set you chose)

---

## Step 0 — Bind Evidence home guild (required once)

**Why:** Live `GET https://moneyhunter-bot.moneyhunter.workers.dev/api/reviewed-evidence` currently returns `status: "awaiting_home_guild_binding"` and empty `records`. Until home is bound, approved evidence never reaches Python scans (`docs/sold_evidence_workflow.md` §7.1).

**Action:** In the existing **sold-prices / flip-log** channel of the MoneyHunter Discord server, run:

```text
/menu
```

Then click **Evidence / Private outcomes**.

**Expected:** Evidence panel text: *“Evidence workspace — not a deal recommendation…”* with buttons Sold observation / Cash quote / …

**Paste back:** screenshot or exact panel content + channel name.

---

## Step 1 — Record the candidate identity

**Action:** Choose **one** candidate above. Confirm it still appears in the latest scan’s `review_queue` / deals (title + set number).

**Record / paste back:**

* Exact `match` string (e.g. `LEGO 21586`)
* Category `lego`
* Intended `condition` / `variant` / `attrs`
* Offer title + HUKD URL from the scan (acquisition context only — not the sold URL)

---

## Step 2 — Find a real completed eBay sold listing

**Action:** On eBay.co.uk (or .com), find a **completed sold** listing for the **same** exact identity (same set/model, same condition, GBP). Do not use asking prices, best-offer struck-through asks, or different variants.

**Record / paste back:**

* Sold listing URL (`https://www.ebay.co.uk/itm/…`)
* Item price GBP (excl buyer-only fees)
* Buyer-paid shipping GBP (`0` if included)
* Date sold `YYYY-MM-DD`
* Date you observed it `YYYY-MM-DD`
* Optional date listed `YYYY-MM-DD`
* Brief note that condition/variant match Step 1

---

## Step 3 — Submit as pending (Evidence workspace)

**Action:**

1. `/menu` → **Evidence / Private outcomes** (or **Submit sold price** on the comps panel).
2. Click **Sold observation**.
3. Select category **lego** (or **tools**).
4. Identity modal — fill exactly:

   * Exact product name / repeat same name → `LEGO 21586` (your match)
   * Condition → `new` / `used` / `refurbished` as verified
   * Exact colour / contents / variant → your variant
   * Exact attributes → `set_number=21586`
   * Original public HTTPS source URL → the **sold listing** URL from Step 2

5. Confirmation should offer **Enter observation details** — click it.
6. Terms modal:

   * Actual sold item price GBP → item price
   * Buyer-paid shipping GBP → shipping or `0`
   * Date sold → `YYYY-MM-DD`
   * Date listed → optional
   * Date sale was observed → `YYYY-MM-DD`

**Expected confirmation (exact product string):**

```text
Saved PENDING human review. It is not trusted evidence and creates no BUY signal.
```

(After identity alone you first see: *“Identity saved privately. Next enter actual GBP evidence…”* — that is not yet pending.)

**Paste back:** the PENDING confirmation message verbatim.

---

## Step 4 — Verify it is pending, not approved

**Action:** Evidence panel → **Review queue**.

Navigate with **Previous** / **Next** until you see your submission.

**Expected:** Review card header contains `sold · pending`, your `match`, identity JSON, and submitted facts. Buttons **Review & approve** / **Reject** (not Revoke).

**Paste back:** the review card text (redact nothing material; this is your attestation trail). Confirm status reads **pending**.

---

## Step 5 — No-send scan while pending (Grok Bot runs)

**You:** Paste Step 3–4 confirmations and say “run pending check”.

**Grok Bot will:**

1. Dispatch **one** GitHub Actions `moneyhunter-scan` on `main` with `dry_run=true`, `publish_state=false`, `keep_running=false` (no Discord send; state publish skipped).
2. Download artifact `moneyhunter-no-send-research`.
3. Check:

   * `stats.sources.reviewed_bridge` (or equivalent) — must **not** list your new sold URL / must not show a new `community_*` observation for this identity from the pending row.
   * No `review_queue` / deals row for this identity newly gains `evidence_type: "sold"` **from this pending submission**.
   * `seen.json` on `origin/state` remains byte-identical vs pre-scan snapshot (dry-run does not publish state).

**Honest alternative if bridge still unbound:** If `/api/reviewed-evidence` remains `awaiting_home_guild_binding` or `reviewed_bridge.status` is `unavailable_fail_closed` / empty ready with 0 records **and** Step 0 was skipped, Grok will say so plainly, re-request Step 0, and will **not** pretend pending isolation was proven via comps. Pending isolation is still guaranteed by code (`publicFacts` only exports `approved`), but the live empty export cannot demonstrate a positive contrast until home is bound.

**Paste back (Grok):** run URL + bridge status JSON snippet + “pending not in comps: yes/no”.

---

## Step 6 — Approve the submission

**Action:** In **Review queue**, on the pending card, click **Review & approve**.

Modal:

* `I checked source, GBP, variant/dates: CHECKED` → type exactly **`CHECKED`**
* `Review notes / reason` → real notes (≥3 chars), e.g. what you verified on the eBay page

**Expected confirmation:**

```text
Evidence approved. Approval is a recorded human attestation, not automatic truth, shipping approval or a BUY. Revoked data is excluded on the next coherent read/scan.
```

**Paste back:** confirmation verbatim + your review note text.

---

## Step 7 — No-send scan after approval (Grok Bot runs)

**You:** Paste Step 6 confirmation and say “run approved check”.

**Grok Bot will:**

1. Confirm live `GET /api/reviewed-evidence` now has `status: "ready"` (or non-empty `records`) including your sold URL under a `community_*` id.
2. Dispatch **one** no-send scan (`dry_run=true`, `publish_state=false`).
3. Verify in the artifact:

   * Bridge status ready with `sold_observations >= 1` (or records listing your identity).
   * Matched deal/review entry shows `evidence_type: "sold"` / `evidence_record_id` starting `community_` when the offer title matches.
   * Grading still almost certainly REJECT / research-only (need 5 comps + other gates) — note grade if present.
   * `seen.json` byte-identical.

**If no-send cannot see approved evidence** (unbound home, worker 503, revision mismatch): Grok will say so, will **not** invent success, and will propose waiting for the **next natural cadence live scan** (or fixing home binding) then reading `origin/state:deals.json` / health endpoint instead.

**Paste back (Grok):** run URL + bridge snippet + matched evidence fields + grade note.

---

## Step 8 — Inspect evidence durability / expiry binding

**Action / Grok:**

1. From `/api/reviewed-evidence` (or scan export), confirm the observation fields: URL, `sold_at`, `price` / `item_price`+`shipping`, identity, `reviewed_at`.
2. Confirm sold age window: observation is retained while `sold_at` is within **30 days** (`MAX_COMP_AGE_DAYS`).
3. Check repo `data/evidence.json` on `main` / `origin/state`:

   * **Expect:** file may still be empty / unchanged — approval does **not** auto-write it (`import-evidence` is separate). Report actual contents honestly.

**Paste back:** JSON excerpt of the approved observation from the bridge payload (not fabricated), plus whether `data/evidence.json` changed.

---

## Step 9 — Second sold observation left pending

**Action:** Repeat Steps 2–3 with a **different** real sold URL for the **same** identity (or another priced identity). **Do not approve.**

**Expected:** PENDING confirmation again.

**Grok:** one more no-send (or bridge read) confirming this second URL is **absent** from `publicFacts` / comps while the Step 6 approval remains present.

**Paste back:** PENDING confirmation + Grok’s isolation check.

---

## Step 10 — Cash floor (CeX) on the **same** identity

**Constraint — CeX 403:** Automated CeX/webuy fetches are blocked (403). **No bypass.** Open CeX in **your browser**, get a real **cash** (not voucher) quote for the same identity (or another priced item that already has an approved sold in Steps 6–8 — cash-only identities never export; see workflow §7.3).

**Action:**

1. Evidence panel → **Cash quote** → same category/identity discipline as Step 3 (same `match` / attrs / condition / variant as the approved sold).
2. Source URL: public HTTPS page you used (CeX product URL).
3. Terms:

   * Quoted CASH GBP → cash figure
   * Exit costs GBP → testing/postage deductions you will actually bear (`0` if none)
   * Quote ISO timestamp with timezone → e.g. `2026-11-09T15:00:00+00:00` (**must be &lt;24h old** at submit **and** at approve)
   * `CASH` or `CASH; PHYSICALLY ACCEPTED` → for approve to succeed you **must** use **`CASH; PHYSICALLY ACCEPTED`** and only if that is true
   * Conditions → exact acceptance/testing notes **without** banned phrases `subject to testing`, `testing pending`, `uninspected`, etc. (approve validator rejects those — workflow §7.4). If the quote is only theoretical/subject to testing, **stop and say so** — do not force-approve.

4. Approve via Review queue (same CHECKED + notes), immediately while &lt;24h.

**Expected:** PENDING then `Evidence approved.`

**Grok:** confirm bridge record for that identity now includes `floor` with `kind: "cash"` and that a scan/load treats it as fresh (&lt;1 day). Re-check after &gt;24h only in Part C if you wait; for Part B note the clock.

**Paste back:** cash amount, timestamp, confirmation messages, and whether approve succeeded or validator rejected.

---

## What to send Grok when finished

A single message containing pastes for Steps 0–4, 6, 8–10 confirmations. Grok runs Steps 5/7(/9) scans and later writes `docs/sold_evidence_workflow_verification.md` (Part C) after your run.

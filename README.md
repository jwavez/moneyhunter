# MONEYHUNTER

An online-to-online UK flipping scanner. It reads public hotukdeals RSS feeds for the target categories (trainers, sportswear, LEGO, power tools, gaming, fragrance), matches offers against reviewed observations in `data/evidence.json`; legacy `data/comps.csv` values are reference-only, and calculates conservative fee/cost scenarios (not guaranteed realised profits). Reviewed exact-variant deals are graded A (buy), B (verify) or REJECT using evidence, landed-cost, availability and profit checks, and A/B deals go to your Discord channel through a webhook. No dependencies beyond the Python 3.10+ standard library.

Labels: [S] means sourced (see the Page), [H] means a house rule you can change in `moneyhunter/config.py`.

## 1. Create the Discord webhook
1. In your MONEYHUNTER Discord server, go to Server Settings > Integrations > Webhooks > New Webhook.
2. Pick the alerts channel (for example #moneyhunter), name it MONEYHUNTER, then Copy Webhook URL.
3. Keep the URL secret: anyone who has it can post to your channel.

## 2. Run locally
```bash
export MONEYHUNTER_DISCORD_WEBHOOK="paste-url-here"   # leave unset to dry-run
python -m moneyhunter.cli test-webhook --dry-run      # prints the embed
python -m moneyhunter.cli test-webhook                # sends it
python -m moneyhunter.cli scan --dry-run --show-all   # grade real deals, print only
python -m moneyhunter.cli scan                        # post new A/B deals
python -m unittest tests/test_engine.py
```
If the webhook variable is missing, everything runs as a dry run and prints instead. The URL is never printed.

## 3. Best-effort 30-minute GitHub Actions target
1. Create a **public** GitHub repo; Actions minutes are free on public repos. Push this folder to it.
2. Repo > Settings > Secrets and variables > Actions:
   - Secret `MONEYHUNTER_DISCORD_WEBHOOK` = your webhook URL
   - Optional secrets `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` (existing authorised Browse access; adds clearly separated indicative active asking research, not sold prices)
   - No bankroll variable: the cloud scanner uses the public starter rule set (MONEYHUNTER_COMMUNITY=1)
3. Under Actions, enable workflows. Manual **moneyhunter-scan** defaults to a no-send/no-publication diagnostic; scheduled scans retain normal operation. Deliberately disable its `dry_run` input only when live delivery is intended.

Your ledger (`data/ledger.db`) is git-ignored, so your money data never goes to the public repo.

## 4. Make deals gradeable: comps
The 44 historical CSV keys are retained for compatibility, not approved as exact fresh sold evidence. They cannot generate BUY/VERIFY alerts. No new real sold observations are included in this repair.

See [evidence intake and operating guide](docs/EVIDENCE_PIPELINE.md). Reviewed observations need exact variants/condition, public source URLs and actual sale dates/prices. A also needs measured velocity, a current cash exit quote net of exit costs and an exact recently reviewed online retailer offer. Unknown acquisition delivery is not zero.

```bash
python -m moneyhunter.cli import-evidence /path/to/reviewed-public-observations.json
MONEYHUNTER_DISABLE_SEND=1 python -m unittest discover -s tests -v
```
Commit the resulting reviewed `data/evidence.json` through normal review to persist scheduled inputs. This command validates and saves evidence locally; it does not send anything or push it. Do not insert invented examples or personal information into production data.

Unmatched affordable online offers are prioritised in `data/review_queue.json` and the public export, with specific blockers and hypothetical resale requirements. WATCH cards are research, not approval.

Grades:
- **A, BUY:** all evidence/offer checks pass, including exact realised GBP sold observations no older than 30 days, recent measured velocity and a current cash floor. Expected net and ROI meet the tier minimums, days-to-sell, sell-through, comp count and confidence all pass, the **verified floor exit is at or above breakeven** (the no-loss rule), and the cost is within the tier's max item size.
- **B, VERIFY:** reviewed exact sold evidence, landed costs, retailer offer and availability are established and the money/downside checks pass; velocity or floor verification may still be missing. Never treat active asking prices as sold evidence.
- **REJECT:** anything else. A floor can't guarantee zero losses; the system keeps losses small.

## 5. Ledger commands
```bash
python -m moneyhunter.cli capital 200 "starting bankroll"
python -m moneyhunter.cli buy "adidas Samba OG UK9" trainers 38 --source Vinted --target 65 --floor 30
python -m moneyhunter.cli sell 1 66 ebay_private --postage 2.62
python -m moneyhunter.cli expense 4.99 "mailing bags"
python -m moneyhunter.cli status        # bankroll, tier, tax meters, UC capital check
python -m moneyhunter.cli uc 2026-11-08 2026-12-07 --capital 300   # UC assessment-period report
```
Platforms: `ebay_private`, `ebay_business`, `vinted`, `depop`, `stockx`, `fb`. Fees are calculated automatically unless you pass `--fees`.

## 6. Universal Credit and tax (tracker, not advice)
- Report self-employed income and expenses in your UC journal at the end of **every** monthly assessment period, even if nil.
- Tell your work coach before you start. Once you are classed as *gainfully self-employed* and past any start-up period, UC may use the **Minimum Income Floor**. Pass it with `--mif` and use `--no-startup`.
- Losses carry forward. Earnings £2,500 or more over your nil-UC limit become **surplus earnings**; pass `--nil-limit` from your UC statement.
- Capital under £6,000 has no effect. From £6,000 to £16,000, UC drops £4.35 a month per £250 (or part). Over £16,000, you are usually not eligible. Confirm with DWP how business stock and cash are counted.
- HMRC: a £1,000 trading allowance on gross sales per tax year. If you go over, register for Self Assessment by 5 October after the tax year. Platforms report you at 30 sales or about £1,700 a year (eBay 2026: £1,707).

## Files
- `moneyhunter/fees.py`: fee and cost engine
- `moneyhunter/grading.py`: EV, evidence and acquisition checks, tiers, quarter-Kelly, no-loss floor
- `moneyhunter/scanners/`: `hotukdeals.py` (live), `ebay.py` (needs keys), `cex.py` (blocked, HTTP 403)
- `moneyhunter/discord.py`: webhook embeds, handles 429 rate limits
- `moneyhunter/ledger.py`: SQLite ledger and audit log
- `moneyhunter/benefits.py`: UC and HMRC rules
- `.github/workflows/scan.yml`: best-effort cron, safe tier fallback, health summary and fast-forward public state history


### Reviewed pricing and research access
The scanner export now carries independent exact-product `pricing_catalog` values when genuine observations have been imported, and a `pricing_status` blocker when none exist. Worker Price Check uses this catalog without requiring a current RSS deal; its **Research Watchlist** shows affordable unmatched candidates and missing evidence. `/api/health` exposes public scan/coverage status. Current sourced, unapproved research is in [`data/research_watchlist.json`](data/research_watchlist.json), clearly separate from accepted sold evidence. See [operation, schema and limits](docs/EVIDENCE_PIPELINE.md). These changes do not create sold-data access or promise profitable stock.

### Source-led research and independent capture
See [pinned open-source review and adoption decisions](docs/OPEN_SOURCE_RESEARCH.md).
The existing Worker now buffers four public RSS feeds on a ten-minute target, with
conditional requests and visible failures; `/api/research-capture` exposes retained
research offers, not live-stock guarantees or grades. The Python scanner merges
this buffer via the configured `MONEYHUNTER_CAPTURE_URL`. Scanner grading can still
lag GitHub cron; health distinguishes it from fresh feed capture. Existing Browse
keys can populate a separate six-hour `asking_catalog` for identifiable gaming/LEGO
queries: known item + quoted postage, strict title filters, no sold/velocity claim.
Neither current asks nor retained RSS alone can unlock BUY/VERIFY. No fresh sold
history is bundled or automatically licensed by these changes.

### Autonomous operation

The Worker captures leads independently. The grader now supports a GitHub-native,
server-side delayed successor instead of depending only on unreliable cron. See
[operational setup, no-send acceptance and pricing boundaries](docs/AUTONOMOUS_OPERATION.md).

### Practical competitor pricing

[Competitor-based resale estimates](docs/COMPETITOR_ESTIMATES.md) are now a separate
model and labelled CHECK opportunity path. Sold history is not required for these
estimates. Verified BUY semantics are unchanged.

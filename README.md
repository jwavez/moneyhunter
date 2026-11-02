# MONEYHUNTER

An online-to-online UK flipping scanner. It reads public hotukdeals RSS feeds for the target categories (trainers, sportswear, LEGO, power tools, gaming, fragrance), prices each deal against sold-price comps you keep in `data/comps.csv`, and works out the real profit after every fee and cost. Each deal is graded A (buy), B (verify) or REJECT using 8 checks, and A/B deals go to your Discord channel through a webhook. No dependencies beyond the Python 3.10+ standard library.

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

## 3. Run free every 30 minutes on GitHub Actions
1. Create a **public** GitHub repo; Actions minutes are free on public repos. Push this folder to it.
2. Repo > Settings > Secrets and variables > Actions:
   - Secret `MONEYHUNTER_DISCORD_WEBHOOK` = your webhook URL
   - Optional secrets `EBAY_CLIENT_ID` and `EBAY_CLIENT_SECRET` (free eBay developer keys; adds the active-listing count and median asking price)
   - No bankroll variable: the cloud scanner uses the public starter rule set (MONEYHUNTER_COMMUNITY=1)
3. Under Actions, enable workflows, then run **moneyhunter-scan** once by hand.

Your ledger (`data/ledger.db`) is git-ignored, so your money data never goes to the public repo.

## 4. Make deals gradeable: comps
`data/comps.csv` is seeded only with published sold ranges (Nifty eBay UK study, Oct 2026). For A grades, check each item in Terapeak (eBay Seller Hub > Research) and fill in:
`floor` (the CeX cash price, checked the same day), `sold_90d`, `sell_through` (sold ÷ active × 100) and `days_to_sell`.
Deals without comps are listed as *unpriced* by `scan --show-all`.

Grades:
- **A, BUY:** all 8 checks pass. Expected net and ROI meet the tier minimums, days-to-sell, sell-through, comp count and confidence all pass, the **verified floor exit is at or above breakeven** (the no-loss rule), and the cost is within the tier's max item size.
- **B, VERIFY:** the money works, but your own comps or floor check is missing.
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
- `moneyhunter/grading.py`: EV, the 8 checks, tiers, quarter-Kelly, no-loss floor
- `moneyhunter/scanners/`: `hotukdeals.py` (live), `ebay.py` (needs keys), `cex.py` (blocked, HTTP 403)
- `moneyhunter/discord.py`: webhook embeds, handles 429 rate limits
- `moneyhunter/ledger.py`: SQLite ledger and audit log
- `moneyhunter/benefits.py`: UC and HMRC rules
- `.github/workflows/scan.yml`: the 30-minute schedule

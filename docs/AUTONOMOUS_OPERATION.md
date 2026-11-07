# Autonomous capture and grading

## Two independent production clocks

- Cloudflare Worker `*/10 * * * *`: bounded RSS **capture only**, retained in KV.
  Authenticated KV inspection on 7 November 2026 confirmed successful automatic
  capture at 14:00:24 London, all four configured feeds healthy and 22 retained offers.
  This is not evidence that the GitHub grader ran, nor sold history.
- GitHub `moneyhunter-scan`: collects current feeds plus that buffer, researches
  current NEW active asking prices with the existing authorised Browse API, grades
  only genuine reviewed sold observations, and publishes public state.

The old 30-minute cron was active but actually last fired at 09:10 London on
7 November (old revision d03406a). No scheduled grader had used the upgraded revision
by 14:14 London. Worker capture cannot repair a stopped grader on its own.

## GitHub-native delayed successor (no new service or copied token)

A scan can now arm a successor using GitHub's environment wait timer. GitHub waits
server-side, without an allocated runner or billable wait time, then a short job
uses its own ephemeral, repository-scoped `GITHUB_TOKEN` (`actions: write`,
`contents: read`) to call the documented `workflow_dispatch` endpoint. No personal
access token is extracted or transferred to Cloudflare. Public repositories support
these timers on GitHub Free. This repository must remain public for this setup.

Configure the two **repository-only** environments through GitHub's documented API:

```sh
gh api --method PUT repos/jwavez/moneyhunter/environments/moneyhunter-cadence \
  -F wait_timer=30 -F 'deployment_branch_policy[protected_branches]=false' \
  -F 'deployment_branch_policy[custom_branch_policies]=true'
gh api --method POST repos/jwavez/moneyhunter/environments/moneyhunter-cadence/deployment-branch-policies \
  -f name=main -f type=branch
# Repeat for moneyhunter-cadence-probe with wait_timer=1.
```

These are scheduling gates, not claims that application code has been deployed.
No environment secrets, new provider, paid runtime, local daemon or idle runner is
needed. Timers and API processing are not real-time guarantees. GitHub incidents
or disabled Actions can still interrupt operation. Cron remains an independent
best-effort watchdog. Repeated cron/rearm jobs replace the delayed successor rather
than forking independent loops; scan jobs separately serialize state publication.
A minimum elapsed-time check fails closed if a timer is accidentally removed.
API permission errors are visible failed jobs, never silently treated as scheduled.
An ambiguous POST is not retried, to avoid duplicate dispatches.

### Reproducible acceptance without Discord sends

```sh
# Real feeds/API, real state publication; alert acknowledgements remain unchanged.
# Exactly one automatic no-send successor after the one-minute probe gate.
gh workflow run scan.yml --repo jwavez/moneyhunter --ref main \
  -f dry_run=true -f publish_state=true -f cadence_probe=true
# Start ongoing normal operation without manually sending a test alert.
# Initial scan is no-send; future 30-minute successors use ordinary app behaviour.
gh workflow run scan.yml --repo jwavez/moneyhunter --ref main \
  -f dry_run=true -f publish_state=true -f keep_running=true
```

Prove an automatic successor by checking its `github-actions[bot]` actor, its
`parent_run_id`, current `execution.revision`, feed diagnostics, actual export time,
and normal fast-forward state commit. Default manual diagnostics remain artifact
only. `--no-send` publishes actual observations without routing or falsely marking
unsent alerts as delivered; `--dry-run` remains nonpersistent.

Emergency pause: disable `scan.yml`, or set repository Actions variable
`MH_SCANNER_PAUSED=1` and cancel any already-running scan. Clearing the pause and
starting a no-send bootstrap resumes it. No code merge or leaked token is needed.

## Pricing remains evidence-dependent

The automatic Browse integration supplies indicative current asking totals, not
sales, forecasts, demand or cash exits. Grading and sold evidence never consume
those asks. Missing delivery remains unknown. The evidence importer accepts exact
condition/variant sales with separate sale, observation and review dates. Grade B
already allows missing cash floor/velocity when its other financial, evidence and
offer checks pass; A still requires the extra exit/velocity safeguards.

Zero reviewed sold observations is a data-access blocker, not proof there are no
deals. Neither scheduling nor open-source examples can create an unavailable sold
API entitlement. eBay Product Research in the user's permitted session, authorised
exports or independently verifiable completed sales can supply reviewed records.
The user-held CAPTCHA must be cleared normally; never substitute a scraper,
proxy, alternate domain or internal API. MusicMagpie exposes an official barcode
quote form, but no quote or documented public quote API has been obtained here.
Do not call it a configured automatic cash exit.

References:
- https://docs.github.com/en/actions/reference/workflows-and-actions/deployments-and-environments#wait-timer
- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
- https://docs.github.com/en/rest/actions/workflows#create-a-workflow-dispatch-event
- https://docs.github.com/en/rest/deployments/environments#create-or-update-an-environment
- https://www.musicmagpie.co.uk/entertainment/trade-in-games

## Whole-product research identity correction

The first real autonomous run exposed asking ranges as low as £3.49 for a named
LEGO set and nine wide-spread snapshots out of thirteen lookups. That alone does
not prove which listings were wrong. Code inspection, however, confirmed that a
set number alone plus singular “sticker”, “instruction booklet” or a SMART tag could
pass the old title filter. Those are components, not evidence of a whole set price.

LEGO research now also requires distinctive product-name tokens from the source
lead, rejects those component/accessory forms, and fingerprints the name alongside
the set number in its durable cache. Old number-only snapshots are not reused.
Up to three accepted source examples retain listing title, declared condition,
item price and fixed shipping so the filter can be audited. Genuine price extremes
are still retained and flagged, never removed just to raise a resale estimate.
These remain seller-declared active asks, not independently verified products or
realised sales. Gaming keeps its separate platform/edition/accessory checks.

The bounded acceptance probe has its own concurrency group: rechecking it cannot
cancel the normal production delayed successor. Both share the serialized scan
publication boundary, not a timer cancellation group.

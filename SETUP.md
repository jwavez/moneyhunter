# MONEYHUNTER setup (free, runs without your computer)

Everything runs on free tiers: GitHub Actions scans every 30 min, a Cloudflare Worker answers Discord slash commands.
Your ledger, UC and tax data stay on your own machine (git-ignored) and are never uploaded.

## 1. GitHub (scanner) ~10 min
1. Create a free account at github.com (or let the assistant run `gh auth login` with a device code you approve).
2. Create a **public** repo, e.g. `moneyhunter` (public = unlimited free standard runners).
3. Push this folder: `git add -A && git commit -m init && git remote add origin https://github.com/YOU/moneyhunter.git && git push -u origin main`
4. Repo > Settings > Secrets and variables > Actions > New repository secret:
   - `MONEYHUNTER_DISCORD_WEBHOOK` (your deals-channel webhook URL)
   - `EBAY_CLIENT_ID`, `EBAY_CLIENT_SECRET` (when eBay approves your developer account)
5. Repo > Settings > Actions > General > Workflow permissions: **Read and write**.
6. Actions tab > moneyhunter-scan > **Run workflow** once. It creates a `state` branch with `deals.json`, `seen.json`, `comps.csv`.
7. Create a fine-grained token for the bot's /scan button: github.com/settings/personal-access-tokens > Fine-grained >
   only this repo > Permissions: **Actions: Read and write**. Copy it (used in step 3.4).

## 2. Discord application ~5 min
1. discord.com/developers/applications > **New Application** "MONEYHUNTER".
2. General Information: copy **Application ID** and **Public Key**.
3. Bot tab: **Reset Token**, copy the **Bot token** (only used once, to register commands; keep it private).
4. Installation (or OAuth2 > URL Generator): scopes `applications.commands` (+ `bot` optional) > open the link > add to your server.
5. Optional: right-click your server > Copy Server ID (enable Developer Mode) for instant command registration.

## 3. Cloudflare Worker (bot) ~10 min
1. Create a free account at dash.cloudflare.com.
2. On the box: `cd worker && wrangler login` (opens a browser sign-in you complete).
3. Edit `worker/wrangler.toml`: replace `OWNER/REPO` (3 places) with `YOU/moneyhunter`.
4. Secrets: `wrangler secret put DISCORD_PUBLIC_KEY` and `wrangler secret put GITHUB_TOKEN`.
5. `wrangler deploy` and copy the `https://moneyhunter-bot.<you>.workers.dev` URL.
6. Discord Developer Portal > General Information > **Interactions Endpoint URL** = that URL > Save
   (Discord sends a signed PING; it only saves if the Worker answers correctly).
7. Register commands: `DISCORD_APP_ID=... DISCORD_BOT_TOKEN=... DISCORD_GUILD_ID=... node scripts/register.mjs`

## Commands
`/deal` latest deals · `/price item [buy]` sold range + max buy · `/calc buy sell [platform] [category]` · `/scan` (Manage Server) · `/help`

## Keeping it alive
Public repos auto-disable scheduled workflows after 60 days with no repo activity. The workflow's keepalive step re-enables it
through the API when main has no commits for 45 days. If it ever stops, Actions tab > Enable workflow.

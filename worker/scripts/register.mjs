// Registers slash commands. Usage:
//   DISCORD_APP_ID=... DISCORD_BOT_TOKEN=... [DISCORD_GUILD_ID=...] node scripts/register.mjs
// With a guild id, commands appear instantly in that server; without, globally.
const { DISCORD_APP_ID: app, DISCORD_BOT_TOKEN: tok, DISCORD_GUILD_ID: guild } = process.env;
const S = 3, N = 10; // option types: string, number
const platforms = ["ebay_business", "ebay_private", "vinted", "depop", "stockx", "fb"].map(v => ({ name: v, value: v }));
const cats = ["trainers", "sportswear", "lego", "fragrance", "gaming", "tools", "default"].map(v => ({ name: v, value: v }));
export const COMMANDS = [
  { name: "menu", description: "Open the MONEYHUNTER control panel" },
  { name: "deal", description: "Browse the latest graded deals" },
  { name: "setup", description: "Post the control panel in this channel (Manage Server)", default_member_permissions: "32" },
  { name: "price", description: "Sold range, max buy and profit for an item",
    options: [{ type: S, name: "item", description: "e.g. mario kart 8", required: true }, { type: N, name: "buy", description: "Your buy price in £", min_value: 0 }] },
  { name: "calc", description: "Fee and profit calculator",
    options: [{ type: N, name: "buy", description: "Buy price £", required: true, min_value: 0 }, { type: N, name: "sell", description: "Sell price £", required: true, min_value: 0 },
      { type: S, name: "platform", description: "Where you sell", choices: platforms }, { type: S, name: "category", description: "Item category", choices: cats }] },
  { name: "scan", description: "Start a fresh scan now (coming soon)" },
  { name: "help", description: "How MONEYHUNTER works" },
  { name: "logflip", description: "Log a buy/sell flip and earn XP" },
  { name: "soldprice", description: "Submit a real sold price for review" },
  { name: "leaderboard", description: "Community XP leaderboard" },
  { name: "review", description: "Latest sold-price submissions (Manage Server)", default_member_permissions: "32" },
];
if (import.meta.url === `file://${process.argv[1]}`) {
  if (!app || !tok) { console.error("Set DISCORD_APP_ID and DISCORD_BOT_TOKEN"); process.exit(1); }
  const url = `https://discord.com/api/v10/applications/${app}/${guild ? `guilds/${guild}/` : ""}commands`;
  const r = await fetch(url, { method: "PUT", headers: { authorization: `Bot ${tok}`, "content-type": "application/json" }, body: JSON.stringify(COMMANDS) });
  console.log(r.status, r.ok ? "registered " + COMMANDS.length + " commands" : await r.text());
}

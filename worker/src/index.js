// MONEYHUNTER Discord bot: HTTP interactions on Cloudflare Workers (no gateway).
import { calc, parseCsv, findComp, gbp, verifyDiscord } from "./logic.js";

const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "content-type": "application/json" } });
const reply = (data, ephemeral = false) => json({ type: 4, data: { ...data, flags: ephemeral ? 64 : 0, allowed_mentions: { parse: [] } } });
const opt = (i, n) => i.data.options?.find(o => o.name === n)?.value;
const GREEN = 0x22c55e, AMBER = 0xf59e0b, RED = 0xef4444, BLUE = 0x3b82f6;

async function getJson(url) { const r = await fetch(url, { cf: { cacheTtl: 60 } }); if (!r.ok) throw new Error(url + " " + r.status); return r.json(); }
async function getText(url) { const r = await fetch(url, { cf: { cacheTtl: 300 } }); if (!r.ok) throw new Error(url + " " + r.status); return r.text(); }

async function cmdDeal(env) {
  const d = await getJson(env.DEALS_URL);
  const top = d.deals.slice(0, 5);
  const icon = g => g === "A" ? "🟢" : g === "B" ? "🟡" : "🔴";
  const lines = top.map(x => `${icon(x.grade)} **[${x.title.slice(0, 60)}](${x.url})**\n${gbp(x.buy)} → ${gbp(x.target)} · net ${gbp(x.net)} · max buy ${gbp(x.max_buy)}${x.why.length ? " · " + x.why[0] : ""} · [eBay sold](${x.ebay_sold})`);
  const s = d.stats;
  return reply({ embeds: [{ title: `🔎 Latest scan · ${s.A} buy · ${s.B} verify`, color: s.A ? GREEN : s.B ? AMBER : BLUE,
    description: lines.join("\n\n") || `Nothing priced under £${d.price_cap} right now.`,
    footer: { text: `${s.scanned} scanned · ${s.priced} priced · updated ${d.generated_utc.replace("T", " ").slice(0, 16)} UTC` } }] });
}

async function cmdPrice(i, env) {
  const q = String(opt(i, "item")), buy = opt(i, "buy");
  const comps = parseCsv(await getText(env.COMPS_URL));
  const c = findComp(q, comps);
  if (!c) return reply({ content: `No sold-price data for “${q.slice(0, 80)}” yet. Try a shorter name, or check [eBay sold](https://www.ebay.co.uk/sch/i.html?_nkw=${encodeURIComponent(q)}&LH_Sold=1&LH_Complete=1).` }, true);
  const sell = parseFloat(c.low), hi = parseFloat(c.high);
  const k = calc(buy ?? 0, sell, "ebay_business", c.category), kv = calc(buy ?? 0, sell, "vinted", c.category);
  const fields = [
    { name: "Sold range", value: `${gbp(sell)} – ${gbp(hi)}`, inline: true },
    { name: "Max buy (eBay business)", value: gbp(k.maxBuy), inline: true },
    { name: "Max buy (Vinted)", value: gbp(kv.maxBuy), inline: true },
  ];
  if (buy != null) fields.push({ name: "Net if you buy at " + gbp(buy), value: `eBay ${gbp(k.net)} (${k.roi}%) · Vinted ${gbp(kv.net)} (${kv.roi}%)`, inline: false });
  fields.push({ name: "Evidence", value: (c.sold_evidence + " · " + c.source).slice(0, 1000), inline: false });
  return reply({ embeds: [{ title: `💷 ${c.match} (${c.category})`, color: BLUE, fields, footer: { text: "Max buy leaves £8 net and 40% ROI after fees, postage, packaging and 3% returns" } }] });
}

function cmdCalc(i) {
  const k = calc(opt(i, "buy"), opt(i, "sell"), opt(i, "platform") ?? "ebay_business", opt(i, "category") ?? "default");
  return reply({ embeds: [{ title: `🧮 ${gbp(k.sell)} on ${k.platform} → net ${gbp(k.net)} (${k.roi}% ROI)`, color: k.net >= 8 ? GREEN : k.net > 0 ? AMBER : RED,
    fields: [["Buy", k.buy], ["Fee", k.fee], ["Postage", k.postage], ["Packaging", k.packaging], ["Returns 3%", k.returns], ["Max buy", k.maxBuy]].map(([n, v]) => ({ name: n, value: gbp(v), inline: true })),
    footer: { text: "Vinted: buyer pays postage. Rates checked 2 Nov 2026" } }] });
}

async function dispatchScan(i, env) {
  const r = await fetch(`https://api.github.com/repos/${env.GITHUB_REPO}/actions/workflows/scan.yml/dispatches`, {
    method: "POST", headers: { authorization: `Bearer ${env.GITHUB_TOKEN}`, accept: "application/vnd.github+json", "user-agent": "moneyhunter-bot", "x-github-api-version": "2022-11-28" },
    body: JSON.stringify({ ref: env.GITHUB_REF || "main" }) });
  const msg = r.status === 204 ? "✅ Scan started. Results post in the deals channel in about 1–2 minutes." : `⚠️ Could not start scan (GitHub ${r.status}).`;
  await fetch(`https://discord.com/api/v10/webhooks/${i.application_id}/${i.token}/messages/@original`, { method: "PATCH", headers: { "content-type": "application/json" }, body: JSON.stringify({ content: msg }) });
}

const HELP = ["**/deal** latest graded deals from the last scan", "**/price item [buy]** sold range, max buy, net at your price",
  "**/calc buy sell [platform] [category]** fee and profit calculator", "**/scan** start a fresh scan (Manage Server only)",
  "Grades: 🟢 all 8 checks pass · 🟡 numbers work, verify comps · 🔴 pass. Not financial advice."].join("\n");

export default {
  async fetch(req, env, ctx) {
    if (req.method !== "POST") return new Response("MONEYHUNTER bot is running", { status: 200 });
    const body = await req.text();
    if (!(await verifyDiscord(req, body, env.DISCORD_PUBLIC_KEY))) return new Response("invalid request signature", { status: 401 });
    const i = JSON.parse(body);
    if (i.type === 1) return json({ type: 1 }); // PING -> PONG
    if (i.type !== 2) return reply({ content: "Unsupported." }, true);
    try {
      switch (i.data.name) {
        case "deal": return await cmdDeal(env);
        case "price": return await cmdPrice(i, env);
        case "calc": return cmdCalc(i);
        case "help": return reply({ embeds: [{ title: "MONEYHUNTER commands", description: HELP, color: BLUE }] }, true);
        case "scan": {
          const perms = BigInt(i.member?.permissions ?? "0");
          if (!(perms & 0x20n)) return reply({ content: "Only members with Manage Server can start a scan. Scans also run automatically every 30 min." }, true);
          if (!env.GITHUB_TOKEN) return reply({ content: "Manual scan is not enabled yet. Scans run automatically every 30 min." }, true);
          ctx.waitUntil(dispatchScan(i, env));
          return json({ type: 5 }); // deferred: answer within 3 s, edit within 15 min
        }
      }
      return reply({ content: "Unknown command." }, true);
    } catch (e) { return reply({ content: "Something went wrong: " + String(e.message).slice(0, 150) }, true); }
  },
};

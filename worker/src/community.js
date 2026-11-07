// Community features stored in Cloudflare KV (free: 100k reads/day, 1k writes/day, 1 GB).
// Data stored: Discord user id + display name, and what members choose to submit. Nothing else.
import { calc, gbp } from "./logic.js";
const row = (...c) => ({ type: 1, components: c });
const ti = (id, label, req = true, ph = "", style = 1) => row({ type: 4, custom_id: id, label, style, required: req, placeholder: ph, max_length: style === 2 ? 300 : 80 });
const num = v => (v == null || v === "" ? null : parseFloat(String(v).replace(/[£,\s]/g, "")));
export const XP_PER_FLIP = 10, XP_CAP = 200;
export const xpFor = profit => XP_PER_FLIP + Math.min(XP_CAP, Math.max(0, Math.round(profit)));
const PLAT = { ebay: "ebay_business", "ebay business": "ebay_business", "ebay private": "ebay_private", vinted: "vinted", depop: "depop", stockx: "stockx", fb: "fb", facebook: "fb" };

export const flipPanel = () => ({ embeds: [{ title: "📒 Flip log", color: 0x22c55e,
  description: "Bought or sold something? Click **Log a flip**. Fees are worked out for you, and you earn community XP.\n\n" +
    "XP: **10 per flip + 1 per £ profit** (max 200 per flip). Flips with £20+ profit are shared in #wins.\nOnly log what you are happy to share publicly.",
  footer: { text: "Weekly leaderboard every Monday 9am" } }],
  components: [row({ type: 2, style: 3, label: "Log a flip", custom_id: "fl:open", emoji: { name: "📒" } }, { type: 2, style: 2, label: "Leaderboard", custom_id: "lb:show", emoji: { name: "🏆" } })] });
export const compsPanel = () => ({ embeds: [{ title: "🧾 Submit a sold price", color: 0x3b82f6,
  description: "Seen what an item **actually sold for** (actual sold listing; a CeX cash quote is separate floor evidence)? Submit it and help price more deals for everyone.\n" +
    "Submissions are reviewed before they are used. Please include a link to the sold listing.", footer: { text: "+5 XP per accepted submission" } }],
  components: [row({ type: 2, style: 1, label: "Submit sold price", custom_id: "sc:open", emoji: { name: "🧾" } })] });

export const flipModal = () => ({ custom_id: "m:flip", title: "📒 Log a flip", components: [
  ti("item", "Item", true, "e.g. Nike Air Force 1 size 9"), ti("buy", "Buy price (£)", true, "e.g. 30"), ti("sell", "Sold for (£)", true, "e.g. 55"),
  ti("platform", "Sold on: ebay, ebay private, vinted, depop, fb", true, "vinted"), ti("note", "Tip or where you found it (optional)", false, "", 2)] });
export const compModal = () => ({ custom_id: "m:comp", title: "🧾 Submit a sold price", components: [
  ti("item", "Item (exact model)", true, "e.g. LEGO 76449"), ti("price", "Sold price (£)", true, "e.g. 32"),
  ti("date", "Date sold", true, "e.g. 2026-11-01"), ti("link", "Link to sold listing", true, "https://www.ebay.co.uk/itm/..."), ti("condition", "Condition", false, "new / used")] });

const who = i => ({ id: i.member?.user?.id ?? i.user?.id, name: i.member?.nick || i.member?.user?.global_name || i.member?.user?.username || "member" });
async function getLb(env) { return (await env.MH.get("lb", "json")) || {}; }

export async function logFlip(i, v, env) {
  const buy = num(v.buy), sell = num(v.sell), pl = PLAT[String(v.platform || "").trim().toLowerCase()];
  if ([buy, sell].some(x => x == null || isNaN(x))) return { error: "Please enter numbers for buy and sold price." };
  if (!pl) return { error: "Platform not recognised. Use ebay, ebay private, vinted, depop or fb." };
  if (sell > 5000 || buy > 5000) return { error: "That's above the £5,000 limit for logged flips." };
  const k = calc(buy, sell, pl, "default"), u = who(i), xp = xpFor(k.net);
  const lb = await getLb(env); const e = lb[u.id] || { name: u.name, xp: 0, flips: 0 };
  e.name = u.name; e.xp += xp; e.flips += 1; lb[u.id] = e;
  await env.MH.put("lb", JSON.stringify(lb));
  await env.MH.put(`flip:${Date.now()}:${u.id}`, JSON.stringify({ u: u.id, item: String(v.item).slice(0, 80), buy, sell, pl, net: k.net, ts: new Date().toISOString() }), { expirationTtl: 60 * 60 * 24 * 400 });
  const embed = { author: { name: `${u.name} logged a flip` }, title: `${k.net >= 0 ? "✅" : "📉"} ${String(v.item).slice(0, 80)}`, color: k.net >= 20 ? 0xeab308 : k.net >= 0 ? 0x22c55e : 0xef4444,
    fields: [{ name: "Bought", value: gbp(buy), inline: true }, { name: "Sold", value: `${gbp(sell)} · ${pl.replace("_", " ")}`, inline: true },
      { name: "Net after fees", value: `**${gbp(k.net)}**`, inline: true }, { name: "XP", value: `+${xp} (total ${e.xp})`, inline: true }],
    footer: { text: "Fees, postage, packaging and 3% returns estimated by MONEYHUNTER" } };
  if (v.note) embed.description = "💡 " + String(v.note).slice(0, 300);
  return { embed, net: k.net };
}
export async function postToChannel(env, channel, body) {
  if (!env.DISCORD_BOT_TOKEN || !channel) return;
  await fetch(`https://discord.com/api/v10/channels/${channel}/messages`, { method: "POST", headers: { authorization: `Bot ${env.DISCORD_BOT_TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ allowed_mentions: { parse: [] }, ...body }) });
}
export async function submitComp(i, v, env) {
  const p = num(v.price), link = String(v.link || "").trim();
  if (p == null || isNaN(p) || p <= 0) return { error: "Please enter the sold price as a number." };
  if (!/^https?:\/\//.test(link)) return { error: "Please include a link to the sold listing (starting https://)." };
  const u = who(i), id = `comp:${Date.now()}:${u.id}`;
  await env.MH.put(id, JSON.stringify({ u: u.id, name: u.name, item: String(v.item).slice(0, 80), price: p, date: String(v.date).slice(0, 20), link: link.slice(0, 300), condition: String(v.condition || "").slice(0, 20), status: "pending" }), { expirationTtl: 60 * 60 * 24 * 180 });
  return { ok: true, p };
}
export async function leaderboard(env, n = 15) {
  const lb = await getLb(env);
  return Object.values(lb).sort((a, b) => b.xp - a.xp).slice(0, n).map(e => ({ name: e.name, xp: e.xp, flips: e.flips }));
}
export async function pendingComps(env) {
  const l = await env.MH.list({ prefix: "comp:", limit: 20 });
  const out = [];
  for (const k of l.keys.slice(-10)) { const v = await env.MH.get(k.name, "json"); if (v) out.push(v); }
  return out;
}
export const lbEmbed = top => ({ title: "🏆 Community leaderboard", color: 0xeab308,
  description: top.length ? top.map((u, i) => `${["🥇", "🥈", "🥉"][i] ?? `\`${i + 1}.\``} **${u.name}** · ${u.xp} XP · ${u.flips} flips`).join("\n") : "No flips logged yet. Be the first in #flip-log!",
  footer: { text: "XP: 10 per flip + 1 per £ profit (max 200 per flip)" } });

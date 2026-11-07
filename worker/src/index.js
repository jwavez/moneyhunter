// MONEYHUNTER Discord bot: HTTP interactions on Cloudflare Workers (no gateway), button-driven UI.
import { calc, parseCsv, findComp, gbp, verifyDiscord } from "./logic.js";
import * as CM from "./community.js";

const C = { A: 0x22c55e, B: 0xf59e0b, R: 0xef4444, BRAND: 0x8b5cf6, INFO: 0x3b82f6 };
const EPH = 64;
const json = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "content-type": "application/json" } });
const msg = (data, eph = true) => json({ type: 4, data: { allowed_mentions: { parse: [] }, ...data, flags: eph ? EPH : 0 } });
const upd = data => json({ type: 7, data: { allowed_mentions: { parse: [] }, ...data } });
const modal = data => json({ type: 9, data });
const opt = (i, n) => i.data.options?.find(o => o.name === n)?.value;
const bar = (p, n = 10) => { const k = Math.max(0, Math.min(n, Math.round(p / 100 * n))); return "▰".repeat(k) + "▱".repeat(n - k); };
const row = (...c) => ({ type: 1, components: c });
const btn = (id, label, emoji, style = 2, disabled = false) => ({ type: 2, style, label, custom_id: id, emoji: { name: emoji }, disabled });
const link = (url, label, emoji) => ({ type: 2, style: 5, label, url: String(url).slice(0, 512), emoji: { name: emoji } });
const pct = x => (x >= 0 ? "+" : "−") + Math.abs(x).toFixed(0) + "%";
const sgbp = x => (x >= 0 ? "+" : "") + gbp(x);

const CATS = [["all", "All deals", "🔎"], ["trainers", "Trainers", "👟"], ["lego", "LEGO", "🧱"], ["games", "Games", "🎮"],
  ["consoles", "Consoles", "🕹️"], ["tools", "Tools", "🛠️"], ["fragrance", "Fragrance", "🧴"]];
const isConsole = d => d.category === "gaming" && /console|oled|switch 2|ps5 (slim|pro|digital)|xbox series/i.test(d.title);
function filterDeals(deals, f) {
  switch (f) {
    case "top": return deals.filter(d => d.grade !== "R" && d.under_cap);
    case "near": return deals.filter(d => d.grade === "R" && d.under_cap);
    case "all": return deals;
    case "games": return deals.filter(d => d.category === "gaming" && !isConsole(d));
    case "consoles": return deals.filter(isConsole);
    default: return deals.filter(d => d.category === f);
  }
}
const FNAME = { top: "Top deals", near: "Near misses", all: "All priced deals", games: "Games", consoles: "Consoles", trainers: "Trainers", lego: "LEGO", tools: "Tools", fragrance: "Fragrance" };

async function getDeals(env) { const r = await fetch(env.DEALS_URL, { cf: { cacheTtl: 60 } }); if (!r.ok) throw new Error("deals feed " + r.status); return r.json(); }
async function getComps(env) { const r = await fetch(env.COMPS_URL, { cf: { cacheTtl: 300 } }); if (!r.ok) throw new Error("comps " + r.status); return parseCsv(await r.text()); }
const updated = d => d.generated_utc.replace("T", " ").slice(0, 16) + " UTC";

// ---------- control panel ----------
function panel(d) {
  const s = d?.stats;
  const status = s ? `**${s.A}** buy · **${s.B}** verify · **${s.R}** passed · **${s.scanned}** scanned\nLast scan ${updated(d)}` : "Scan data loading…";
  return {
    embeds: [{
      author: { name: "MONEYHUNTER" }, title: "💰 Control Panel", color: C.BRAND,
      description: "Find under-£60 deals that resell for profit, with every fee counted.\nClick a button below. Results are private to you.",
      fields: [{ name: "📡 Live status", value: status }],
      footer: { text: "30-minute cron target, best effort; inspect last scan · Not financial advice" },
    }],
    components: [
      row(btn("v:top:0", "Top Deals", "🟢", 3), btn("v:near:0", "Near Misses", "🟡", 1), btn("p:cats", "Categories", "🗂️")),
      row(btn("p:calc", "Profit Calculator", "🧮", 1), btn("p:price", "Price Check", "💷", 1)),
      row(btn("p:how", "How it works", "📘"), btn("p:scan", "Scan Now", "⚡")),
    ],
  };
}

// ---------- deal browser ----------
function dealView(d, list, f, i) {
  const n = list.length;
  const nav = (j, label, emoji, dis) => btn(`v:${f}:${j}`, label, emoji, 2, dis);
  const home = btn("p:home", "Menu", "🏠");
  if (!n) {
    return { embeds: [{ title: `${FNAME[f] ?? f}: nothing right now`, color: C.INFO,
      description: f === "top" ? "No deal passes the money checks this scan. Near misses show what came closest." : "No priced deals in this view this scan.",
      footer: { text: `Last scan ${updated(d)}` } }],
      components: [row(home, btn("v:near:0", "Near Misses", "🟡", 1), btn("p:cats", "Categories", "🗂️"))] };
  }
  i = ((i % n) + n) % n;
  const x = list[i];
  const [icon, word] = x.grade === "A" ? ["🟢", "BUY"] : x.grade === "B" ? ["🟡", "VERIFY"] : ["🔴", "PASS"];
  const e = {
    author: { name: `${x.merchant || "Deal"} · ${x.delivery || "check delivery"}`.slice(0, 250) },
    title: `${icon} ${word} · ${sgbp(x.net)} net · ${pct(x.roi)} ROI`, url: x.url, color: C[x.grade],
    description: `**${x.title.slice(0, 200)}**${x.delivery_known === false ? "\n⚠️ Delivery unknown: profit is an item-only estimate, not verified net." : ""}${x.evidence_type && x.evidence_type !== "sold" ? "\nReference-only valuation, not exact sold evidence." : ""}${x.under_cap ? "" : "\n⚠️ Over cap or landed delivery cost not confirmed"}`,
    fields: [
      { name: "Buy", value: gbp(x.buy), inline: true }, { name: "Sell target", value: gbp(x.target), inline: true },
      { name: "Max landed cost (money gates only)", value: gbp(x.max_buy), inline: true },
      { name: "Net", value: sgbp(x.net), inline: true }, { name: "Worst case", value: sgbp(x.worst) + (x.worst_verified ? "" : " (est.)"), inline: true },
      { name: "Days to sell", value: x.days_to_sell != null ? `~${x.days_to_sell} days` : "No data yet", inline: true },
      { name: "Confidence", value: `${bar(x.confidence)} ${x.confidence}`, inline: false },
      { name: x.grade === "A" ? "Why" : "Why not BUY", value: x.why.length ? x.why.join(" · ") : "All 9 checks pass", inline: false },
      ...(x.intel?.retailer ? [{ name: "Retailer", value: x.intel.retailer.slice(0, 200), inline: false }] : []),
      ...(x.intel?.fake ? [{ name: "Fake risk", value: x.intel.fake.slice(0, 200), inline: false }] : []),
      ...(x.intel?.history ? [{ name: "Price history", value: x.intel.history.slice(0, 200), inline: true }] : []),
    ],
    footer: { text: `${FNAME[f] ?? f} · ${i + 1} of ${n} · last scan ${updated(d)}` },
  };
  if (x.thumb) e.thumbnail = { url: x.thumb };
  return { embeds: [e], components: [
    row(nav(i - 1, "Prev", "◀️", n < 2), nav(i + 1, "Next", "▶️", n < 2), btn(`plan:${f}:${i}`, "Full Plan", "📋", 1), btn(`dc:${f}:${i}`, "Calc", "🧮", 1), home),
    row(link(x.url, "Open Deal", "🛒"), link(x.ebay_sold, "eBay Sold", "📊"), link(x.vinted, "Vinted", "👕")),
  ] };
}

function planView(x) {
  const p = x.plan || {};
  return { embeds: [{ title: `📋 Trade plan · ${x.title.slice(0, 80)}`, color: C[x.grade], fields: [
    { name: "1 · Buy", value: `At or under **${gbp(x.max_buy)}** (deal ${gbp(x.buy)})`, inline: false },
    { name: "2 · List", value: `${gbp(p.list ?? x.target)}, then ${gbp(p.target ?? x.target)} by day 3`, inline: false },
    { name: "3 · Reprice", value: `Day 7: −5% and cross-list · Day 10: ${gbp(p.quick ?? x.target * 0.9)}`, inline: false },
    { name: "4 · Exit", value: x.worst_verified ? `Sell by day ${p.time_stop_day ?? 17} at ${gbp(p.floor ?? 0)} (verified floor)` : `If unsold by day ${p.time_stop_day ?? 17}${p.time_stop_rule ? " (house rule)" : ""}, take the best offer. Est. ${gbp(p.floor ?? 0)}, not verified, so worst case ${sgbp(x.worst)}.`, inline: false },
    ...(x.intel?.cashback ? [{ name: "Cashback", value: x.intel.cashback, inline: false }] : []),
    { name: "Where to sell", value: p.platforms || "eBay, Vinted", inline: false },
    { name: "Comps", value: (x.comp || "none").slice(0, 1000), inline: false },
  ], footer: { text: `Costs: eBay business standard fees incl 20% VAT, ${gbp(x.postage ?? 3.52)} home-delivery postage, £0.50 packaging, 3% returns` } }] };
}

// ---------- calculator ----------
const PLATFORMS = { ebay: "ebay_business", ebay_business: "ebay_business", "ebay business": "ebay_business", "ebay private": "ebay_private", ebay_private: "ebay_private",
  vinted: "vinted", depop: "depop", stockx: "stockx", fb: "fb", facebook: "fb", "fb cash": "fb_cash", fb_cash: "fb_cash", cash: "fb_cash", paypal: "fb" };
const ti = (id, label, value = "", req = true, ph = "") => row({ type: 4, custom_id: id, label, style: 1, required: req, value: value === "" ? undefined : String(value), placeholder: ph, max_length: 60 });
function calcModal(buy = "", sell = "", cat = "") {
  return { custom_id: "m:calc", title: "🧮 Profit Calculator", components: [
    ti("buy", "Landed buy cost incl delivery (£)", buy, true, "e.g. 25"), ti("sell", "Expected sell price (£)", sell, true, "e.g. 45"),
    ti("platform", "ebay, ebay private, vinted, depop, fb, fb cash", "ebay", true),
    ti("category", "Category: trainers, lego, gaming, tools, fragrance", cat, false, "optional"),
    ti("postage", "Postage you pay (£)", "", false, "optional, default by category (Evri home)") ] };
}
function calcView(buy, sell, platform, cat, postage) {
  if (![buy, sell].every(x => Number.isFinite(x) && x >= 0) || (postage != null && (!Number.isFinite(postage) || postage < 0))) return { content: "Enter finite nonnegative landed buy cost, sale price and postage." };
  const k = calc(buy, sell, platform, cat || "default", postage);
  const verdict = k.net >= 8 && (k.roi ?? 0) >= 40 ? ["🧮 Money gates only — not a BUY", C.INFO] : k.net > 0 ? ["🟡 Thin margin", C.B] : ["🔴 Loses money", C.R];
  return { embeds: [{ title: `${verdict[0]} · ${sgbp(k.net)} net · ${k.roi == null ? "—" : pct(k.roi)} ROI`, color: verdict[1],
    description: `Sell **${gbp(sell)}** on **${platform.replace("_", " ")}**${cat ? ` · ${cat}` : ""}`,
    fields: [
      { name: "Buy", value: gbp(buy), inline: true }, { name: "Platform fee", value: gbp(k.fee), inline: true }, { name: "Postage", value: gbp(k.postage), inline: true },
      { name: "Packaging", value: gbp(k.packaging), inline: true }, { name: "Returns (3%)", value: gbp(k.returns), inline: true }, { name: "Max landed cost (money gates only)", value: `**${gbp(k.maxBuy)}**`, inline: true },
      { name: "Margin bar", value: `${bar(Math.max(0, Math.min(100, (k.roi ?? 0))))} ${k.roi ?? 0}% (target 40%)`, inline: false },
    ], footer: { text: "Financial ceiling only, not approval · business fees incl 20% VAT · Vinted buyer pays postage · FB shipped = PayPal 2.9%+30p · Fees checked 2 Nov 2026" } }],
    components: [row(btn("p:calc", "New calculation", "🧮", 1), btn("p:home", "Menu", "🏠"))] };
}

// ---------- price check ----------
const priceModal = () => ({ custom_id: "m:price", title: "💷 Price Check", components: [ti("item", "Item name", "", true, "e.g. mario kart 8"), ti("buy", "Your buy price (£)", "", false, "optional")] });
async function priceView(q, buy, env) {
  const c = findComp(q, await getComps(env));
  const sold = `https://www.ebay.co.uk/sch/i.html?_nkw=${encodeURIComponent(q)}&LH_Sold=1&LH_Complete=1`;
  const vinted = `https://www.vinted.co.uk/catalog?search_text=${encodeURIComponent(q)}`;
  const links = row(link(sold, "eBay Sold", "📊"), link(vinted, "Vinted", "👕"));
  const again = row(btn("p:price", "Check another", "💷", 1), btn("p:home", "Menu", "🏠"));
  if (c && c.blocked) return { embeds: [{ title: "⚠️ Not priced: uncertain match", color: C.B, description: `Closest comp is **${c.blocked.slice(0, 80)}**, but your item looks like a different version (kids, bundle, used, edition or kit). Check eBay sold for the exact item.` }], components: [links, again] };
  if (!c) return { embeds: [{ title: `No sold-price data for “${q.slice(0, 60)}” yet`, color: C.INFO, description: "Try a shorter name (e.g. *mario kart 8*), or check sold listings below." }], components: [links, again] };
  const lo = parseFloat(c.low), hi = parseFloat(c.high);
  const eb = calc(buy ?? 0, lo, "ebay_business", c.category), vi = calc(buy ?? 0, lo, "vinted", c.category);
  const fields = [
    { name: "Legacy guide range — not exact sold evidence", value: `${gbp(lo)} – ${gbp(hi)}`, inline: true }, { name: "Max buy · eBay", value: gbp(eb.maxBuy), inline: true }, { name: "Max buy · Vinted", value: gbp(vi.maxBuy), inline: true },
  ];
  if (buy != null && !isNaN(buy)) fields.push({ name: `Net if you pay ${gbp(buy)}`, value: `eBay ${sgbp(eb.net)} (${pct(eb.roi)}) · Vinted ${sgbp(vi.net)} (${pct(vi.roi)})`, inline: false });
  fields.push({ name: "Evidence", value: `${c.sold_evidence}`.slice(0, 900), inline: false });
  const src = (c.source.match(/https?:\/\/\S+/) || [])[0];
  return { embeds: [{ title: `💷 ${c.match}`, description: `Category: **${c.category}**. Reference only: date, condition and exact variant may differ. Not a BUY signal. Use reviewed scanner evidence before buying.`, color: C.INFO, fields, footer: { text: "Hypothetical calculations from legacy guide; include inbound delivery; not approval" } }],
    components: [src ? row(link(sold, "eBay Sold", "📊"), link(vinted, "Vinted", "👕"), link(src, "Source", "🔗")) : links, again] };
}

// ---------- misc views ----------
const catsView = () => ({ embeds: [{ title: "🗂️ Browse by category", color: C.BRAND, description: "Pick a category to page through every priced deal in it." }],
  components: [row({ type: 3, custom_id: "cat", placeholder: "Choose a category…", options: CATS.map(([v, l, e]) => ({ label: l, value: v, emoji: { name: e } })) }), row(btn("p:home", "Menu", "🏠"))] });
const howView = () => ({ embeds: [{ title: "📘 How MONEYHUNTER works", color: C.BRAND, fields: [
  { name: "1 · Scan", value: "Best-effort 30-minute cron reads hotukdeals. New/rescan counts and coverage are reported; most products may need reviewed evidence." },
  { name: "2 · Strict matching", value: "A sold price only prices the exact same item. Kids' sizes, bundles, multipacks, pre-orders, used/refurbished, other editions, kits vs body-only and other bottle sizes are never priced." },
  { name: "3 · Count every cost", value: "eBay standard business fees incl 20% VAT (promotions/surcharges extra), home-delivery postage by category, £0.50 packaging and a 3% returns allowance." },
  { name: "4 · Grade", value: "🟢 **BUY**: all evidence, offer, availability and money checks pass · 🟡 **VERIFY**: profit works on estimates, check eBay sold first · 🔴 **PASS**: fails a check. Sold prices older than 30 days never give BUY or VERIFY; expired deals never alert." },
  { name: "5 · Max buy", value: "Financial landed-cost ceiling for £8 net/40% ROI; not permission to buy without the evidence gates." },
  { name: "Honest limits", value: "Sold prices are averages, not guarantees. Always check eBay sold before buying. Not financial advice." },
] }], components: [row(btn("p:home", "Menu", "🏠"))] });

const isAdmin = i => (BigInt(i.member?.permissions ?? "0") & 0x20n) !== 0n;
const fieldVals = i => { const o = {}; for (const r of i.data.components || []) for (const c of (r.components || (r.component ? [r.component] : []))) o[c.custom_id] = c.value ?? c.values?.[0]; return o; };
const num = v => (v == null || v === "" ? null : parseFloat(String(v).replace(/[£,\s]/g, "")));

async function handleCommand(i, env) {
  switch (i.data.name) {
    case "menu": { let d = null; try { d = await getDeals(env); } catch {} return msg(panel(d)); }
    case "deal": { const d = await getDeals(env); const l = filterDeals(d.deals, "top"); return msg(dealView(d, l.length ? l : filterDeals(d.deals, "near"), l.length ? "top" : "near", 0)); }
    case "setup": {
      if (!isAdmin(i)) return msg({ content: "Only members with **Manage Server** can post the panel." });
      let d = null; try { d = await getDeals(env); } catch {} return msg(panel(d), false);
    }
    case "price": return msg(await priceView(String(opt(i, "item")), opt(i, "buy"), env));
    case "calc": return msg(calcView(opt(i, "buy"), opt(i, "sell"), opt(i, "platform") ?? "ebay_business", opt(i, "category") ?? "", null));
    case "scan": return msg({ content: "⚡ Manual scan is coming soon. Cron targets 30 minutes but can be delayed or dropped." });
    case "help": return msg(howView());
    case "logflip": return modal(CM.flipModal());
    case "soldprice": return modal(CM.compModal());
    case "leaderboard": return msg({ embeds: [CM.lbEmbed(await CM.leaderboard(env))] });
    case "review": {
      if (!isAdmin(i)) return msg({ content: "Only members with **Manage Server** can review submissions." });
      const p = await CM.pendingComps(env);
      return msg({ embeds: [{ title: `🧾 Latest sold-price submissions (${p.length})`, color: C.INFO,
        description: p.map(x => `• **${x.item}** £${x.price} · ${x.date} · ${x.condition || "?"} · [listing](${x.link}) · by ${x.name}`).join("\n").slice(0, 4000) || "None yet." }] });
    }
  }
  return msg({ content: "Unknown command." });
}

async function handleComponent(i, env) {
  const id = i.data.custom_id;
  const fromPanel = !(i.message?.flags & EPH);       // clicks on the shared panel open a private view
  const show = data => (fromPanel ? msg(data) : upd(data));
  const [k, f, n] = id.split(":");
  if (id === "p:home") { let d = null; try { d = await getDeals(env); } catch {} return fromPanel ? msg(panel(d)) : upd(panel(d)); }
  if (id === "p:calc") return modal(calcModal());
  if (id === "p:price") return modal(priceModal());
  if (id === "p:cats") return show(catsView());
  if (id === "p:how") return show(howView());
  if (id === "fl:open") return modal(CM.flipModal());
  if (id === "sc:open") return modal(CM.compModal());
  if (id === "lb:show") return msg({ embeds: [CM.lbEmbed(await CM.leaderboard(env))] });
  if (id === "p:scan") return msg({ content: "⚡ **Scan Now is coming soon.** Cron targets 30 minutes but can be delayed or dropped." });
  if (id === "cat") { const d = await getDeals(env); const c = i.data.values[0]; return show(dealView(d, filterDeals(d.deals, c), c, 0)); }
  const d = await getDeals(env), list = filterDeals(d.deals, f), x = list[((+n % (list.length || 1)) + list.length) % (list.length || 1)];
  if (k === "v") return show(dealView(d, list, f, +n));
  if (!x) return msg({ content: "That deal has gone from the latest scan. Open the menu again." });
  if (k === "plan") return msg(planView(x));
  if (k === "dc") return modal(calcModal(x.buy, x.target, x.category === "gaming" ? "gaming" : x.category));
  return msg({ content: "Unknown button." });
}

async function handleModal(i, env, ctx) {
  const v = fieldVals(i);
  if (i.data.custom_id === "m:calc") {
    const buy = num(v.buy), sell = num(v.sell);
    const platform = PLATFORMS[String(v.platform || "ebay").trim().toLowerCase()];
    if (buy == null || sell == null || isNaN(buy) || isNaN(sell)) return msg({ content: "Please enter numbers for buy and sell, e.g. 25 and 45." });
    if (!platform) return msg({ content: "Platform not recognised. Use: ebay, ebay private, vinted, depop, stockx or fb." });
    return msg(calcView(buy, sell, platform, String(v.category || "").trim().toLowerCase(), num(v.postage)));
  }
  if (i.data.custom_id === "m:flip") {
    const r = await CM.logFlip(i, v, env);
    if (r.error) return msg({ content: r.error });
    if (r.net >= 20 && i.channel_id !== env.WINS_CHANNEL) ctx.waitUntil(CM.postToChannel(env, env.WINS_CHANNEL, { embeds: [{ ...r.embed, title: "🏆 " + r.embed.title }] }));
    return msg({ embeds: [r.embed] }, false);
  }
  if (i.data.custom_id === "m:comp") {
    const r = await CM.submitComp(i, v, env);
    return msg({ content: r.error ?? `✅ Thanks! Sold price £${r.p.toFixed(2)} saved for review.` });
  }
  if (i.data.custom_id === "m:price") return msg(await priceView(String(v.item || "").trim(), num(v.buy), env));
  return msg({ content: "Unknown form." });
}

export default {
  async fetch(req, env, ctx) {
    const url = new URL(req.url || "https://x/");
    if (req.method === "GET" && url.pathname === "/api/leaderboard") return json({ top: await CM.leaderboard(env, 25) });
    if (req.method !== "POST") return new Response("MONEYHUNTER bot is running", { status: 200 });
    const body = await req.text();
    if (!(await verifyDiscord(req, body, env.DISCORD_PUBLIC_KEY))) return new Response("invalid request signature", { status: 401 });
    const i = JSON.parse(body);
    try {
      if (i.type === 1) return json({ type: 1 });
      if (i.type === 2) return await handleCommand(i, env);
      if (i.type === 3) return await handleComponent(i, env);
      if (i.type === 5) return await handleModal(i, env, ctx);
      return msg({ content: "Unsupported." });
    } catch (e) { return msg({ content: "⚠️ Something went wrong: " + String(e.message).slice(0, 150) }); }
  },
};
export const _test = { flipPanel: CM.flipPanel, compsPanel: CM.compsPanel, panel, dealView, calcView, filterDeals, planView, catsView };

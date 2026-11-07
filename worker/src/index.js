// MONEYHUNTER Discord bot: HTTP interactions on Cloudflare Workers (no gateway), button-driven UI.
import { calc, parseCsv, findComp, findReviewed, gbp, verifyDiscord } from "./logic.js";
import * as CM from "./community.js";
import { capture, readCapture, publicCapture } from "./capture.js";

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

async function getDeals(env) {
  const r = await fetch(env.DEALS_URL, { cf: { cacheTtl: 60 } });
  if (!r.ok) throw new Error("deals feed " + r.status);
  const d = {...await r.json()};
  d.scanner_stale = !Number.isFinite(Date.parse(d.generated_utc)) || Date.now()-Date.parse(d.generated_utc) > 90*60000;
  try { d.capture = publicCapture(await readCapture(env)); d.review_queue = mergeResearch(d.review_queue ?? [], d.capture); }
  catch { d.capture = {status:"capture_state_unavailable",items:[]}; }
  return d;
}
const london = value => Number.isFinite(Date.parse(value)) ? new Date(value).toLocaleString("en-GB",{timeZone:"Europe/London"})+" London" : "not observed";
function researchCost(price, category, goal) {
  let lo=0,hi=price*4+50;
  for(let i=0;i<50;i++) { const mid=(lo+hi)/2; if(calc(price,mid,"ebay_business",category).net<goal) lo=mid; else hi=mid; }
  return Math.ceil(hi*100)/100;
}
function mergeResearch(queue, snapshot) {
  const items=new Map(queue.map(x=>[x.url,x]));
  for(const x of snapshot.items ?? []) {
    const old=items.get(x.url);
    if(old && old.item_price===x.price && old.title===x.title) { items.set(x.url,{...old,capture_last_seen:x.last_seen}); continue; }
    items.set(x.url,{title:x.title,url:x.url,category:x.category,item_price:x.price,landed_cost:null,
      breakeven_sell:researchCost(x.price,x.category,0),sell_for_minimum_profit:researchCost(x.price,x.category,Math.max(8,x.price*.4)),
      cost_basis:"item-only lower bound; delivery unknown",first_seen:x.first_seen,capture_last_seen:x.last_seen,
      priority:15,blockers:["No reviewed exact sold observations","Delivery unknown","Retailer stock/price and exact variant unverified"],
      sold_search:`https://www.ebay.co.uk/sch/i.html?_nkw=${encodeURIComponent(x.title)}&LH_Sold=1&LH_Complete=1`});
  }
  return [...items.values()].sort((a,b)=>(b.priority??0)-(a.priority??0) || String(b.capture_last_seen??b.first_seen??"").localeCompare(String(a.capture_last_seen??a.first_seen??""))).slice(0,100);
}
function freshAsking(x) {
  const age=Date.now()-Date.parse(x?.observed_at);
  return x?.kind==="active_ask" && age>=0 && age<6*3600000 && Number.isInteger(x.sample_count) && x.sample_count>0 &&
    [x.listed_total_low,x.listed_total_median,x.listed_total_high].every(v=>Number.isFinite(v)&&v>0);
}
function askFields(x) {
  if(!freshAsking(x)) return [];
  return [{name:"Indicative NEW listed totals · NOT sold or a resale forecast",value:`${gbp(x.listed_total_low)}–${gbp(x.listed_total_high)} observed asking range; median ${gbp(x.listed_total_median)}. ${x.sample_count} exact-title shipped samples. Buyer-only fees may be additional.`,inline:false},
    {name:"Ask provenance / limits",value:`${x.query} · ${london(x.observed_at)} · ${x.status}. No velocity or cash floor inferred; title matches are not independent verification.`,inline:false}];
}
function estimateFields(m, buy = null, landedConfirmed = false) {
  const age=Date.now()-Date.parse(m?.observed_at);
  if(!m || m.model!=="competitor-asks-v1" || !Number.isFinite(age) || age<0 || age>6*3600000) return [];
  const custom=buy!=null && Number.isFinite(buy) && buy>0 ? calc(buy,m.estimated_resale,"ebay_business",m.category || "default") : null;
  const profit=custom ? `${sgbp(custom.net)}${landedConfirmed ? ` / ${pct(custom.roi)} ROI at your supplied landed cost` : " BEFORE unknown inbound delivery; actual net/ROI unknown"}` : m.delivery_known ? `${sgbp(m.net)} / ${pct(m.roi)} ROI at ${gbp(m.landed_cost)} landed` : `Up to ${sgbp(m.net_before_unknown_delivery)} before UNKNOWN inbound delivery; actual net/ROI unknown`;
  return [{name:m.signal,value:`Estimated resale **${gbp(m.estimated_resale)}**; suggested listing ${gbp(m.suggested_listing)}. Model range ${gbp(m.estimated_range[0])}–${gbp(m.estimated_range[1])}. Not sold or guaranteed.`,inline:false},
    {name:"Estimated net / ROI",value:profit,inline:false},
    {name:"Competition, model and confidence",value:`${m.sample_count} seller-deduplicated asks / ${m.seller_count} known sellers; ${m.confidence} confidence. Current lowest delivered competition ${gbp(m.competition_low)}. Quick-sale model ${gbp(m.quick_sale_model)}; speed NOT measured. ${m.discount_note}`,inline:false},
    {name:"Max landed buy / costs",value:`${gbp(m.max_landed_buy)} ceiling for £8 net + 40% ROI. Fee ${gbp(m.fees)}, outbound ${gbp(m.outbound_postage)}, packaging ${gbp(m.packaging)}, returns ${gbp(m.returns_allowance)}. Check actual checkout delivery/stock.`,inline:false},
    {name:"Checks and provenance",value:`${m.checks.join(" · ")}\nObserved ${london(m.observed_at)}. Regular price not established. ${m.acquisition_excluded} known acquisition listings excluded.`,inline:false}];
}
function estimateLinks(m) { return (m?.sources ?? []).slice(0,3).map((x,i)=>link(x.url,`Competitor ${i+1}`,"🔗")); }
async function getComps(env) { const r = await fetch(env.COMPS_URL, { cf: { cacheTtl: 300 } }); if (!r.ok) throw new Error("comps " + r.status); return parseCsv(await r.text()); }
const updated = d => d.generated_utc.replace("T", " ").slice(0, 16) + " UTC";

// ---------- control panel ----------
function panel(d) {
  const s = d?.stats;
  const status = s ? `**${s.A}** buy · **${s.B}** verify · **${s.R}** passed · **${s.scanned}** scanned\nLast scan ${updated(d)}${d.scanner_stale ? " · ⚠️ STALE (>90 minutes)" : ""}` : "Scan data loading…";
  return {
    embeds: [{
      author: { name: "MONEYHUNTER" }, title: "💰 Control Panel", color: C.BRAND,
      description: "Research under-£60 offers using conservative costs and reviewed sold evidence.\nClick a button below. Results are private to you.",
      fields: [{ name: "📡 Scanner grading status", value: status },
        { name: "Independent RSS capture (research only)", value: d?.capture ? `${d.capture.status}${d.capture.stale ? " · STALE (>30 minutes or never captured)" : ""} · ${d.capture.items?.length ?? 0} retained offers · last attempt ${london(d.capture.last_attempt)}. No BUY grading or resale prices inferred.` : "Awaiting capture status" },
        { name: "Resale estimates / verified pricing", value: d?.pricing_status ? `${d.pricing_status.ask_estimated_products ?? 0} products with competitor-based resale estimates · ${d.pricing_status.estimated_opportunities ?? 0} estimated CHECK opportunities. Separately: ${d.pricing_status.products} sold-valued products / ${d.pricing_status.sold_observations} sold observations. Estimates are not verified BUYs.` : "Awaiting first migrated scheduled scan; legacy guide is not sold evidence." }],
      footer: { text: "30-minute queued scan target; inspect last scan · Estimates are not guarantees" },
    }],
    components: [
      row(btn("v:top:0", "Verified Deals", "🟢", 3), btn("v:near:0", "Near Misses", "🟡", 1), btn("p:cats", "Categories", "🗂️")),
      row(btn("p:calc", "Profit Calculator", "🧮", 1), btn("p:price", "Price Check", "💷", 1), btn("research:0", "Resale Estimates", "🔎", 1)),
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
      { name: x.grade === "A" ? "Why" : "Why not BUY", value: x.why.length ? x.why.join(" · ") : "All evidence, offer and money checks pass", inline: false },
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
    { name: "1 · Financial ceiling (not approval)", value: `At or under **${gbp(x.max_buy)}** (deal ${gbp(x.buy)})`, inline: false },
    { name: "2 · List", value: `${gbp(p.list ?? x.target)}, then ${gbp(p.target ?? x.target)} by day 3`, inline: false },
    { name: "3 · Reprice", value: `Day 7: −5% and cross-list · Day 10: ${gbp(p.quick ?? x.target * 0.9)}`, inline: false },
    { name: "4 · Exit", value: x.worst_verified ? `Sell by day ${p.time_stop_day ?? 17} at ${gbp(p.floor ?? 0)} (verified floor)` : `If unsold by day ${p.time_stop_day ?? 17}${p.time_stop_rule ? " (house rule)" : ""}, take the best offer. Est. ${gbp(p.floor ?? 0)}, not verified, so worst case ${sgbp(x.worst)}.`, inline: false },
    ...(x.intel?.cashback ? [{ name: "Cashback", value: x.intel.cashback, inline: false }] : []),
    { name: "Where to sell", value: p.platforms || "eBay, Vinted", inline: false },
    { name: "Comps", value: (x.comp || "none").slice(0, 1000), inline: false },
  ], footer: { text: `Costs: eBay business standard fees incl 20% VAT, ${gbp(x.postage ?? 3.52)} home-delivery postage, £0.50 packaging, 3% returns` } }] };
}

// Prioritised public research tasks, not purchasable recommendations or sold valuations.
function researchView(d, index = 0) {
  const list = d.review_queue ?? [];
  if (!list.length) return { embeds: [{title:"Research watchlist",color:C.INFO,description:"No prioritised candidates in this export yet. A migrated scheduled scan must publish the queue. No BUY is implied."}],components:[row(btn("p:home","Menu","🏠"))] };
  const i = ((index % list.length) + list.length) % list.length, x = list[i];
  const fields = [
    {name:"Item / landed cost",value:`${gbp(x.item_price)} / ${x.landed_cost == null ? "unknown (delivery missing)" : gbp(x.landed_cost)}`,inline:true},
    {name:"Hypothetical breakeven / required resale",value:`${gbp(x.breakeven_sell)} / ${gbp(x.sell_for_minimum_profit)}. ${x.cost_basis}. These are required prices, NOT market valuations.`,inline:false},
    {name:"Evidence and availability blockers",value:(x.blockers ?? ["Exact evidence needed"]).join(" · ").slice(0,1000),inline:false},
    ...estimateFields(x.ask_estimate),
    ...askFields(x.ask_context),
    ...(x.ask_context && !freshAsking(x.ask_context) ? [{name:"Automatic asking research",value:`${x.ask_context.status}; ${x.ask_context.sample_count ?? 0} usable samples. Rejections: ${JSON.stringify(x.ask_context.rejected ?? {})}. No fresh asking range can be shown.`,inline:false}] : []),
    ...(!x.ask_context && x.ask_status ? [{name:"Automatic asking research",value:x.ask_status,inline:false}] : []),
    ...(x.capture_last_seen ? [{name:"Independent RSS observation",value:`Last seen ${london(x.capture_last_seen)}. Feed presence does not verify retailer stock or checkout price.`,inline:false}] : [])];
  return {embeds:[{title:`${x.ask_estimate ? "ASK-BASED ESTIMATE" : "RESEARCH ONLY"} · ${x.title}`.slice(0,250),url:x.url,color:C.INFO,description:"Competitor-based resale estimates are separate from verified BUY grades. Check exact physical variant, retailer stock/checkout price and delivery. Estimates are not guaranteed sales or measured turnover.",fields,footer:{text:`Priority ${x.priority} · ${i+1} of ${list.length} · last scan ${updated(d)}`}}],components:[row(btn(`research:${i-1}`,"Prev","◀️"),btn(`research:${i+1}`,"Next","▶️"),btn("p:home","Menu","🏠")),row(link(x.url,"Offer source","🔗"),...estimateLinks(x.ask_estimate))]};
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
const priceModal = () => ({ custom_id: "m:price", title: "💷 Price Check", components: [ti("item", "Item name", "", true, "e.g. mario kart 8"), ti("buy", "Landed cost INCLUDING delivery (£)", "", false, "optional")] });
async function priceView(q, buy, env, landedConfirmed = false) {
  const sold = `https://www.ebay.co.uk/sch/i.html?_nkw=${encodeURIComponent(q)}&LH_Sold=1&LH_Complete=1`;
  const vinted = `https://www.vinted.co.uk/catalog?search_text=${encodeURIComponent(q)}`;
  const links = row(link(sold, "eBay Sold", "📊"), link(vinted, "Vinted", "👕"));
  const again = row(btn("p:price", "Check another", "💷", 1), btn("p:home", "Menu", "🏠"));
  let pricing;
  try { pricing = await getDeals(env); }
  catch { return { content: "Pricing feed unavailable. No fresh competitor estimate can be shown right now.", components: [links, again] }; }
  const reviewed = findReviewed(q, pricing.pricing_catalog);
  if (reviewed?.blocked) return { embeds: [{ title: "Exact variant needed before pricing", color: C.B,
    description: `${reviewed.reason}.\nIdentity: ${Object.entries(reviewed.identity ?? {}).map(([k,v]) => `${k}: ${v}`).join(" · ").slice(0,850)}. Not a BUY.` }], components: [links, again] };
  if (reviewed) {
    const fields = [
      { name: "Observed sold gross · lower quartile / median", value: `${gbp(reviewed.low)} / ${gbp(reviewed.high)}`, inline: true },
      { name: "Actual sample / oldest supporting sale", value: `${reviewed.sample_count} sales · ${reviewed.sold_as_of}`, inline: true },
      { name: "Exact identity", value: Object.entries(reviewed.identity).map(([k,v]) => `${k}: ${v}`).join(" · ").slice(0,900), inline: false },
      { name: "Days to sell", value: reviewed.days_to_sell == null ? "Not measured" : `Observed median ${reviewed.days_to_sell} days; not a forecast`, inline: true }];
    if (buy != null && Number.isFinite(buy) && buy >= 0) {
      const k = calc(buy, reviewed.low, "ebay_business", reviewed.category);
      fields.push({ name: "Hypothetical net at lower-quartile gross", value: `${sgbp(k.net)} at landed cost ${gbp(buy)}. Money-only ceiling ${gbp(k.maxBuy)}; not approval.`, inline: false });
    }
    const source = reviewed.sold_sources?.find(x => /^https:\/\//.test(x.url ?? ""));
    return { embeds: [{ title: `Reviewed sold research · ${reviewed.match}`.slice(0,250), color: C.INFO,
      description: `${reviewed.price_basis}. ${reviewed.sample_count < 5 ? "⚠️ Fewer than five observations: too little evidence for a reliable resale estimate. " : "Sample evidence, not a guaranteed future sale price. "}No current offer, cash floor or BUY is implied.`, fields,
      footer: { text: "Sold date is separate from observed/reviewed date; active asks never refresh it" } }], components: [source ? row(link(source.url, "Actual sold source", "🔗"), link(sold, "Research sold", "📊")) : links, again] };
  }
  const cleanAskQuery = value => String(value).toLowerCase().replace(/\b(new|sealed)\b/g,"").replace(/[^a-z0-9]+/g," ").trim();
  const numbers=[...new Set(String(q).match(/(?<!\d)\d{5,6}(?!\d)/g) ?? [])];
  const unsafe=/\b(used|refurb|bundle|multipack|sticker|instructions|manual|parts|digital|download|minifig|missing)\b/i.test(q);
  const asking = !unsafe && (pricing.asking_catalog ?? []).find(x=>freshAsking(x) && (cleanAskQuery(x.query)===cleanAskQuery(q) || (/lego/i.test(q) && numbers.length===1 && x.query===`LEGO ${numbers[0]}`)));
  if(asking) {
    const entry=(pricing.review_queue ?? []).find(x=>x.ask_estimate?.query===asking.query);
    return {embeds:[{title:`Estimated resale · ${asking.query}`.slice(0,250),color:C.INFO,
      description:"Current exact-title NEW competitor offers including quoted shipping support this conservative MODEL estimate. Not sold data or a guaranteed sale. The cheapest credible competition caps the estimate even when discounted.",fields:[...estimateFields(entry?.ask_estimate,buy,landedConfirmed),...askFields(asking)]}],components:[row(...estimateLinks(entry?.ask_estimate),link(sold,"Sold research","📊")),again]};
  }
  const c = findComp(q, await getComps(env));
  if (c && c.blocked) return { embeds: [{ title: "⚠️ Not priced: uncertain match", color: C.B, description: `Closest comp is **${c.blocked.slice(0, 80)}**, but your item looks like a different version (kids, bundle, used, edition or kit). Check eBay sold for the exact item.` }], components: [links, again] };
  if (!c) return { embeds: [{ title: `No exact competitor estimate for “${q.slice(0, 60)}” yet`, color: C.INFO, description: "Try the exact game/platform or LEGO set number. Ambiguous variants are not guessed." }], components: [links, again] };
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
  { name: "Ask-based CHECK opportunities", value: "Five independent sellers and supported low competition can support a separate estimated opportunity when net/ROI/cap and delivery checks pass. This is not verified BUY or measured fast turnover." },
  { name: "5 · Max buy", value: "Financial landed-cost ceiling for £8 net/40% ROI; not permission to buy without the evidence gates." },
  { name: "Honest limits", value: "Competitor-ask models estimate resale, not sold prices or guaranteed turnover. Check actual stock, delivery and current competition. Verified BUY still requires its separate evidence gates." },
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
  if (k === "research") return show(researchView(await getDeals(env), Number(f) || 0));
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
  if (i.data.custom_id === "m:price") return msg(await priceView(String(v.item || "").trim(), num(v.buy), env, true));
  return msg({ content: "Unknown form." });
}

export default {
  async scheduled(controller, env, ctx) {
    // Existing KV + four approved public RSS feeds only. No Discord call is reachable.
    await capture(env);
  },
  async fetch(req, env, ctx) {
    const url = new URL(req.url || "https://x/");
    if (req.method === "GET" && url.pathname === "/api/research-capture") {
      try { return json(publicCapture(await readCapture(env))); }
      catch { return json({error:"Public capture unavailable"},503); }
    }
    if (req.method === "GET" && url.pathname === "/api/health") {
      try {
        const d = await getDeals(env);
        return json({service:"moneyhunter-bot",contract_version:4,generated_utc:d.generated_utc,scanner_stale:d.scanner_stale,
          capture:d.capture ? {...d.capture,items:undefined,retained_offers:d.capture.items?.length ?? 0} : null,
          pricing_status:d.pricing_status ?? {blocker:"Awaiting first migrated scan; legacy guide is not sold evidence",products:0,sold_observations:0,automatic_sold_feed:false},
          sources:d.stats?.sources ?? null,review_candidates:d.review_queue?.length ?? 0});
      } catch { return json({service:"moneyhunter-bot",contract_version:4,error:"Public scan feed unavailable"},503); }
    }
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
export const _test = { flipPanel: CM.flipPanel, compsPanel: CM.compsPanel, panel, dealView, calcView, filterDeals, planView, catsView, researchView, mergeResearch, freshAsking, askFields, estimateFields, priceView };

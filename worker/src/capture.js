import {nonphysical,normalizeProduct} from "./product-format.js";
// Original bounded public-RSS capture, independent of GitHub grading jobs.
// Conditional caching / source-item persistence concepts: docs/OPEN_SOURCE_RESEARCH.md.
// NO Discord, eBay, retailer HTML, credentials, grades, sold prices or public write route.
export const CAPTURE_KEY = "research:capture:v1";
export const FEEDS = [
  ["lego", "tag/lego"], ["gaming", "tag/nintendo-switch"],
  ["gaming", "tag/playstation"], ["gaming", "tag/xbox"],
];
const DAY = 86400000, MAX_BYTES = 524288, MAX_ITEMS = 300;
const stamp = n => new Date(n).toISOString();
const text = s => String(s ?? "").trim().replace(/^<!\[CDATA\[([\s\S]*)\]\]>$/, "$1")
  .replace(/<[^>]*>/g, " ").replace(/&#(x[0-9a-f]+|\d+);/gi, (_, n) => {
    const v = n[0].toLowerCase() === "x" ? parseInt(n.slice(1),16) : Number(n);
    return v > 0 && v <= 0x10ffff ? String.fromCodePoint(v) : " ";
  }).replace(/&pound;/g,"£").replace(/&amp;/g,"&").replace(/&quot;/g,'"').replace(/&apos;/g,"'")
  .replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/\s+/g," ").trim();
const tag = (xml, name) => (xml.match(new RegExp(`<${name}(?:\\s[^>]*)?>([\\s\\S]*?)<\\/${name}>`,"i")) ?? [])[1] ?? "";
const attr = (xml, name) => text((xml.match(new RegExp(`(?:^|\\s)${name}=["']([^"']*)["']`,"i")) ?? [])[1]);
export function productImage(value) {
  try {
    const u = new URL(String(value ?? ""));
    if (u.protocol !== "https:" || u.username || u.password || u.port || !["images.hotukdeals.com","static.pepper.com","i.ebayimg.com"].includes(u.hostname) || u.pathname === "/" || /logo|avatar|placeholder|banner|\.svg$/i.test(u.pathname)) return "";
    u.hash="";
    return u.href;
  } catch { return ""; }
}
function feedImage(body) {
  const media = [...body.matchAll(/<(?:media:(?:content|thumbnail)|enclosure)\b([^>]*)/gi)].map(m=>attr(m[1],"url"));
  const description=tag(body,"description").replace(/&lt;/g,"<").replace(/&gt;/g,">").replace(/&quot;/g,'"');
  const imgs=[...description.matchAll(/<img\b([^>]*)/gi)].map(m=>attr(m[1],"src"));
  return [...media,...imgs].map(productImage).find(Boolean) ?? "";
}
export function price(s) {
  const values = [...text(s).matchAll(/£\s*([\d,]+(?:\.\d{1,2})?)(?![\d.])/g)].map(m => Number(m[1].replace(/,/g,"")));
  const unique = [...new Set(values)];
  return unique.length === 1 && Number.isFinite(unique[0]) && unique[0] > 0 ? unique[0] : null;
}
const digitalStores = new Set(["eneba","loaded","cdkeys","cdkeys.com","steam","gog","gog.com","xbox","microsoft","nintendo eshop","playstation store"]);
function physicalCandidate(x) {
  if(nonphysical(x))return false;
  if (/\b(game pass|pc windows|xbox store|nintendo eshop|playstation store|steam|cd ?key|game key|gift card|digital|download|dlc|code in a box)\b/i.test(x.title)) return false;
  return !(x.category === "gaming" && digitalStores.has(String(x.merchant).trim().toLowerCase()) && !/\b(controller|headset|keyboard|mouse|console|racing wheel)\b/i.test(x.title));
}
export function parseFeed(xml, category, feed, now = Date.now()) {
  if (xml.length > MAX_BYTES || /<!DOCTYPE|<!ENTITY/i.test(xml) || !/<rss\b/i.test(xml) || !/<\/rss>\s*$/i.test(xml) || !/<channel[>\s]/i.test(xml)) throw new Error("invalid_or_oversize_rss");
  if ((xml.match(/<item[>\s]/gi) ?? []).length !== (xml.match(/<\/item>/gi) ?? []).length) throw new Error("truncated_rss");
  const result = [];
  for (const item of [...xml.matchAll(/<item(?:\s[^>]*)?>([\s\S]*?)<\/item>/gi)].slice(0,20)) {
    const body = item[1], title = text(tag(body,"title")).replace(/^-?\d+°\s*-\s*/,"").slice(0,200);
    const desc = text(tag(body,"description")).slice(0,1200);
    let url;
    try { url = new URL(text(tag(body,"link"))); } catch { continue; }
    if (url.protocol !== "https:" || url.username || url.password || url.hostname !== "www.hotukdeals.com" || !url.pathname.startsWith("/deals/")) continue;
    url.search = ""; url.hash = "";
    const merchant = (body.match(/<pepper:merchant\b([^>]*)/i) ?? [])[1] ?? "";
    const amount = price(attr(merchant,"price")) ?? price(desc);
    const pub = Date.parse(text(tag(body,"pubDate")));
    if (!Number.isFinite(pub) || now - pub > 7*DAY || pub-now > DAY) continue;
    if (!title || amount == null || amount > 60 || /in.?store only|in store|instore|collection only|c&c only|click (?:&|and) collect only|limited stores|local only|pre.?order|out of stock|sold out|digital|download|dlc|code in a box/i.test(title+" "+desc)) continue;
    if (category === "lego" && !/\b(ps[45]|playstation|xbox|nintendo switch)\b/i.test(title) && (!/\blego\b/i.test(title) || !/\b\d{5,6}\b/.test(title))) continue;
    const actualCategory = /\blego\b/i.test(title) && /\b\d{5,6}\b/.test(title) ? "lego" : category;
    const offer = normalizeProduct({thumb:feedImage(body),title,url:url.href,price:amount,category:actualCategory,merchant:attr(merchant,"name").slice(0,80),
      feed,published_at:stamp(pub),last_seen:stamp(now),kind:"feed_offer_only",availability:"unverified",
      inbound_delivery:null,online_eligible:true,desc:"",delivery:"Delivery cost and current stock unverified"});
    if(physicalCandidate(offer)) result.push(offer);
  }
  return result;
}
async function boundedText(response) {
  const reader = response.body.getReader(), parts = []; let bytes = 0;
  try {
    while (true) {
      const {done,value} = await reader.read(); if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_BYTES) { await reader.cancel(); throw new Error("oversize_rss"); }
      parts.push(value);
    }
  } finally { reader.releaseLock(); }
  const joined = new Uint8Array(bytes); let offset = 0;
  for (const p of parts) { joined.set(p,offset); offset += p.length; }
  return new TextDecoder().decode(joined);
}
export async function readCapture(env) {
  const data = await env.MH?.get(CAPTURE_KEY,"json");
  if (!data) return {schema_version:1,kind:"feed_capture_only",status:"awaiting_first_capture",items:[],feeds:{}};
  if (data.schema_version !== 1 || !Array.isArray(data.items) || !data.feeds) throw new Error("invalid_capture_state");
  return data;
}
export function publicCapture(data, now = Date.now()) {
  return {schema_version:1,kind:"feed_capture_only",status:data.status,
    last_attempt:data.last_attempt ?? null,last_success:data.last_success ?? null,
    target_minutes:10,grades_computed:false,
    stale:!Number.isFinite(Date.parse(data.last_attempt)) || now-Date.parse(data.last_attempt)>30*60000,
    feeds:Object.fromEntries(Object.entries(data.feeds).map(([k,v]) => [k,{status:v.status,last_success:v.last_success ?? null,error:v.error ?? null,paused:v.paused ?? false}])),
    items:data.items.map(normalizeProduct).filter(x => physicalCandidate(x) && now-Date.parse(x.published_at) <= 7*DAY && now-Date.parse(x.last_seen) <= 7*DAY)};
}
export async function capture(env, now = Date.now(), fetcher = fetch) {
  if (!env.MH) throw new Error("existing_KV_binding_required");
  const state = await readCapture(env), feeds = {}, incoming = [];
  await Promise.all(FEEDS.map(async ([category,path]) => {
    const old = state.feeds[path] ?? {};
    if (old.paused) { feeds[path] = old; return; } // no automatic retry after access challenge
    if (Date.parse(old.retry_after) > now) { feeds[path] = old; return; }
    try {
      const headers = {"User-Agent":"moneyhunter/0.1 (+personal deal scanner)"};
      if (old.etag) headers["If-None-Match"] = old.etag;
      if (old.modified) headers["If-Modified-Since"] = old.modified;
      const r = await fetcher("https://www.hotukdeals.com/rss/"+path,{headers,redirect:"manual",signal:AbortSignal.timeout(10000)});
      if (r.status === 304 && Array.isArray(old.rows)) {
        const rows = old.rows.map(x => ({...x,last_seen:stamp(now)}));
        feeds[path] = {...old,status:"not_modified",last_success:stamp(now),error:null,rows}; incoming.push(...rows); return;
      }
      if (!r.ok) {
        feeds[path] = {...old,status:"failed",error:`HTTP ${r.status}`,paused:[401,403].includes(r.status),
          retry_after:r.status === 429 ? stamp(now+3600000) : null}; return;
      }
      const xml = await boundedText(r);
      if (/captcha|pardon our interruption|verify you are human|access denied/i.test(xml)) {
        feeds[path] = {...old,status:"blocked",error:"Access verification required; paused for operator review",paused:true}; return;
      }
      const rows = parseFeed(xml,category,path,now);
      feeds[path] = {status:"ok",last_success:stamp(now),error:null,etag:r.headers.get("etag"),modified:r.headers.get("last-modified"),rows}; incoming.push(...rows);
    } catch (e) { feeds[path] = {...old,status:"failed",error:e.name === "TimeoutError" ? "timeout" : `${e.name}: ${String(e.message).replace(/https?:\/\/\S+/g,"[public RSS URL]").slice(0,100)}`}; }
  }));
  const byUrl = new Map(state.items.map(x => [x.url,x]));
  for (const x of incoming) {
    const old = byUrl.get(x.url);
    byUrl.set(x.url,{...x,first_seen:old?.first_seen ?? stamp(now),
      price_changed_at:old && old.price !== x.price ? stamp(now) : old?.price_changed_at ?? null});
  }
  state.items = [...byUrl.values()].filter(x => physicalCandidate(x) && now-Date.parse(x.published_at) <= 7*DAY && now-Date.parse(x.last_seen) <= 7*DAY)
    .sort((a,b) => b.last_seen.localeCompare(a.last_seen) || a.url.localeCompare(b.url)).slice(0,MAX_ITEMS);
  state.feeds = feeds; state.last_attempt = stamp(now);
  state.status = Object.values(feeds).every(x => ["ok","not_modified"].includes(x.status)) ? "ok" : "partial_or_failed";
  if (state.status === "ok") state.last_success = stamp(now);
  await env.MH.put(CAPTURE_KEY,JSON.stringify(state)); // exactly one bounded write; 144/day at target cadence
  return publicCapture(state,now);
}

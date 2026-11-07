// Pure logic shared by the Worker and tests. Fee rates mirror moneyhunter/fees.py [S] (checked 2 Nov 2026).
export const PACKAGING = 0.5, RETURNS = 0.03;
// Home-delivery postage by category [S] evri.com/our-services/our-prices, checked 2 Nov 2026 (mirrors config.py)
export const POSTAGE_BY_CAT = { gaming: 2.70, fragrance: 3.04, tech: 3.04, sportswear: 3.04, trainers: 3.52, lego: 4.79, tools: 6.59, default: 3.52 };
export const MIN_NET = 8, MIN_ROI = 40; // [H] neutral community max-buy rule
const FVF = { sportswear: 0.119, lego: 0.109, fragrance: 0.109, gaming: 0.099, default: 0.129 };

export function ebayBusinessFee(price, cat, post = 0) {
  const t = price + post; let f;
  if (cat === "trainers") f = t * (price >= 100 ? 0.07 : 0.119);
  else if (cat === "tools") f = Math.min(t, 750) * 0.069 + Math.max(0, t - 750) * 0.03;
  else f = t * (FVF[cat] ?? FVF.default);
  return r2((f + (t <= 10 ? 0.3 : 0.4) + t * 0.0035) * 1.20); // VAT on published business fees
}
export function platformFee(pl, price, cat) {
  if (["ebay_private", "vinted", "fb_cash"].includes(pl)) return 0;
  if (pl === "fb" || pl === "paypal") return r2(price * 0.029 + 0.3);   // PayPal UK goods & services
  if (pl === "ebay_business") return ebayBusinessFee(price, cat);
  if (pl === "depop") return r2(price * 0.029 + 0.3);
  if (pl === "stockx") return r2(Math.max(4.5, price * 0.09) + price * 0.03 + 4);
  throw new Error("unknown platform " + pl);
}
export function calc(buy, sell, pl = "ebay_business", cat = "default", outbound = null) {
  if (![buy, sell].every(x => Number.isFinite(x) && x >= 0) || (outbound != null && (!Number.isFinite(outbound) || outbound < 0))) throw new Error("Finite nonnegative costs required");
  const fee = platformFee(pl, sell, cat);
  const post = pl === "vinted" || pl === "fb_cash" ? 0 : (outbound ?? POSTAGE_BY_CAT[cat] ?? POSTAGE_BY_CAT.default);
  const ret = r2(sell * RETURNS);
  const net = r2(sell - fee - post - PACKAGING - ret - buy);
  const proceeds = sell - fee - post - PACKAGING - ret;
  const maxBuy = Math.floor(Math.max(0, Math.min(proceeds - MIN_NET, proceeds / (1 + MIN_ROI / 100))) * 100) / 100;
  return { buy, sell, platform: pl, category: cat, fee, postage: post, packaging: PACKAGING, returns: ret, net, roi: buy ? r2(net / buy * 100) : null, maxBuy };
}
export function parseCsv(text) {
  const rows = []; let row = [], cur = "", q = false;
  for (let i = 0; i < text.length; i++) {
    const c = text[i];
    if (q) { if (c === '"') { if (text[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += c; }
    else if (c === '"') q = true; else if (c === ",") { row.push(cur); cur = ""; }
    else if (c === "\n") { row.push(cur); rows.push(row); row = []; cur = ""; } else if (c !== "\r") cur += c;
  }
  if (cur || row.length) { row.push(cur); rows.push(row); }
  const [h, ...b] = rows; return b.filter(r => r.length > 1).map(r => Object.fromEntries(h.map((k, i) => [k, r[i] ?? ""])));
}
// Strict match only (mirrors moneyhunter/matching.py): every comp word must appear as a whole word,
// and kids / bundle / pre-order / used / edition words in the query that the comp lacks block the match.
const GUARD = ["girls", "boys", "kids", "junior", "infant", "toddler", "child", "youth", "baby", "bundle", "pack", "set of",
  "pre order", "preorder", "used", "pre owned", "refurbished", "refurb", "renewed", "resale", "open box", "grey import", "tester",
  "deluxe edition", "collectors", "limited edition", "special edition", "switch 2", "digital", "kit", "battery", "console"];
const norm = s => " " + s.toLowerCase().replace(/[’'`.]/g, "").replace(/[^a-z0-9£+]+/g, " ").trim() + " ";
const hasW = (t, w) => t.includes(" " + w + " ");
export function findComp(query, comps) {
  const t = norm(query); let best = null, blocked = "";
  for (const c of comps) {
    const m = norm(c.match); const words = m.trim().split(" ");
    if (!words.every(w => hasW(t, w))) continue;
    const g = GUARD.find(w => hasW(t, w) && !hasW(m, w));
    if (g) { blocked = blocked || `${c.match} (${g})`; continue; }
    if (!best || c.match.length > best.match.length) best = c;
  }
  if (!best && blocked) return { blocked };
  return best;
}
export const r2 = x => Math.round(x * 100) / 100;
export const gbp = x => (x < 0 ? "−£" : "£") + Math.abs(x).toFixed(2);
export function hexToBytes(h) { const a = new Uint8Array(h.length / 2); for (let i = 0; i < a.length; i++) a[i] = parseInt(h.substr(i * 2, 2), 16); return a; }
export async function verifyDiscord(req, body, publicKeyHex) {
  const sig = req.headers.get("x-signature-ed25519"), ts = req.headers.get("x-signature-timestamp");
  if (!sig || !ts) return false;
  try {
    const key = await crypto.subtle.importKey("raw", hexToBytes(publicKeyHex), { name: "Ed25519" }, false, ["verify"]);
    return await crypto.subtle.verify("Ed25519", key, hexToBytes(sig), new TextEncoder().encode(ts + body));
  } catch { return false; }
}

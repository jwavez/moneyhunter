// One-off: post and pin the hub's guide messages (bot token from env, never printed).
import { readFileSync } from "node:fs";
const { _test } = await import("../worker/src/index.js");
const ch = JSON.parse(readFileSync(new URL("./channels.json", import.meta.url)));
const T = process.env.DISCORD_BOT_TOKEN, API = "https://discord.com/api/v10";
const H = { authorization: "Bot " + T, "content-type": "application/json" };
const id = n => Object.fromEntries(Object.entries(ch))[n];
async function postPin(name, body) {
  const r = await fetch(`${API}/channels/${id(name)}/messages`, { method: "POST", headers: H, body: JSON.stringify({ allowed_mentions: { parse: [] }, ...body }) });
  const m = await r.json(); if (!r.ok) { console.log(name, "post", r.status, JSON.stringify(m).slice(0, 200)); return; }
  const p = await fetch(`${API}/channels/${id(name)}/pins/${m.id}`, { method: "PUT", headers: H });
  console.log(`#${name}: posted ${r.status}, pinned ${p.status}`);
}
const L = n => `<#${id(n)}>`;
const welcome = { embeds: [
  { title: "👋 Welcome to MONEY HUNTERS", color: 0x8b5cf6, description:
    "MONEYHUNTER scans UK deals every 30 minutes, works out every fee and posts only deals that can resell for profit.\n\n" +
    `**Start:** open ${L("control-panel")} and click the buttons. Everything there is private to you.` },
  { title: "🟢🟡🔴 Grades", color: 0x22c55e, description:
    "🟢 **BUY** (A): all 8 checks pass: profit, ROI, speed, demand, comps, confidence, safe exit, price cap.\n" +
    "🟡 **VERIFY** (B): the money works but check eBay sold first.\n🔴 **PASS**: fails a money check. Shown only as near-misses.\n" +
    "**Max buy** = the highest price that still leaves £8 net and 40% ROI after fees, postage, packaging and 3% returns." },
  { title: "🗺️ Channels", color: 0x3b82f6, description:
    `${L("buy-now")} A-grade deals · ${L("verify")} B-grade · ${L("price-errors")} price errors and very hot deals\n` +
    `${L("trainers")} ${L("lego")} ${L("games-consoles")} ${L("tools")} ${L("fragrance")} ${L("tech")} category feeds\n` +
    `${L("price-drops")} prices that fell · ${L("trending")} hottest deals · ${L("near-misses")} 8am digest · ${L("seasonal-calendar")} when to buy and sell\n` +
    `${L("flip-log")} log flips for XP · ${L("wins")} share wins · ${L("sold-comps")} submit sold prices · ${L("leaderboard")} Monday 9am · ${L("flip-chat")} chat\n${L("bot-status")} scan health` },
  { title: "⚠️ Rules and honesty", color: 0xef4444, description:
    "1. Always check **eBay sold** before you buy. Prices are estimates, not guarantees. No guaranteed profits.\n" +
    "2. Price errors may be cancelled by the retailer. Never buy more than you can afford to return.\n" +
    "3. Be kind, no spam or referral links, no selling fakes.\n4. Not financial advice. You are responsible for your own tax." } ] };
const calendar = { embeds: [{ title: "📅 UK flipping calendar", color: 0x06b6d4, description:
  "Dates below are calendar facts. *Demand notes are house guidance [H], not guarantees.*\n\n" +
  "**Fri 27 Nov 2026 · Black Friday** (day after US Thanksgiving): best buying week for trainers, LEGO, tools, tech.\n" +
  "**Mon 30 Nov 2026 · Cyber Monday**: last big discount day before Christmas.\n" +
  "**Early to mid Dec**: sell gifts (LEGO, fragrance, games). Watch couriers' last-posting dates.\n" +
  "**Sat 26 Dec 2026 · Boxing Day** and **January sales**: buy clearance, sell in spring.\n" +
  "**Sun 14 Feb 2027 · Valentine's Day**: fragrance demand.\n**Sun 7 Mar 2027 · Mother's Day (UK)**: fragrance and gifts.\n" +
  "**Sun 20 Jun 2027 · Father's Day (UK)**: tools, aftershave, tech.\n**Usually July · Amazon Prime Day** (date announced nearer the time).\n" +
  "**Aug to early Sep · Back to school**: trainers, tech, calculators.", footer: { text: "Updated 2 Nov 2026" } }] };
await postPin("welcome-how-it-works", welcome);
const deals = await (await fetch("https://raw.githubusercontent.com/jwavez/moneyhunter/state/deals.json")).json();
await postPin("control-panel", _test.panel(deals));
await postPin("flip-log", _test.flipPanel());
await postPin("sold-comps", _test.compsPanel());
await postPin("seasonal-calendar", calendar);

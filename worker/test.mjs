import assert from "node:assert/strict";
import { calc, ebayBusinessFee, parseCsv, findComp, verifyDiscord } from "./src/logic.js";
import { readFileSync } from "node:fs";
import { webcrypto } from "node:crypto";
// fees match the Python tests
assert.equal(ebayBusinessFee(50, "sportswear"), Math.round((50*0.119+0.40+50*0.0035)*100)/100);
assert.equal(ebayBusinessFee(120, "trainers"), Math.round((120*0.07+0.40+120*0.0035)*100)/100);
assert.equal(ebayBusinessFee(800, "tools"), Math.round((750*0.069+50*0.03+0.40+800*0.0035)*100)/100);
const v = calc(10, 30, "vinted", "gaming"); assert.equal(v.fee, 0); assert.equal(v.postage, 0); assert.equal(v.net, Math.round((30-0.5-0.9-10)*100)/100);
const comps = parseCsv(readFileSync("../data/comps.csv", "utf8")); assert.ok(comps.length >= 40, "comps " + comps.length);
assert.equal(findComp("Mario Kart 8 Deluxe Switch", comps).match, "mario kart 8");
// ed25519 signature check with a throwaway key
const kp = await webcrypto.subtle.generateKey({ name: "Ed25519" }, true, ["sign", "verify"]);
const pub = Buffer.from(await webcrypto.subtle.exportKey("raw", kp.publicKey)).toString("hex");
const ts = "123", body = '{"type":1}';
const sig = Buffer.from(await webcrypto.subtle.sign("Ed25519", kp.privateKey, new TextEncoder().encode(ts + body))).toString("hex");
const req = h => ({ headers: new Map(Object.entries(h)) });
assert.equal(await verifyDiscord(req({ "x-signature-ed25519": sig, "x-signature-timestamp": ts }), body, pub), true);
assert.equal(await verifyDiscord(req({ "x-signature-ed25519": sig, "x-signature-timestamp": "124" }), body, pub), false);
// full handler: PING, bad sig, calc
const { default: w } = await import("./src/index.js");
const mk = (b, s = sig, t = ts) => ({ method: "POST", text: async () => b, headers: new Map([["x-signature-ed25519", s], ["x-signature-timestamp", t]]) });
const env = { DISCORD_PUBLIC_KEY: pub };
assert.equal((await (await w.fetch(mk(body), env, {})).json()).type, 1);
assert.equal((await w.fetch(mk(body, sig, "999"), env, {})).status, 401);
const cb = JSON.stringify({ type: 2, data: { name: "calc", options: [{ name: "buy", value: 10 }, { name: "sell", value: 30 }, { name: "platform", value: "vinted" }] } });
const csig = Buffer.from(await webcrypto.subtle.sign("Ed25519", kp.privateKey, new TextEncoder().encode(ts + cb))).toString("hex");
const out = await (await w.fetch(mk(cb, csig), env, {})).json(); assert.equal(out.type, 4); assert.match(out.data.embeds[0].title, /net £18\.60/);
const { COMMANDS } = await import("./scripts/register.mjs"); assert.equal(COMMANDS.length, 5);
console.log("worker tests OK");

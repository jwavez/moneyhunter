// Synthetic fixtures only. No external request or Discord send is performed.
import assert from "node:assert/strict";
import test from "node:test";
import { capture, parseFeed, price, publicCapture, CAPTURE_KEY, FEEDS } from "./src/capture.js";
import worker,{_test} from "./src/index.js";
const now=Date.parse("2026-11-07T12:00:00Z");
function xml({title="LEGO 75402 New",amount="£20",date=new Date(now).toUTCString(),url="https://www.hotukdeals.com/deals/synthetic-fixture",desc="Fixture research only"}={}) {
 return `<rss xmlns:pepper="http://www.pepper.com/rss"><channel><item><title><![CDATA[${title}]]></title><link>${url}</link><description><![CDATA[${desc}]]></description><pubDate>${date}</pubDate><pepper:merchant name="Synthetic retailer" price="${amount}" /></item></channel></rss>`;
}
function kv() { const store=new Map(),writes=[];return {store,writes,get:async(k,type)=>store.has(k)?JSON.parse(store.get(k)):null,put:async(k,v)=>{writes.push(k);store.set(k,v);}}; }
function response(body=xml(),status=200) {return new Response(status===304?null:body,{status,headers:{etag:'"synthetic-fixture"',"last-modified":"Sat, 07 Nov 2026 12:00:00 GMT"}});}
const fetcher=async(u,o)=>{assert.equal(o.redirect,"manual");return response();};
test("currency ambiguity rejects old/was prices, accepts one distinct value",()=>{
 assert.equal(price("was £80 now £40"),null);assert.equal(price("£20 + £3 delivery"),null);
 assert.equal(price("£20 £20"),20);assert.equal(price("&pound;20"),20);assert.equal(price("£9.999"),null);
});
test("bounded RSS exact source, CDATA, date, cap and online-only",()=>{
 const rows=parseFeed(xml(),"lego","tag/lego",now);assert.equal(rows.length,1);assert.equal(rows[0].price,20);
 assert.equal(rows[0].inbound_delivery,null);assert.equal(rows[0].availability,"unverified");
 for(const changes of [{amount:"£61"},{url:"https://evil.example/deals/x"},{title:"LEGO 75402 in store only"},{date:"01 Oct 2026"},{amount:"was £80 now £20"},{title:"LEGO 75402 pre-order"},{title:"LEGO digital download"}])
  assert.equal(parseFeed(xml(changes),"lego","tag/lego",now).length,0,JSON.stringify(changes));
 assert.equal(parseFeed(xml({title:"Captain Game Xbox Series X"}).replace('name="Synthetic retailer"','name="Xbox"'),"gaming","tag/xbox",now).length,0);
 assert.throws(()=>parseFeed("<!DOCTYPE foo>"+xml(),"lego","x",now));
 assert.throws(()=>parseFeed(xml().replace("</item>",""),"lego","x",now));
 assert.throws(()=>parseFeed("x".repeat(524289),"lego","x",now));
});
test("independent capture writes once and keeps first seen/price changes",async()=>{
 const MH=kv();const a=await capture({MH},now,fetcher);assert.equal(a.status,"ok");assert.equal(a.items.length,1);
 assert.equal(MH.writes.length,1);assert.deepEqual(MH.writes,[CAPTURE_KEY]);assert.equal(a.grades_computed,false);
 const b=await capture({MH},now+600000,async()=>response(xml({amount:"£18"})));
 assert.equal(b.items[0].first_seen,a.items[0].first_seen);assert.equal(b.items[0].price,18);assert.ok(b.items[0].price_changed_at);
 assert.equal(MH.writes.length,2);assert.equal(b.items[0].category,"lego");
});
test("conditional 304 retains offers without inventing new items",async()=>{
 const MH=kv();await capture({MH},now,fetcher);let calls=0;
 const b=await capture({MH},now+600000,async(u,o)=>{calls++;assert.equal(o.headers["If-None-Match"],'"synthetic-fixture"');return response(null,304);});
 assert.equal(calls,4);assert.equal(b.items.length,1);assert.equal(b.status,"ok");
 assert.equal(b.items[0].last_seen,new Date(now+600000).toISOString());
});
test("403/challenge pauses source, never retries through fallback",async()=>{
 const MH=kv();let calls=0;
 const a=await capture({MH},now,async()=>{calls++;return response("Access denied",403);});
 assert.equal(a.status,"partial_or_failed");assert.equal(a.last_success,null);assert.equal(calls,4);
 await capture({MH},now+600000,async()=>{throw new Error("must not retry");});assert.equal(calls,4);
 assert.ok(Object.values(a.feeds).every(x=>x.paused));
});
test("429 backoff respects cooldown and failure retains previous success clock",async()=>{
 const MH=kv();const first=await capture({MH},now,fetcher);
 const second=await capture({MH},now+600000,async()=>response("limited",429));assert.equal(second.last_success,first.last_success);
 let calls=0;await capture({MH},now+1200000,async()=>{calls++;return response();});assert.equal(calls,0);
});
test("malformed/oversized response stays failure, not an empty successful scan",async()=>{
 for(const payload of ["<html>unexpected</html>",xml().replace("</item>",""),"x".repeat(524289)]) {
  const MH=kv(),r=await capture({MH},now,async()=>response(payload));assert.equal(r.status,"partial_or_failed");assert.equal(r.last_success,null);
 }
});
test("seven-day retention and public endpoint exclude internal cache validators",async()=>{
 const MH=kv();await capture({MH},now,fetcher);
 const data=JSON.parse(MH.store.get(CAPTURE_KEY));const pub=publicCapture(data,now+8*86400000);assert.equal(pub.items.length,0);assert.equal(pub.stale,true);
 assert.equal(JSON.stringify(pub).includes("etag"),false);assert.equal(JSON.stringify(pub).includes("rows"),false);
 const out=await worker.fetch({method:"GET",url:"https://x/api/research-capture"},{MH},{});
 assert.equal(out.status,200);assert.equal((await out.json()).grades_computed,false);
});
test("scheduled handler only requests four approved feeds, no Discord/GitHub/eBay",async()=>{
 const original=globalThis.fetch,MH=kv(),urls=[];
 globalThis.fetch=async u=>{urls.push(u);assert.ok(FEEDS.some(([,path])=>u==="https://www.hotukdeals.com/rss/"+path));return response(xml({date:new Date().toUTCString()}));};
 try {await worker.scheduled({}, {MH}, {});} finally {globalThis.fetch=original;}
 assert.equal(urls.length,4);assert.equal(MH.writes.length,1);
});
test("merging capture into UI leaves grades/timestamps alone; changed price drops stale context",()=>{
 const main={url:"x",title:"LEGO 75402",item_price:20,priority:5,ask_context:{kind:"active_ask"}};
 const row={url:"x",title:main.title,price:18,category:"lego",first_seen:new Date(now).toISOString(),last_seen:new Date(now).toISOString()};
 const result=_test.mergeResearch([main],{items:[row]});assert.equal(main.item_price,20);assert.equal(result[0].item_price,18);
 assert.equal(result[0].landed_cost,null);assert.equal(result[0].ask_context,undefined);assert.ok(result[0].breakeven_sell>18);assert.ok(result[0].blockers.length);
});
test("asking ranges have independent expiry and cannot render as sold prices",()=>{
 const x={kind:"active_ask",observed_at:new Date().toISOString(),sample_count:3,listed_total_low:30,listed_total_median:32,listed_total_high:35,query:"LEGO 75402",status:"indicative_only"};
 assert.equal(_test.freshAsking(x),true);assert.match(_test.askFields(x)[0].name,/NOT sold/);
 assert.equal(_test.freshAsking({...x,observed_at:"2026-01-01T00:00:00Z"}),false);
 assert.equal(_test.askFields({...x,kind:"sold"}).length,0);
});

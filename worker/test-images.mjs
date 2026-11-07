// Synthetic offline image fixtures. No network, Discord sends or production evidence.
import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';
import {guardData,verifyImage,imageMeta} from './src/images.js';import {_test} from './src/index.js';
const image='https://i.ebayimg.com/images/g/synthetic/s-l500.jpg';
const photo=()=>new Response(Uint8Array.from([255,216,255,...Array(40).fill(0)]),{headers:{'content-type':'image/jpeg'}});
const kv=()=>{const s=new Map();return {get:async(k,t)=>s.has(k)?(t==='json'?JSON.parse(s.get(k)):s.get(k)):null,put:async(k,v)=>s.set(k,v)};};
const row=()=>({category:'lego',title:'LEGO Synthetic Moon Rover 75402',thumb:image});
test('real image status + MIME + signature, HTTPS host pin and redirect rejection',async()=>{
 for(const [response,expected] of [[photo(),true],[new Response('<html>not image</html>',{headers:{'content-type':'image/jpeg'}}),false],[new Response('x',{status:302,headers:{location:'https://localhost/private'}}),false],[new Response('x',{status:404}),false]]) {
  let calls=0;const result=await verifyImage(image,{},async(u,o)=>{calls++;assert.equal(o.redirect,'manual');assert.equal(o.credentials,'omit');return response;});assert.equal(result,expected);assert.equal(calls,1);
 }
 let calls=0;assert.equal(await verifyImage('https://127.0.0.1/private',{},async()=>{calls++;}),false);assert.equal(calls,0);
});
test('cache avoids repeated reads; denied host is paused instead of bypassed or retried',async()=>{
 const env={MH:kv()};let calls=0;
 assert.ok(await verifyImage(image,env,async()=>{calls++;return photo();}));assert.ok(await verifyImage(image,env,async()=>{calls++;return photo();}));assert.equal(calls,1);
 const blocked={MH:kv()};assert.equal(await verifyImage(image,blocked,async()=>{calls++;return new Response('denied',{status:403});}),false);
 const before=calls;assert.equal(await verifyImage(image+'?other',blocked,async()=>{calls++;return photo();}),false);assert.equal(calls,before);
});
test('missing/broken photo holds entire product card; valid exact-source alternate succeeds',async()=>{
 for(const x of [{category:'lego',title:'LEGO 75402'},{...row(),thumb:'https://localhost/x'}]){
  const result=await guardData({flags:64,allowed_mentions:{parse:[]},embeds:[{...imageMeta(x),title:x.title}]},{},async()=>photo());assert.equal(result.embeds,undefined);assert.match(result.content,/held/);assert.equal(result.flags,64);assert.deepEqual(result.allowed_mentions,{parse:[]});
 }
 const r=await guardData({embeds:[{...imageMeta({...row(),image_basis:'Reference exact set',image_candidates:[image+'?fallback']}),title:row().title}]},{},async(u)=>u===image?new Response('gone',{status:404}):photo());
 assert.equal(r.embeds[0].image.url,image+'?fallback');assert.match(r.embeds[0].description,/not proof of listing condition/);assert.doesNotMatch(JSON.stringify(r),/_mh_/);
});
test('research, category/deal and plan views all pass the same final image guard',async()=>{
 const d=JSON.parse(fs.readFileSync('./test-deals.json'));const x={...d.deals[0],...row()};
 const outputs=[_test.dealView(d,[x],'all',0),_test.planView(x),_test.researchView({...d,review_queue:[{...x,item_price:20,priority:1}]})];
 for(const out of outputs){const r=await guardData(out,{},async()=>photo());assert.equal(r.embeds[0].image.url,image);assert.doesNotMatch(JSON.stringify(r),/_mh_/);}
});

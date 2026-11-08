import test from 'node:test';import assert from 'node:assert/strict';
import {priced as fixture} from './test-publication-fixture.mjs';import {priced} from './src/publication.js';import {guardData} from './src/images.js';import {_test} from './src/index.js';
const good=()=>fixture({title:'Sony WH-CH520 Black New',category:'tech',item_price:30});
test('exact Python attestation required; source title, price, model, expiry cannot drift',()=>{
 const r=good();assert.ok(priced(r));
 for(const edit of [x=>delete x.publication_proof,x=>x.ask_estimate.sources[0].title='wrong variant',x=>x.ask_estimate.sources[0].shipping=99,x=>x.title='different identity',x=>x.ask_estimate.observed_at='2001-01-01',x=>x.ask_estimate.sources=x.ask_estimate.sources.slice(0,1)]){const x=structuredClone(r);edit(x);assert.ok(!priced(x));}
});
test('final response refuses a valid hidden price without displayed selling price',async()=>{
 const r=good();const {imageMeta}=await import('./src/images.js');
 let out=await guardData({embeds:[{title:r.title,...imageMeta(r)}]});assert.match(out.embeds[0].title,/research pending/);
 out=await guardData({embeds:[{title:r.title,...imageMeta(r),fields:[{name:'Sell',value:'£49.99'}]}]});assert.equal(out.embeds[0].title,r.title);
});
test('unpriced research, plans and browser contain no product/target financial card',()=>{
 const x={title:'Unpriced DUB185Z',category:'tools',item_price:39.99,target:119.54};
 for(const out of [_test.researchView({review_queue:[x]}),_test.planView(x)]){assert.ok(!JSON.stringify(out).includes(x.title));assert.ok(!JSON.stringify(out).includes('119.54'));}
});

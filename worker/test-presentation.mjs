import test from 'node:test';import assert from 'node:assert/strict';
import {nonphysical,normalizeProduct,physicalRows} from './src/product-format.js';
import {summaryFields} from './src/presentation.js';import {calc} from './src/logic.js';import {_test} from './src/index.js';import {guardData} from './src/images.js';
const m={model:'competitor-asks-v1',observed_at:new Date().toISOString(),category:'gaming',suggested_listing:51.02,estimated_resale:49.49,item_price:34.99,delivery_known:false,net_before_unknown_delivery:3.25,seller_count:1,confidence:'low',policy:{cap:60},checks:[],sources:[]};
test('PC key excluded irrespective of stale LEGO category/store; physical keys and console preserved',()=>{
 for(const merchant of ['Loaded','Unknown','Steam','GOG','Epic Games'])assert.ok(nonphysical({title:'LEGO Batman Legacy of the Dark Knight PC Key',category:'lego',merchant}));
 for(const title of ['Logitech Keyboard replacement PC key','LEGO Batman keychain','Sony PS5 Digital Edition Console'])assert.ok(!nonphysical({title}),title);
 assert.equal(normalizeProduct({title:'LEGO Batman PS5 physical game',category:'lego'}).category,'gaming');
 assert.equal(physicalRows([{title:'LEGO Batman PC Key',category:'lego'}]).length,0);
});
test('listing profit at same sale price, conservative profit explicit, limited comp and delivery unknown',()=>{
 const f=summaryFields({},m);assert.match(f[0].value,/51.02.*INDICATIVE ONLY/);assert.ok(f[1].value.includes(calc(34.99,51.02,'ebay_business','gaming').net.toFixed(2)));assert.match(f[1].value,/UNKNOWN.*49.49.*3.25/);assert.match(f[2].value,/NOT A BUY/);
});
test('unknown, stale, loss and conditional fragrance stay explicit',()=>{
 assert.match(summaryFields({})[0].value,/No reliable resale estimate/);
 assert.match(summaryFields({},{...m,observed_at:'2001-01-01'})[0].value,/No reliable/);
 assert.match(summaryFields({},{...m,item_price:59,suggested_listing:60,estimated_resale:58.2,net_before_unknown_delivery:-15})[2].value,/SKIP/);
 assert.match(summaryFields({},{...m,transport_validated:false,net_before_unknown_delivery:null})[1].value,/UNKNOWN/);
 assert.match(summaryFields({},{...m,above_budget:true})[2].value,/WATCH ONLY/);
});
test('legacy interactive research and plan cannot revive physical key economics',async()=>{
 const x={title:'LEGO Batman PC Key',category:'lego',item_price:29.99};
 assert.equal(_test.mergeResearch([x],{items:[]}).length,0);
 assert.match(JSON.stringify(_test.planView(x)),/EXCLUDED/);
 assert.match(JSON.stringify(await _test.priceView(x.title,null,{})),/EXCLUDED/);
 const data=await guardData({embeds:[{title:x.title,_mh_product_category:'lego',fields:[{name:'postage',value:'bad old cost'}]}]});
 assert.match(data.content,/nonphysical/);assert.ok(!data.embeds);
});

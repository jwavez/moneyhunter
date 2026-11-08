// Offline synthetic source shape, never production observations.
export function priced(x){
 const now=new Date().toISOString(), title=x.title??'LEGO 75402 New',query=x.ask_estimate?.query??'LEGO 75402';
 const sources=Array.from({length:6},(_,i)=>({url:`https://www.ebay.co.uk/itm/${123456789000+i}`,title,country:'GB',currency:'GBP',declared_condition:'new',item_price:50+i,shipping:0,listed_total:50+i,seller:`fixture-${i}`}));
 const m={model:'competitor-asks-v1',category:x.category??'lego',query,observed_at:now,suggested_listing:49.99,estimated_resale:48.5,confidence:'moderate',seller_count:6,net_before_unknown_delivery:10,estimated_range:[45,55],checks:[],...x.ask_estimate,sources,observed_at:now};
 return {...x,ask_estimate:m,publication_proof:{ok:true,title,query:m.query,listing:m.suggested_listing,observed_at:now,valid_until:new Date(Date.now()+6*3600000).toISOString(),sources:sources.map(s=>s.url),comparators:sources.map(o=>[o.url,o.title,o.listed_total,o.shipping,o.item_price,o.seller])}};
}

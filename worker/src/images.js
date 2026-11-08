import {priceMeta,validProof,pending} from './publication.js';
import {nonphysical} from "./product-format.js";
// Mandatory LEGO product-photo publication guard. Only original approved public CDN
// images; no redirect following, cookies, credentials, arbitrary hosts or full downloads.
import {productImage} from './capture.js';
const TTL=20*60*1000;
const memory=new WeakMap();
const cacheRequest=key=>new Request('https://moneyhunter-bot.moneyhunter.workers.dev/__image_validation/'+key);
async function readCheck(key,env){
 if(globalThis.caches?.default){const r=await caches.default.match(cacheRequest(key));return r?await r.json():null;}
 return memory.get(env)?.get(key);
}
async function saveCheck(key,value,env,seconds){
 // Existing free edge Cache API; no per-photo KV writes or new storage service.
 if(globalThis.caches?.default){await caches.default.put(cacheRequest(key),new Response(JSON.stringify(value),{headers:{'Cache-Control':'max-age='+seconds}}));return;}
 if(!memory.has(env))memory.set(env,new Map());const m=memory.get(env);if(m.size>=128)m.delete(m.keys().next().value);m.set(key,value);
}
export function imageMeta(x={}) {
 return {...priceMeta(x),_mh_product_category:x.category??x.ask_estimate?.category,_mh_image_basis:x.image_basis,_mh_image_candidates:[x.thumb,...(x.image_candidates??[])].map(productImage).filter(Boolean).slice(0,4),
   ...(productImage(x.thumb)?{image:{url:productImage(x.thumb)}}:{})};
}
function actualImage(b){return (b[0]===255&&b[1]===216&&b[2]===255)||[137,80,78,71,13,10,26,10].every((v,i)=>b[i]===v)||new TextDecoder().decode(b.slice(0,6)).match(/^GIF8[79]a$/)||new TextDecoder().decode(b.slice(0,12)).match(/^RIFF....WEBP$/s);}
export async function verifyImage(url,env={},fetcher=fetch,now=Date.now(),paused=new Set()) {
 url=productImage(url);if(!url)return false;
 const host=new URL(url).hostname;
 if(paused.has(host)||await env.MH?.get("image-host-paused:"+host))return false;
 const hash=[...new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(url)))].map(x=>x.toString(16).padStart(2,'0')).join('');
 const key='image-check:v1:'+hash;
 const old=await readCheck(key,env);if(old?.until>now)return old.ok===true;
 let ok=false;
 try {
  const response=await fetcher(url,{redirect:'manual',credentials:'omit',headers:{Accept:'image/jpeg,image/png,image/webp,image/gif'},signal:AbortSignal.timeout(900)});
  if([401,403].includes(response.status)){paused.add(host);await env.MH?.put("image-host-paused:"+host,"access_denied");}
  const mime=(response.headers.get('content-type')??'').split(';')[0].toLowerCase();
  if(response.status===200&&['image/jpeg','image/png','image/webp','image/gif'].includes(mime)) {
   const reader=response.body.getReader();let total=0;const chunks=[];
   try {while(total<32){const {value,done}=await reader.read();if(done)break;chunks.push(value.slice(0,4096-total));total+=Math.min(value.length,4096-total);}}
   finally{await reader.cancel();reader.releaseLock();}
   const bytes=new Uint8Array(total);let offset=0;for(const c of chunks){bytes.set(c,offset);offset+=c.length;}
   ok=!!actualImage(bytes);
  } else await response.body?.cancel();
 } catch {}
 await saveCheck(key,{ok,until:now+(ok?TTL:60000)},env,ok?1200:60);
 return ok;
}
export async function guardData(data,env={},fetcher=fetch){
 if(!data?.embeds)return data;
 for(const e of data.embeds){
  if((e._mh_product_card||e._mh_product_category||(e.url&&e.title))&&(!validProof(e._mh_price_proof)||!JSON.stringify(Object.fromEntries(Object.entries(e).filter(([k])=>!k.startsWith('_mh_')))).includes('£'+e._mh_price_proof.listing.toFixed(2))))return {...pending(),flags:data.flags??64,allowed_mentions:{parse:[]}};
  if(nonphysical({title:e.title??""}))return {flags:data.flags??64,content:"Excluded nonphysical digital key/code: no physical-resale card or postage calculation is available.",allowed_mentions:{parse:[]}};
  const identified=e._mh_product_category==='lego'||/\blego\b[^\n]*\b\d{5,6}\b/i.test([e.title,e.author?.name].join('\n'));
  if(!identified)continue;
  const candidates=[e.image?.url,...(e._mh_image_candidates??[])].map(productImage).filter(Boolean);
  const paused=new Set();let chosen='';for(const url of [...new Set(candidates)].slice(0,2)){if(await verifyImage(url,env,fetcher,Date.now(),paused)){chosen=url;break;}}
  if(!chosen)return {...(data.flags!=null?{flags:data.flags}:{}),allowed_mentions:data.allowed_mentions??{parse:[]},content:'LEGO product photo pending verification. This product card is held rather than published without a working image. Try Next or check later.',components:(data.components??[]).filter(r=>r.components?.some(c=>c.custom_id))};
  e.image={url:chosen};
  if(e._mh_image_basis?.startsWith("Reference") && !/reference/i.test(e.description??""))e.description=(e.description??"")+"\nImage is an exact-set reference, not proof of listing condition.";
 }
 return {...data,embeds:data.embeds.map(e=>Object.fromEntries(Object.entries(e).filter(([k])=>!k.startsWith('_mh_'))))};
}
export async function guardResponse(response,env){
 const body=await response.json();if(body.data)body.data=await guardData(body.data,env);
 return new Response(JSON.stringify(body),{status:response.status,headers:response.headers});
}

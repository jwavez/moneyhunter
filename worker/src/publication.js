// Required source-backed price, independent of profit/BUY qualification.
import {nonphysical} from './product-format.js';
const positive=x=>Number.isFinite(x)&&x>0;
export function priceProof(x={}){
 if(nonphysical(x)||x.offer_ambiguity||x.format_reclassified)return {ok:false,reason:'format_or_primary_offer_ambiguous'};
 const m=x.ask_estimate;
 if(m){
  const bound=x.publication_proof;
  if(!validProof(bound)||bound.title!==x.title||bound.query!==m.query||bound.observed_at!==m.observed_at||bound.listing!==m.suggested_listing||!bound.sources.every(u=>(m.sources??[]).some(o=>o.url===u))||!Array.isArray(bound.comparators)||!bound.comparators.every(c=>(m.sources??[]).some(o=>[o.url,o.title,o.listed_total,o.shipping,o.item_price,o.seller].every((v,i)=>v===c[i]))))return {ok:false,reason:'exact_identity_attestation_missing_or_changed'};
  const age=Date.now()-Date.parse(m.observed_at);
  if(m.model!=='competitor-asks-v1'||!Number.isFinite(age)||age<0||age>=6*3600000||!positive(m.suggested_listing)||!positive(m.estimated_resale))return {ok:false,reason:'missing_or_stale_market_price'};
  if(![undefined,'not_required','verified_fields'].includes(m.detail_status)||m.competitor_coupon_unknown)return {ok:false,reason:'exact_details_or_coupon_unknown'};
  const sellers=new Map();
  for(const o of m.sources??[]){
   let u;try{u=new URL(o.url);}catch{continue;}
   if(u.protocol!=='https:'||!['www.ebay.co.uk','www.ebay.com'].includes(u.hostname)||!u.pathname.startsWith('/itm/')||o.country!=='GB'||o.currency!=='GBP'||o.declared_condition!=='new'||!positive(o.item_price)||!positive(o.listed_total)||!Number.isFinite(o.shipping)||o.shipping<0||Math.abs(o.listed_total-o.item_price-o.shipping)>.01)continue;
   if(o.seller&&(!sellers.has(o.seller.toLowerCase())||o.listed_total<sellers.get(o.seller.toLowerCase()).listed_total))sellers.set(o.seller.toLowerCase(),o);
  }
  const os=[...sellers.values()],low=Math.min(...os.map(o=>o.listed_total));
  if(os.length<3||os.filter(o=>o.listed_total<=low*1.1).length<2||m.suggested_listing>low+.01||m.estimated_resale>low)return {ok:false,reason:'insufficient_exact_comparator_depth'};
  return {ok:true,kind:'active_ask',listing:m.suggested_listing,valid_until:new Date(Date.parse(m.observed_at)+6*3600000).toISOString(),sources:os.map(o=>o.url)};
 }
 const sold=x.evidence_type==='sold',sources=x.sold_sources??[],count=x.sold_90d??x.sample_count??0;
 const age=x.comp_age_days??((Date.now()-Date.parse(x.sold_as_of))/86400000),listing=x.publication_listing??x.plan?.list??(x.reviewed===true?x.low:null);
 if((sold||x.reviewed===true)&&count>=5&&Number.isFinite(age)&&age>=0&&age<=30&&sources.length&&positive(listing))return {ok:true,kind:'reviewed_sold',listing,valid_until:new Date(Date.now()+900000).toISOString(),sources};
 return {ok:false,reason:'no_supported_resale_estimate'};
}
export const priced=x=>priceProof(x).ok;
export const priceMeta=x=>({_mh_product_card:true,_mh_price_proof:priceProof(x)});
export const validProof=p=>p?.ok===true&&positive(p.listing)&&p.sources?.length>0&&Date.parse(p.valid_until)>Date.now();
export const pending=(count=null)=>({embeds:[{title:'Resale research pending',description:`${count==null?'The requested identity is':count+' product identities are'} still being priced in background research. No supported current resale estimate is available, so no product card or buying recommendation is published.`}]});

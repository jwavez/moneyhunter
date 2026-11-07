import {calc,gbp} from './logic.js';
const signed=x=>(x>=0?'+':'')+gbp(x);
export function summaryFields(raw={},m=null,buy=null,landed=false,legacy=null) {
 const age=Date.now()-Date.parse(m?.observed_at);
 if(m&&(!Number.isFinite(age)||age<0||age>=6*3600000))m=null;
 let sell,profit,decision;
 if(m){
  const listing=m.suggested_listing, known=buy!=null?landed:m.delivery_known;
  const cost=buy??(known?m.landed_cost:(raw.price??raw.item_price??m.item_price));
  const conditional=m.transport_validated===false;
  const net=conditional||!Number.isFinite(cost)?null:calc(cost,listing,'ebay_business',raw.category??m.category??'default').net;
  const conservative=buy!=null&&!conditional?calc(buy,m.estimated_resale,'ebay_business',raw.category??m.category??'default').net:known?m.net:m.net_before_unknown_delivery;
  const indicative=m.confidence!=='moderate'||m.seller_count<5||!['not_required','verified_fields',undefined].includes(m.detail_status);
  sell=`${gbp(listing)} starting listing — ${indicative?'INDICATIVE ONLY; limited/unverified comparators':'competitor-based, not guaranteed'}. Conservative sale model ${gbp(m.estimated_resale)}.`;
  profit=conditional?'UNKNOWN — actual compliant parcel/packaging costs unverified; conditional scenario below is not actual profit.':net==null?'UNKNOWN — acquisition cost not supplied.':`${known?'Estimated':'At most'} ${signed(net)} at ${gbp(listing)} sale${known?' after known inbound and configured selling costs.':' BEFORE UNKNOWN inbound delivery; actual net/ROI UNKNOWN.'}`;
  if(conservative!=null)profit+=` Conservative ${gbp(m.estimated_resale)} sale: ${signed(conservative)}${known?' net.':' before unknown delivery.'}`;
  if(m.above_budget||(known&&cost>(m.policy?.cap??60)))decision='ABOVE BUDGET — WATCH ONLY; no purchase approval.'+((net!=null&&net<0)||(conservative!=null&&conservative<0)?' SKIP: estimated loss even before delivery.':'');
  else if((net!=null&&net<0)||(conservative!=null&&conservative<0))decision='SKIP — estimated loss'+(!known?' even before unknown inbound delivery.':' after selling costs.');
  else if(conditional)decision='RESEARCH ONLY — actual perfume transport and profit unvalidated.';
  else if(buy!=null)decision='RESEARCH ONLY — supplied-cost calculation, NOT a verified BUY; saved buying signal does not apply to a different acquisition cost.';
  else if(m.estimated_opportunity)decision='STRONG CHECK — NOT a verified BUY; verify stock, exact item and checkout costs.';
  else if(m.worth_reviewing)decision='MANUAL REVIEW — NOT a verified BUY.';
  else decision=`NOT A BUY — small/insufficient modeled margin or evidence/cost gaps. ${!known?'Inbound delivery unknown. ':''}${m.seller_count??0} known sellers; ${m.confidence??'unknown'} confidence.`;
 }else if(legacy?.evidence_type==='sold'){
  const list=legacy.plan?.list??legacy.target,known=legacy.delivery_known!==false, cost=legacy.landed_cost??legacy.buy;
  sell=`${gbp(list)} starting listing from reviewed sold research; not guaranteed.`;
  profit=`${signed(calc(cost,list,'ebay_business',legacy.category,legacy.postage??null).net)} at ${gbp(list)} sale${known?' after configured costs.':' BEFORE unknown inbound delivery; actual net unknown.'}`;
  decision=legacy.grade==='A'?'BUY — existing verified gates pass; confirm checkout.':legacy.grade==='B'?'VERIFY — existing evidence/offer checks still required.':'SKIP — existing buying checks fail.';
 }else {sell='No reliable resale estimate — Not established: '+(raw.ask_status??'exact current comparators unavailable')+'. Required resale targets are NOT market prices.';profit='UNKNOWN — no reliable market sale price; do not treat the policy target as profit.';decision='RESEARCH ONLY — NOT A BUY. Obtain exact current comparators and all costs.';}
 return [{name:'1 · Sell / starting listing',value:sell.slice(0,1000),inline:false},{name:'2 · Profit at that sale price',value:profit.slice(0,1000),inline:false},{name:'3 · Buy conclusion',value:decision.slice(0,1000),inline:false}];
}

export function soldSummary(reviewed,buy,landed){
 const listing=reviewed.low,valid=Number.isFinite(buy)&&buy>=0&&reviewed.category!=='fragrance';
 return [{name:'1 · Sell / starting listing',value:`${gbp(listing)} working sale estimate from reviewed lower-quartile sold research${reviewed.sample_count<5?' — INDICATIVE ONLY; small sample':''}. Starting listing not independently established; not guaranteed.`,inline:false},
 {name:'2 · Profit at that sale price',value:valid?`${signed(calc(buy,listing,'ebay_business',reviewed.category).net)} at ${gbp(listing)} sale${landed?' with supplied landed cost.':' BEFORE unknown inbound delivery; actual net unknown.'}`:'UNKNOWN — supply landed acquisition cost; perfume also requires verified compliant postage.',inline:false},
 {name:'3 · Buy conclusion',value:'RESEARCH ONLY — no verified current acquisition, stock, cash floor or BUY implied.',inline:false}];
}

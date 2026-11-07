const computer=t=>/\b(desktop|workstation|mini pc)\b/i.test(t)&&/\b(ryzen|intel|geforce|\d+gb|\d+tb)\b/i.test(t);
// Same format rules as Python: category/brand must never override digital format.
const stores=new Set(['eneba','loaded','cdkeys','cdkeys.com','steam','epic games','epic games store','gog','gog.com','xbox','microsoft','nintendo eshop','playstation store']);
export function nonphysical(x={}) {
 const t=String(x.title??'').replace(/[‐‑‒–—]/g,'-');const hardware=/\b(keyboards?|keycaps?|key switches|controller|headset|mouse|console|racing wheel|camera|thermometer|digital piano|steam deck|laptop|notebook|tablet|monitor|television|earbuds|headphones|smartphone|speaker|drill|building set|building kit)\b/i.test(t)||computer(t);
 if(hardware && /\b(keyboard|keycaps?|key switches)\b/i.test(t) && /replacement|spare|keycaps?|key switches|keyboard keys/i.test(t) && !/activation|download|licen[cs]e|game key|software/i.test(t))return false;
 if(/\b(pc[ -]?(?:game[ -]?)?key|cd[ -]?keys?|game[ -]?key|activation[ -]?(?:key|code)|download[ -]?code|digital[ -]?(?:code|key|download)|code in a box|gift[ -]?card|e[ -]?gift|software licen[cs]e|licen[cs]e|steam key|gog key|epic key)\b/i.test(t))return true;
 return !hardware && (/\b(digital|download|steam|gog|epic games|game pass|season pass|dlc|subscription|membership|licen[cs]e)\b/i.test(t)||stores.has(String(x.merchant??'').trim().toLowerCase()));
}
export function normalizeProduct(x={}) {
 if(nonphysical(x))return {...x,category:'digital',online_eligible:false};
 if(computer(x.title??''))return {...x,category:'tech'};
 return /\blego\b/i.test(x.title??'')&&!/(?<!\d)\d{5,6}(?!\d)/.test(x.title??'')&&/\b(ps[45]|playstation|xbox|nintendo switch|pc (?:disc|dvd)|video game)\b/i.test(x.title??'')?{...x,category:'gaming',format_reclassified:true,ask_estimate:undefined,ask_context:undefined}:x;
}
export const physicalRows=xs=>(xs??[]).filter(x=>!nonphysical(x)).map(normalizeProduct);
export const excludedView=x=>({embeds:[{title:String(x.title??'Digital product').slice(0,250),description:'EXCLUDED — NONPHYSICAL. Digital keys/codes are not physical resale offers. No physical postage, profit or LEGO-set advice applies.',fields:[]}]});

export const reclassifiedView=x=>({embeds:[{title:x.title,description:'RESEARCH ONLY — physical LEGO-branded video game belongs in gaming, not building sets. Old category-specific costs/estimates invalidated; await fresh pricing. No set-number selling advice applies.',fields:[{name:'1 · Sell / starting listing',value:'No reliable resale estimate — category-specific refresh required.'},{name:'2 · Profit at that sale price',value:'UNKNOWN — old LEGO-set postage and profit do not apply.'},{name:'3 · Buy conclusion',value:'RESEARCH ONLY — NOT A BUY.'}]}]});

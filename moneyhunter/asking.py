"""Competitor-ask resale estimates. Not sold observations, cash exits or BUY grades.

Current cheapest credible competition caps the model even when it is discounted.
No low-priced offer is removed just because it weakens our acquisition edge.
"""
import datetime as dt
import math
import re
from urllib.parse import urlsplit
from . import config as C
from .fees import net_profit

MODEL = "competitor-asks-v1"


def item_id(value):
    value = str(value or "")
    m = re.search(r"(?:^v1\|)(\d+)\|", value) or re.search(r"/itm/(?:[^/?]+/)?(\d+)", value)
    return m.group(1) if m else value if value.isdigit() else None


def canon(value):
    if not value: return None
    u = urlsplit(str(value))
    return (u.hostname or "").lower().removeprefix("www.") + u.path.rstrip("/")


def max_cost(sale, category):
    from . import policy
    p = policy.current()
    proceeds = net_profit(sale, 0, "ebay_business", category, C.postage_for(category), C.PACKAGING, C.RETURNS_ALLOWANCE).net
    return policy.ceiling(proceeds,p['strong_net'],p['strong_roi'],p['cap'])


def estimate(raw, snapshot, when=None):
    from . import policy
    p = policy.current()
    when = when or dt.datetime.now(dt.timezone.utc)
    try: age = (when-dt.datetime.fromisoformat(snapshot["observed_at"])).total_seconds()/3600
    except (KeyError, ValueError, TypeError): return None
    if snapshot.get("kind") != "active_ask" or not 0 <= age < 6: return None
    acquisition_urls = [raw.get(k) for k in ("url", "retailer_url", "acquisition_url")] + list(raw.get("acquisition_urls") or [])
    urls = {canon(v) for v in acquisition_urls if v}
    ids = {item_id(v) for v in acquisition_urls + [raw.get("ebay_item_id")] if item_id(v)}
    own_seller = str(raw.get("acquisition_seller") or "").casefold()
    seen, sellers, unknown, excluded, promos = set(), {}, [], 0, 0
    promotion_id = raw.get("promotion_id")
    for offer in snapshot.get("offers", [])[:50]:
        if not isinstance(offer, dict): continue
        key = item_id(offer.get("item_id")) or canon(offer.get("url"))
        seller = str(offer.get("seller") or "").casefold()
        if canon(offer.get("url")) in urls or item_id(offer.get("item_id")) in ids or item_id(offer.get("url")) in ids or (own_seller and seller == own_seller):
            excluded += 1; continue
        if key in seen: continue
        seen.add(key)
        total = offer.get("listed_total")
        if not isinstance(total, (int,float)) or isinstance(total,bool) or not math.isfinite(total) or total <= 0: continue
        if offer.get("declared_condition") != "new" or offer.get("country") != "GB" or offer.get("currency") != "GBP": continue
        if not isinstance(offer.get("shipping"),(int,float)) or offer["shipping"] < 0: continue
        if abs(offer.get("item_price", -1) + offer["shipping"] - total) > .005: continue
        same_promo = bool(promotion_id and promotion_id == offer.get("promotion_id"))
        if same_promo: promos += 1
        value = {**offer, "same_acquisition_promotion": same_promo}
        # Cheapest listing per seller: no multi-quantity or duplicate-seller inflation.
        if seller:
            if seller not in sellers or total < sellers[seller]["listed_total"]: sellers[seller] = value
        else: unknown.append(value)
    offers = sorted([*sellers.values(), *unknown], key=lambda o:o["listed_total"])
    if not offers: return None
    xs = sorted(o["listed_total"] for o in offers)
    count, seller_count = len(offers), len(sellers)
    spread = xs[-1] / xs[0]
    low_support = sum(o["listed_total"] <= xs[0]*1.1 for o in sellers.values())
    adequate = seller_count >= 5 and low_support >= 2
    confidence = "moderate" if adequate and spread <= 1.5 else "limited" if adequate else "low"
    target = math.floor(xs[0] * .97 * 100)/100
    quick = math.floor(xs[0] * .90 * 100)/100
    listing = max(.01, round(xs[0]-.01,2))
    category = raw.get("category", snapshot.get("category", "default"))
    buy = raw.get("price")
    if not isinstance(buy,(int,float)) or isinstance(buy,bool) or not math.isfinite(buy) or buy <= 0: return None
    delivery = raw.get("inbound_delivery")
    known = isinstance(delivery,(int,float)) and not isinstance(delivery,bool) and math.isfinite(delivery) and delivery >= 0
    cost = buy + delivery if known else None
    upper = net_profit(target,buy,"ebay_business",category,C.postage_for(category),C.PACKAGING,C.RETURNS_ALLOWANCE)
    breakdown = net_profit(target,cost,"ebay_business",category,C.postage_for(category),C.PACKAGING,C.RETURNS_ALLOWANCE) if known else None
    maximum = max_cost(target,category)
    overlap = promos > 0 or any(o["listed_total"] <= buy+(delivery if known else 0) for o in offers)
    above = buy + (delivery if known else 0) > p['cap']
    money_ok = bool(known and cost <= p['cap'] and breakdown.net >= p['strong_net'] and breakdown.net/cost >= p['strong_roi'])
    stress_sale = math.floor(target*(1-p['review_stress_drop'])*100)/100
    stress = net_profit(stress_sale,cost,"ebay_business",category,C.postage_for(category),C.PACKAGING,C.RETURNS_ALLOWANCE) if known else None
    stress_ok = bool(stress and stress.net >= p['review_stress_net'] and stress.net/cost >= p['review_stress_roi'])
    review_ok = bool(known and cost <= p['cap'] and breakdown.net >= p['review_net'] and breakdown.net/cost >= p['review_roi'] and stress_ok and confidence == 'moderate' and low_support >= 3)
    acquisition_resolved = str(raw.get("merchant", "")).casefold() != "ebay" or bool(ids or own_seller)
    coupon_unknown = any(o.get("available_coupons") and o["listed_total"] <= xs[0]*1.1 for o in offers)
    detail_ok=not snapshot.get("detail_required") or (snapshot.get("detail_status")=="verified_fields" and item_id(snapshot.get("lowest_detail",{}).get("item_id"))==item_id(offers[0].get("item_id")) and snapshot.get("lowest_detail",{}).get("checked_item_price")==offers[0].get("item_price"))
    supported = detail_ok and not coupon_unknown and adequate and raw.get("online_eligible") is True and acquisition_resolved
    opportunity = supported and money_ok
    worth_reviewing = supported and review_ok and not opportunity
    watch_only = above
    blockers = ([] if adequate else ["Fewer than five independent sellers or fewer than two supporting the low price"])
    if not detail_ok:blockers.append("Lowest comparator details unverified/conflicting: "+snapshot.get("detail_status","pending")+"; cheap observation retained, no buying signal")
    if coupon_unknown: blockers.append("Low competing offers advertise coupons; check effective competition before buying")
    if not acquisition_resolved: blockers.append("eBay acquisition listing identity missing; self-exclusion not confirmed")
    if not known: blockers.append("Inbound delivery unknown; profit is only an upper bound")
    if not money_ok: blockers.append(f"£{p['strong_net']:g} net / {p['strong_roi']*100:g}% ROI / £{p['cap']:g} landed strong policy not demonstrated")
    if not stress_ok: blockers.append("Manual review stress test not passed: 10% lower resale must still leave £5 net and 10% ROI")
    if above: blockers.append("ABOVE BUDGET — WATCH ONLY; no purchase approval")
    if not raw.get("online_eligible"): blockers.append("Online physical acquisition not confirmed")
    if raw.get("offer_verified") is not True: blockers.append("Check current retailer stock, checkout price and exact variant before buying")
    advertised = [o["advertised_original_total"] for o in offers if o.get("advertised_original_total") and not o.get("same_acquisition_promotion")]
    model = {"model":MODEL,"category":category,"detail_status":snapshot.get("detail_status","not_required"),"competitor_coupon_unknown":coupon_unknown,"basis":"Current competitor asking totals incl fixed shipping; estimated, NOT sold or guaranteed", "query":snapshot["query"],
        "observed_at":snapshot["observed_at"],"condition":"new (seller declared)","region":"GB","sample_count":count,"seller_count":seller_count,
        "unknown_seller_samples":len(unknown),"low_price_supporting_sellers":low_support,"confidence":confidence,"wide_spread":spread>1.5,
        "competition_low":xs[0],"competition_high":xs[-1],"estimated_resale":target,"estimated_range":[quick,xs[0]],
        "suggested_listing":listing,"quick_sale_model":quick,"quick_sale_basis":"90% of lowest competing ask; no sales speed measured",
        "regular_price_reference":None,"regular_price_status":"Not established; unmarked offers may also be discounted",
        "advertised_original_range":[min(advertised),max(advertised)] if advertised else None,
        "discount_overlap":overlap,"discount_note":"Same promotion or equally cheap competition exists; no exclusive edge implied" if overlap else "No exclusive discount advantage verified",
        "advertised_discount_competitors":sum(o.get("discount_status")=="advertised_discount" for o in offers),
        "same_promotion_references_excluded":promos,"acquisition_excluded":excluded,
        "acquisition_identity_status":"Exact known listing/seller IDs excluded; missing acquisition links/seller cannot be resolved from RSS",
        "item_price":buy,"delivery_known":known,"landed_cost":cost,"net":breakdown.net if breakdown else None,
        "roi":round(breakdown.net/cost*100,1) if breakdown and cost else None,
        "net_before_unknown_delivery":upper.net if not known else None,
        "max_landed_buy":maximum,"max_item_buy":round(maximum-delivery,2) if known else None,
        "delivery_headroom":round(maximum-buy,2),"fees":upper.platform_fee,"outbound_postage":upper.postage,
        "packaging":upper.packaging,"returns_allowance":upper.returns_allowance,
        "estimated_opportunity":opportunity,"worth_reviewing":worth_reviewing,"above_budget":watch_only,"policy":p,
        "review_stress_sale":stress_sale,"review_stress_net":stress.net if stress else None,"review_stress_roi":round(stress.net/cost*100,1) if stress else None,
        "review_stress_passed":stress_ok,"review_stress_basis":"Illustrative 10% resale drop, not a forecast or measured turnover; £5 net AND 10% ROI required",
        "review_max_landed_buy":min(policy.ceiling(buy + upper.net,p['review_net'],p['review_roi'],p['cap']),policy.ceiling(net_profit(stress_sale,0,"ebay_business",category,C.postage_for(category),C.PACKAGING,C.RETURNS_ALLOWANCE).net,p['review_stress_net'],p['review_stress_roi'],p['cap'])),
        "signal":"ABOVE BUDGET — WATCH ONLY" if watch_only else "ESTIMATED OPPORTUNITY — CHECK BEFORE BUYING" if opportunity else "WORTH REVIEWING — MANUAL CHECK" if worth_reviewing else "ASK-BASED RESALE ESTIMATE — NOT A BUY",
        "checks":blockers,"sources":offers[:10]}
    if category=='fragrance':
        from .transport import scenario
        sc=scenario(raw,target,when)
        model['transport_scenario']=sc
        # Market value and a conditional published-tariff scenario are separate from verified costs.
        model.update({k:None for k in ('net','roi','net_before_unknown_delivery','max_landed_buy','max_item_buy','delivery_headroom','fees','outbound_postage','packaging','returns_allowance','review_stress_net','review_stress_roi','review_max_landed_buy')})
        model.update(transport_validated=False,estimated_opportunity=False,worth_reviewing=False,review_stress_passed=False,
            signal='ABOVE BUDGET — WATCH ONLY' if above else 'ASK-BASED RESALE ESTIMATE — CHECK COSTS')
        model['checks'].insert(0,sc['profile']['reason'])
        model['checks'].insert(1,'Actual parcel/carrier and protective packaging costs unverified; conditional tariff scenario cannot create a buying signal')
        if snapshot.get('identity',{}).get('bottle_format')=='not stated':
            model['checks'].insert(1,'Bottle refillability/GTIN not stated: verify exact bottle revision; known refillable listings kept separate')
    return model

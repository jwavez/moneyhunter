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
    proceeds = net_profit(sale, 0, "ebay_business", category, C.postage_for(category), C.PACKAGING, C.RETURNS_ALLOWANCE).net
    return max(0, math.floor(min(proceeds-8, proceeds/1.4, 60)*100)/100)


def estimate(raw, snapshot, when=None):
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
    money_ok = bool(known and cost <= 60 and breakdown.net >= 8 and breakdown.net/cost >= .4)
    acquisition_resolved = str(raw.get("merchant", "")).casefold() != "ebay" or bool(ids or own_seller)
    coupon_unknown = any(o.get("available_coupons") and o["listed_total"] <= xs[0]*1.1 for o in offers)
    opportunity = not coupon_unknown and adequate and money_ok and raw.get("online_eligible") is True and acquisition_resolved
    blockers = ([] if adequate else ["Fewer than five independent sellers or fewer than two supporting the low price"])
    if coupon_unknown: blockers.append("Low competing offers advertise coupons; check effective competition before buying")
    if not acquisition_resolved: blockers.append("eBay acquisition listing identity missing; self-exclusion not confirmed")
    if not known: blockers.append("Inbound delivery unknown; profit is only an upper bound")
    if not money_ok: blockers.append("£8 net / 40% ROI / £60 landed cap not demonstrated")
    if not raw.get("online_eligible"): blockers.append("Online physical acquisition not confirmed")
    if raw.get("offer_verified") is not True: blockers.append("Check current retailer stock, checkout price and exact variant before buying")
    advertised = [o["advertised_original_total"] for o in offers if o.get("advertised_original_total") and not o.get("same_acquisition_promotion")]
    return {"model":MODEL,"category":category,"competitor_coupon_unknown":coupon_unknown,"basis":"Current competitor asking totals incl fixed shipping; estimated, NOT sold or guaranteed", "query":snapshot["query"],
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
        "estimated_opportunity":opportunity,"signal":"ESTIMATED OPPORTUNITY — CHECK BEFORE BUYING" if opportunity else "QUALIFIED ASK-BASED ESTIMATE",
        "checks":blockers,"sources":offers[:10]}

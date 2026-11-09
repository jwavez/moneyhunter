"""Commands:
  python -m moneyhunter.cli scan [--dry-run] [--max-posts N] [--show-all]
  python -m moneyhunter.cli test-webhook [--dry-run]
  python -m moneyhunter.cli capital 200 "start"
  python -m moneyhunter.cli buy "Samba OG UK9" trainers 38.00 --source Vinted --target 65 --floor 30
  python -m moneyhunter.cli sell 1 66.00 ebay_private --postage 2.62
  python -m moneyhunter.cli expense 4.99 "mailing bags"
  python -m moneyhunter.cli status
  python -m moneyhunter.cli uc 2026-11-08 2026-12-07 [--mif 1200 --no-startup --nil-limit 900 --capital 300]
"""
import argparse, json, os, sys
from . import config as C, comps as CP, grading as G, discord as D, ledger as L, benefits as B
from .fees import platform_fee
from . import embeds as E
from .scanners import hotukdeals, ebay, cex

STATE = os.path.join(os.path.dirname(__file__), "..", "data", "seen.json")

COMMUNITY_BANKROLL = 200.0   # [H] public starter (T1) rule set used by the shared scanner

def bankroll() -> float:
    if os.getenv("MONEYHUNTER_COMMUNITY") == "1":
        return E.TIER_BANKROLL[E.active_tier()]   # tier number only; no personal £ in the cloud
    env = os.getenv("MONEYHUNTER_BANKROLL")
    if env: return float(env)
    try:
        s = L.summary()
        if s["capital_in"] > 0: return s["bankroll"]
    except Exception:
        pass
    return 200.0

def checked_offer(raw, comp):
    import datetime as dt
    from . import matching
    if matching.quoted_offer_check(raw["title"], raw.get("desc", ""), comp): return None
    for offer in getattr(comp, "offers", []):
        from .evidence import age_hours
        age = age_hours(offer["observed_at"])/24
        if offer["url"] == raw["url"] and abs(offer["price"] - raw["price"]) < 0.005 and 0 <= age < C.MAX_OFFER_AGE_DAYS:
            return offer
    return None

def build_deal(raw: dict, comp) -> G.Deal:
    import datetime as dt
    offer = checked_offer(raw, comp) if comp else None
    inbound = offer["delivery"] if offer else raw.get("inbound_delivery")
    from . import hub
    d = G.Deal(title=raw["title"], url=raw["url"], buy_price=raw["price"], category=raw["category"],
               source=raw.get("source", "hotukdeals"), merchant=raw["merchant"], delivery=raw["delivery"], heat=raw.get("heat"),
               inbound_delivery=inbound or 0.0, delivery_known=inbound is not None,
               online_eligible=raw.get("online_eligible", False) and hub.resellable(raw), offer_verified=bool(offer))
    if comp:
        d.target, d.stretch = comp.low, comp.high
        d.floor, d.floor_verified = comp.floor, comp.floor is not None and comp.evidence_type == "sold"
        d.sold_90d, d.sell_through, d.days_to_sell = comp.sold_90d, comp.sell_through, comp.days_to_sell
        d.comp_note = f"{comp.evidence_type}: £{comp.low:g}–£{comp.high:g}: {comp.evidence} ({comp.source})"
        d.comp_age_days = comp.age_days()
        d.floor_age_days = (dt.date.today()-comp.floor_as_of).days if comp.floor_as_of else None
        d.velocity_age_days = (dt.date.today()-comp.velocity_as_of).days if comp.velocity_as_of else None
        d.evidence_type = comp.evidence_type
        d.comp_has_evidence = comp.evidence_type == "sold" and bool(comp.source_urls)
        d.floor_observed_at=getattr(comp,'floor_observed_at',None)
        d.evidence_record_id=getattr(comp,'evidence_record_id',None)
        d.evidence_revision=getattr(comp,'evidence_revision',None)
        d.comp_match = comp.match
        d.comp_urls = comp.source_urls
        d.offer_observed_at = offer["observed_at"] if offer else None
    return d

def _load_seen():
    if not os.path.exists(STATE): return set()
    with open(STATE) as f: seen = json.load(f)
    if not isinstance(seen, list) or not all(isinstance(k, str) for k in seen): raise ValueError("invalid alert state")
    return set(seen)

def _key(d):
    return hotukdeals.dedupe_key(d.title, d.buy_price)

LAST_RAWS = []
LIVE_CHECKS = 12   # [H] max deal-page expiry checks per scan (politeness)

def _intel(d, r):
    from . import intel as I, hub
    import json as _j
    prices = hub.read_prices()
    return {"retailer": I.retailer(d.merchant, d.title)["label"], "fake": I.fake_risk(d.category, d.merchant, d.title)["label"],
            "cashback": I.cashback(d.merchant), "history": I.price_history(hub.title_key(d.title), d.buy_price, prices),
            "camel": I.camel_url(d.url, d.title) if (d.merchant or "").lower() == "amazon" else ""}

def drop_expired(graded, br=200):
    """Only financially viable reviewed offers consume bounded expiry checks."""
    n = 0
    for i, (d, r) in enumerate(graded):
        if r.gates[0][1] and r.gates[1][1] and d.comp_has_evidence and d.offer_verified and d.online_eligible and d.delivery_known:
            d.availability = hotukdeals.live_status(d.url) if n < LIVE_CHECKS else "unknown"
            if n < LIVE_CHECKS: n += 1
            d.expired = d.availability == "expired"
            graded[i] = (d, G.grade(d, br))
    return n

def refresh_stale(comp):
    # Asking prices never rewrite a sold observation, its condition or evidence clock.
    return comp

def ebay_status() -> str:
    if not ebay.available(): return "skipped (no keys)"
    try: ebay._auth()
    except Exception as exc:
        return f"token FAILED (HTTP {getattr(exc, 'code', '?')}; {type(exc).__name__})"
    return "token OK" + (", Insights scope granted (sold importer not configured)" if ebay.insights_available() else ", active listings only (no Insights entitlement confirmed)")

LAST_OPERATIONAL = {}
LAST_REVIEW = []
OPERATIONAL = os.path.join(os.path.dirname(STATE), "scan_state.json")
REVIEW_PATH = os.path.join(os.path.dirname(STATE), "review_queue.json")

def run_scan():
    from . import runtime as RT, hub
    import datetime as dt
    global LAST_RAWS, LAST_OPERATIONAL, LAST_REVIEW
    ebay_health = ebay_status()
    print(f"[ebay] {ebay_health}")
    br = bankroll(); tier = C.tier_for(br); cap = min(br * tier.max_pct / 100, E.community_cap())
    errors = []
    warnings = []
    if "FAILED" in ebay_health: errors.append("eBay authentication failed; competition context unavailable")
    if os.getenv("MH_TIER_WARNING"): warnings.append("Using starter policy: £60 cap, £8 net + 40% ROI Strong threshold")
    operational = RT.load(OPERATIONAL)
    from . import watchlist
    operational['detail_run']={'calls':0,'cached':0,'errors':[],'reserved_tools':2}
    from . import details as _details_slot
    _details_slot.reset_slot_log()
    when=RT.now()
    raws = hotukdeals.scan(log=lambda m: (print(m), errors.append(m)))
    from .scanners import capture
    raws = capture.merge(raws, capture.scan(log=lambda m: (print(m), errors.append(m))))
    from . import variants
    raws=[variants.attach_source_identity(r) for r in raws]
    watchlist.migrate(operational,when)
    persistent_health=watchlist.refresh_stale(operational,when,budget=2)
    watchlist.build(operational,when)
    from .scanners import discovery
    from . import policy
    raws += discovery.scan(raws, operational)
    errors.extend(discovery.LAST_DIAGNOSTICS["errors"])
    from . import images
    from . import product_format as PF
    raws,nonphysical=PF.partition(raws)
    image_report=images.prepare(raws,operational)
    LAST_RAWS = raws
    counts = RT.observe(raws, operational)
    if counts["gap_minutes"] is not None and counts["gap_minutes"] > C.MAX_SCAN_GAP_MINUTES:
        errors.append(f"Scan gap {counts['gap_minutes']:.0f} minutes; 30-minute cron is best effort")
    comps = CP.load()
    from . import review_bridge
    comps = review_bridge.load(comps) + comps
    graded, unpriced, review = [], [], []
    for raw in raws:
        raw.pop("ask_estimate",None)  # Rebuild derived models; never count retained stale models as newly priced.
        # Reviewed exact retailer offers can resolve attributes omitted by a feed title.
        comp = next((c for c in comps if c.evidence_type == "sold" and checked_offer(raw, c)), None)
        why_not = ""
        if comp is None: comp, why_not = CP.find_with_reason(raw["title"], comps, raw.get("desc", ""))
        d = build_deal(raw, comp)
        if d.delivery_known: raw["inbound_delivery"] = d.inbound_delivery
        d.identity_evidence=raw.get("identity_evidence",[])
        d.thumb = raw.get("thumb", ""); d.match_warning = why_not
        for attr in ("image_status","image_verified_url","image_verified_until","image_basis","image_source_url","image_candidates"):setattr(d,attr,raw.get(attr))
        res = G.grade(d, br)
        if res is None: unpriced.append(d)
        else:
            d.intel = _intel(d, res)
            graded.append((d, res))
        if hub.resellable(raw) and d.online_eligible and d.buy_price + d.inbound_delivery <= policy.current()["watch_ceiling"]:
            blockers = E.gates_failed(res) if res else [why_not or "No exact reviewed sold observations"]
            if not d.delivery_known and "Inbound delivery unknown" not in blockers: blockers.append("Inbound delivery unknown")
            be, required, _ = hub.sell_needed(d.buy_price + d.inbound_delivery, d.category)
            transport_scenario=None
            if d.category=='fragrance':
                from .transport import scenario
                transport_scenario=scenario(raw)
                be=transport_scenario['breakeven'];required=transport_scenario['required_resale']
            # Priority is research usefulness, NOT projected profit. Prefer identifiable affordable products.
            score = (20 if comp and comp.evidence_type == "sold" else 0) + (10 if counts["new"] and RT.key(raw) in operational["items"] and operational["items"][RT.key(raw)]["observations"] == 1 else 0)
            import re
            score += 10 if re.search(r"\b(?:[a-z]{2,}\d{2,}|\d{5,6})\b", raw["title"], re.I) else 0
            score += 5 if d.delivery_known else 0
            raw["review_priority"] = score
            review.append({"title": d.title, "url": d.url,"policy_key":__import__("moneyhunter.routing",fromlist=["policy_key"]).policy_key(d.url), "category": d.category,"source":raw.get("source","hotukdeals"),"price_basis":raw.get("price_basis"),"identity_evidence":raw.get("identity_evidence",[]),"primary_offer_status":raw.get("primary_offer_status"),"secondary_offer_note":raw.get("secondary_offer_note"),"offer_ambiguity":raw.get("offer_ambiguity"),"merchant":raw.get("merchant",""), "item_price": d.buy_price,
                **{k:raw.get(k) for k in ("image_status","image_verified_url","image_verified_until","image_checked_at","image_candidates")},
                "thumb":raw.get("thumb",""),"image_basis":raw.get("image_basis",""),"image_source_url":raw.get("image_source_url",""),
                "landed_cost": d.buy_price + d.inbound_delivery if d.delivery_known else None,
                "breakeven_sell": be, "sell_for_minimum_profit": required,
                **({"transport_scenario":transport_scenario} if transport_scenario else {}),
                "outbound_transport_status":transport_scenario["profile"]["reason"] if transport_scenario else "configured rate; verify acceptance",
                "cost_basis": "Conditional published Royal Mail tariff scenario, not actual verified parcel costs" if transport_scenario else ("landed" if d.delivery_known else "item-only lower bound; delivery unknown"),
                "blockers": blockers, "priority": score, "first_seen": operational["items"][RT.key(raw)]["first_seen"],
                "sold_search": E.ebay_sold_url(E.short_query(d.title))})
    from . import market
    review.sort(key=lambda r: (-r["priority"], r["item_price"], r["url"]))
    # Independent research slots prevent above-budget discovery starving affordable offers.
    within = [r for r in review if (r['landed_cost'] if r['landed_cost'] is not None else r['item_price']) <= cap]
    above = [r for r in review if (r['landed_cost'] if r['landed_cost'] is not None else r['item_price']) > cap]
    tools_health=market.enrich([r for r in within if r['category']=='tools'],raws,operational,budget=2,lane='asking-tools')
    ask_health = market.enrich(within, raws, operational, budget=2, lane="asking-affordable")
    ask_health['tools_research']=tools_health
    ask_health['queries']+=tools_health['queries'];ask_health['errors']+=tools_health['errors']
    watch_health = market.enrich(above, raws, operational, budget=2, lane="asking-watch")
    ask_health['above_budget_research'] = watch_health
    ask_health['errors'] += watch_health['errors']
    errors.extend(ask_health["errors"])
    from . import asking
    raw_by_url = {raw["url"]: raw for raw in raws}
    for entry in review:
        raw_by_url[entry["url"]]["ask_status"]=entry.get("ask_status","not queried")
        if entry.get("ask_context"):
            model = asking.estimate(raw_by_url[entry["url"]], entry["ask_context"])
            if model:
                entry["ask_estimate"] = model
                raw_by_url[entry["url"]]["ask_estimate"] = model
    ask_by_url = {r["url"]: r.get("ask_context") for r in review if r.get("ask_context")}
    for deal, res in graded:
        deal.ask_context = ask_by_url.get(deal.url)
        deal.ask_estimate=raw_by_url.get(deal.url,{}).get('ask_estimate')
        deal.publication_listing=res.plan['list']
    # Diagnosis only: tools detail sub-check failures. Never changes gates/routes/parsers.
    try:
        from . import tools_detail_diagnostic
        tools_detail_diagnostic.log_tool_detail_failures(
            offers=raws,
            research_rows=review,
            out_path='tools_detail_diagnostic.json',
        )
    except Exception as exc:
        import json as _json, traceback as _tb
        from pathlib import Path as _Path
        _Path('tools_detail_diagnostic.json').write_text(_json.dumps({
            'entries': [],
            'error': f'{type(exc).__name__}: {exc}',
            'traceback': _tb.format_exc(),
        }, indent=2, sort_keys=True) + '\n')
    # Diagnosis only: tools getItem slot allocation. Never changes reservation/ordering/dedup.
    try:
        from . import tools_slot_diagnostic
        tools_slot_diagnostic.log_tool_slot_allocation(
            offers=raws,
            research_rows=review,
            out_path='tools_slot_diagnostic.json',
            state=operational,
        )
    except Exception as exc:
        import json as _json, traceback as _tb
        from pathlib import Path as _Path
        _Path('tools_slot_diagnostic.json').write_text(_json.dumps({
            'entries': [],
            'identity_groups': [],
            'slot_summary': {},
            'error': f'{type(exc).__name__}: {exc}',
            'traceback': _tb.format_exc(),
        }, indent=2, sort_keys=True) + '\n')
    checked = drop_expired(graded, br)
    # Reviewed sold valuations must use the same publication/count/route pipeline,
    # not disappear from raw research merely because no asking model exists.
    sold_fields=('evidence_type','evidence_record_id','evidence_revision','sold_sources','sold_90d','comp_age_days','publication_listing','plan','buy','postage','grade','delivery_known','availability','offer_verified','net','roi')
    for deal,result in graded:
        if deal.evidence_type=='sold':
            facts=_public_deal(deal,result)
            raw_by_url[deal.url].update({k:facts[k] for k in sold_fields})
            for entry in review:
                if entry['url']==deal.url:entry.update({k:facts[k] for k in sold_fields})
    order = {"A": 0, "B": 1, "R": 2}
    graded=[(d,r) for d,r in graded if not PF.reason(vars(d))]
    graded.sort(key=lambda x: (order[x[1].grade[0]], -x[1].ev_net))
    affordable = [(d, r) for d, r in graded if r.cost <= cap and d.delivery_known]
    diagnostics = hotukdeals.LAST_DIAGNOSTICS
    if not raws: errors.append("No deals read from any feed")
    from . import publication
    retail=[r for r in raws if r.get('source','hotukdeals')!='ebay_browse']
    landed_under=[r for r in retail if r.get('inbound_delivery') is not None and r['price']+r['inbound_delivery']<=cap]
    revalued=[r for r in landed_under if r.get('ask_estimate')]
    revaluation={'retailer_offers':len(retail),'known_landed_under_cap':len(landed_under),'under_cap_revalued_independently':len(revalued),'under_cap_supported':sum(publication.allowed(r) for r in revalued),'under_cap_without_model':len(landed_under)-len(revalued),'retailer_unknown_delivery':sum(r.get('inbound_delivery') is None for r in retail),'method':'All-seller NEW UK shipped competition; excludes only acquisition URLs/item IDs and own seller; cheaper independent promotions retained; not a BUY.'}
    stats = {"retailer_revaluation":revaluation,"scanned": len(raws), "priced": len(graded), "unpriced": len(unpriced), "affordable": len(affordable),
             "A": sum(r.grade[0] == "A" for _, r in affordable), "B": sum(r.grade[0] == "B" for _, r in affordable),
             "R": sum(r.grade == "REJECT" for _, r in graded),
             "rejected_reference":sum(r.grade=="REJECT" and d.evidence_type!="sold" for d,r in graded),"rejected_sold":sum(r.grade=="REJECT" and d.evidence_type=="sold" for d,r in graded),
             "uncertain": sum(bool(getattr(d, "match_warning", "")) for d in unpriced),
             "stale": sum(d.comp_age_days is None or d.comp_age_days > C.MAX_COMP_AGE_DAYS for d, _ in graded),
             "expired": sum(getattr(d, "expired", False) for d, _ in graded), "expiry_checked": checked,
             "expiry_unknown": sum(d.availability == "unknown" for d, _ in graded),
             "sold_valued": sum(d.evidence_type == "sold" for d, _ in graded),
             "reference_only": sum(d.evidence_type != "sold" for d, _ in graded),
             "online_eligible": sum(r.get("online_eligible", False) and hub.resellable(r) for r in raws),
             "under_cap_known_delivery": sum(r.get("inbound_delivery") is not None and r["price"] + r["inbound_delivery"] <= cap for r in raws),
             "delivery_known": sum(r.get("inbound_delivery") is not None for r in raws),
             "ask_valued": sum(bool(r.get("ask_estimate")) for r in review),
             "estimated_opportunities": sum(bool(r.get("ask_estimate", {}).get("estimated_opportunity")) for r in review),
             "worth_reviewing":sum(bool(r.get("ask_estimate",{}).get("worth_reviewing")) for r in review),
             "above_budget_estimates":sum(bool(r.get("ask_estimate",{}).get("above_budget")) for r in review),
             "above_budget_candidates":sum((r['landed_cost'] if r['landed_cost'] is not None else r['item_price']) > cap for r in review),
             "above_budget_researched":sum(bool(r.get("ask_context")) for r in above),
             "above_budget_research_candidates":len(above),
             "acquisition_by_source":{source:sum(r.get('source','hotukdeals')==source for r in raws) for source in {r.get('source','hotukdeals') for r in raws}},
             "qualified_delivery_unknown": sum(bool(r.get("ask_estimate")) and not r["ask_estimate"]["delivery_known"] for r in review),
             "ask_delivery_known":sum(bool(r.get('ask_estimate')) and r['ask_estimate']['delivery_known'] for r in review),
             "ask_unique_products":len({(r["category"],r["ask_context"]["query"]) for r in review if r.get("ask_estimate")}),
             "ask_research_identities":len({market.cache_key(market.identity(raw_by_url[r["url"]])) for r in review if r.get("ask_estimate")}),
             "without_any_pricing":sum(r['url'] not in {d.url for d,_ in graded} and not r.get('ask_estimate') for r in raws),
             "pricing_coverage":{cat:{"offers":sum(r.get('category')==cat for r in raws),
                 "exact_identity":sum(market.identity(r) is not None for r in raws if r.get('category')==cat),
                 "estimated_offers":sum(bool(r.get('ask_estimate')) for r in review if r['category']==cat),
                 "estimated_products":len({r['ask_context']['query'] for r in review if r['category']==cat and r.get('ask_estimate')}),
                 "supported_retailer_identities":len({(str(r.get('merchant','')).casefold(),market.cache_key(market.identity(r))) for r in raws if r.get('category')==cat and r.get('source','hotukdeals')!='ebay_browse' and publication.allowed(r) and market.identity(r)})}
                 for cat in sorted({r.get('category') for r in raws})},
             "browse_usage":operational.get('browse_usage',{}),
             "warnings":warnings[:20], "errors": errors[:20], "sources": {"hotukdeals": diagnostics,
                 "ebay": {"status": ebay_health, "purpose": "active asking competition only", "research": ask_health},
                 "capture_buffer": capture.LAST_DIAGNOSTICS,
                 "ebay_acquisition":discovery.LAST_DIAGNOSTICS,
                 "reviewed_bridge":review_bridge.LAST_STATUS, "cash_floors": {"automatic_source": False, "status": "reviewed exact cash quotes only"}}, **counts}
    if raws and not diagnostics.get("feeds_failed"): operational["last_success"] = RT.stamp(RT.now())
    operational["ask_cache"] = {k:v for k,v in operational["ask_cache"].items() if k == "browse-blocked" or v.get("date", "") >= (dt.date.today()-dt.timedelta(days=7)).isoformat()}
    LAST_OPERATIONAL = operational
    # Update blockers after the availability checks rather than exporting stale preliminary reasons.
    by_url = {d.url: (d, r) for d, r in graded}
    for entry in review:
        if entry["url"] in by_url: entry["blockers"] = E.gates_failed(by_url[entry["url"]][1])
    LAST_REVIEW = sorted([r for r in review if r["blockers"]], key=lambda r: (-bool(r.get("ask_estimate", {}).get("estimated_opportunity")), -bool(r.get("ask_estimate",{}).get("worth_reviewing")), -bool(r.get("ask_estimate")), -r["priority"], r["item_price"], r["url"]))
    from . import publication
    hold_state=operational.setdefault('publication_holds',{})
    hold_counts={};eligible=0
    for raw in raws:
        result=publication.proof(raw)
        raw['publication_proof']=result
        if raw['url'] in {r['url'] for r in review}:
            next(r for r in review if r['url']==raw['url'])['publication_proof']=result
        if result['ok']:eligible+=1;hold_state.pop(raw['url'],None)
        else:
            key=result['reason'];hold_counts[key]=hold_counts.get(key,0)+1
            prior=hold_state.get(raw['url'],{})
            hold_state[raw['url']]={'reason':key,'category':raw['category'],'first_held':prior.get('first_held',RT.stamp(RT.now())),'last_checked':RT.stamp(RT.now())}
    operational['publication_holds']=dict(list(hold_state.items())[-1000:])
    stats['publication_holds']={'eligible':eligible,'held':len(raws)-eligible,'reasons':hold_counts,'by_category':{c:sum(r['category']==c and not publication.allowed(r) for r in raws) for c in {r['category'] for r in raws}}}
    # Diagnosis only: tools publication blockers. Never changes gates/routes/state.
    try:
        from . import tools_diagnostic
        tools_diagnostic.log_tool_publication_reasons(
            offers=raws,
            research_rows=review,
            publication_rows=raws,
            out_path='tools_diagnostic.json',
        )
    except Exception as exc:
        import json as _json, traceback as _tb
        from pathlib import Path as _Path
        _Path('tools_diagnostic.json').write_text(_json.dumps({
            'entries': [],
            'error': f'{type(exc).__name__}: {exc}',
            'traceback': _tb.format_exc(),
        }, indent=2, sort_keys=True) + '\n')
    stats['excluded_nonphysical']=nonphysical
    stats['source_coverage']={source:{'offers':sum(r.get('source','hotukdeals')==source for r in raws),
        'new':sum(r.get('source','hotukdeals')==source and operational['items'][RT.key(r)]['observations']==1 for r in raws),
        'estimated':sum(r.get('source','hotukdeals')==source and bool(r.get('ask_estimate')) for r in raws),
        'actionable':sum(r.get('source','hotukdeals')==source and bool(r.get('ask_estimate',{}).get('estimated_opportunity') or r.get('ask_estimate',{}).get('worth_reviewing')) for r in raws)}
        for source in sorted({r.get('source','hotukdeals') for r in raws})}
    stats['value_watchlist']=watchlist.build(operational,RT.now(),inspect=False)
    stats['persistent_research']=persistent_health
    stats['item_details']=dict(operational['detail_run'])
    from . import routing
    stats['publication_stages']=routing.stages(raws,graded)
    above_priced=[r for r in raws if publication.allowed(r) and images.publishable(r) and r.get('inbound_delivery') is not None and r['price']+r['inbound_delivery']>cap]
    if above_priced:
        n=min(above_priced,key=lambda r:r['price']+r['inbound_delivery'])
        stats['nearest_above_cap']={'title':n['title'],'landed':n['price']+n['inbound_delivery'],'gap':round(n['price']+n['inbound_delivery']-cap,2),'url':n['url']}

    stats['routing_destinations']=hub.destination_roles()
    stats['nearest_priced_misses']=routing.nearest(raws)
    stats['notification_delivery']={'mode':stats.get('delivery_mode','pending'),'product_messages_delivered':0,'by_route':{}}
    stats["review_candidates"] = len(LAST_REVIEW)
    stats["lego_image_validation"]=image_report
    stats["images_available"] = sum(bool(r.get("thumb")) for r in raws)
    stats["lego_images_available"] = sum(bool(r.get("thumb")) for r in raws if r.get("category")=="lego")
    return br, tier, graded, affordable, unpriced, stats

def _public_deal(d, r):
    """Community-safe fields only: no bankroll, stake, tier or ledger data."""
    import re as _re
    e_rev = r.cost + r.ev_net
    return {"title": d.title[:200], "url": d.url, "merchant": d.merchant, "category": d.category, "grade": r.grade[0] if r.grade[0] in "AB" else "R",
            "buy": round(r.cost, 2), "target": round(r.plan["target"], 2), "net": round(r.ev_net, 2), "roi": round(r.ev_roi, 1),
            "worst": round(r.worst, 2), "worst_verified": r.worst_verified, "confidence": int(r.confidence),
            "comp_age_days": d.comp_age_days, "expired": getattr(d, "expired", False), "intel": getattr(d, "intel", {}),
            "postage": r.postage, "fees_basis": "eBay business standard fees incl 20% VAT, free-to-buyer postage, £0.50 packaging, 3% returns; promotions/surcharges extra",
            "max_buy": E.max_buy(r),
            **{k:getattr(d,k,None) for k in ("image_status","image_verified_url","image_verified_until","image_basis","image_source_url","image_candidates")},
            "why": (["Deal expired"] if getattr(d, "expired", False) else []) + E.gates_failed(r)[:3], "thumb": getattr(d, "thumb", ""), "comp": (d.comp_note or "")[:200],
            "ebay_sold": E.ebay_sold_url(E.short_query(d.title)), "vinted": E.vinted_url(E.short_query(d.title)),
            "delivery": d.delivery, "days_to_sell": d.days_to_sell, "under_cap": r.cost <= E.community_cap() and d.delivery_known,
            "identity_evidence":getattr(d,"identity_evidence",[]),"evidence_record_id":getattr(d,"evidence_record_id",None),"evidence_revision":getattr(d,"evidence_revision",None),"evidence_type": d.evidence_type, "sold_sources": getattr(d, "comp_urls", [])[:10],
            "floor_age_days": d.floor_age_days, "velocity_age_days": d.velocity_age_days,
            "offer_observed_at": getattr(d, "offer_observed_at", None), "delivery_known": d.delivery_known, "availability": d.availability,
            "valuation_status": "reviewed_sold" if d.evidence_type == "sold" and d.delivery_known else "reference_or_item_only_estimate",
            "offer_verified": d.offer_verified, "ask_context": getattr(d, "ask_context", None),"ask_estimate":getattr(d,"ask_estimate",None),"publication_proof":__import__("moneyhunter.publication",fromlist=["proof"]).proof({**vars(d),"title":d.title[:200]}),
            "sold_90d":d.sold_90d,"publication_listing":r.plan["list"],"plan": {k: r.plan[k] for k in ("list", "target", "quick", "floor", "time_stop_day", "time_stop_rule", "platforms")}}

def export_public(path, stats, graded):
    import datetime as dt
    from .evidence import public_catalog
    from . import review_bridge
    catalog = public_catalog(os.path.join(os.path.dirname(CP.PATH), "evidence.json")) + review_bridge.catalog()
    stats["pricing_products"] = len(catalog)
    stats["pricing_observations"] = sum(c["sample_count"] for c in catalog)
    # Full bounded provenance remains in scan_state; keep the bot response compact.
    review_export = [{**r, **({"ask_context": {**r["ask_context"], "offers": r["ask_context"]["offers"][:10]}} if r.get("ask_context") else {})} for r in LAST_REVIEW]
    asking = {r["ask_context"]["query"]: r["ask_context"] for r in review_export if r.get("ask_context")}
    out = {"value_watchlist":list(LAST_OPERATIONAL.get("value_watchlist",{}).values()),"pricing_catalog": catalog, "asking_catalog": list(asking.values()), "pricing_status": {
               "indicative_asking_products": sum(v["sample_count"] > 0 for v in asking.values()),
               "automatic_asking_estimates": True,
               "ask_estimated_products": len({r["ask_estimate"]["query"] for r in LAST_REVIEW if r.get("ask_estimate")}),
               "estimated_opportunities": stats.get("estimated_opportunities", 0),
               "worth_reviewing":stats.get("worth_reviewing",0),"above_budget_estimates":stats.get("above_budget_estimates",0),
               "automatic_sold_feed": False, "products": len(catalog),
               "sold_observations": stats["pricing_observations"],
               "blocker": None if catalog else "No fresh directly verified exact-product sold observations imported; active asks are not sold data"},
           "generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "price_cap": E.community_cap(),
           "schema_version": 3, "review_queue": review_export, "stats": stats, "deals": [_public_deal(d, r) for d, r in graded[:40]]}
    if os.getenv("MONEYHUNTER_DISABLE_SEND")=="1":
        from . import publication
        from . import discord as D,images,hub
        import re
        sample=[];categories=set()
        for r in sorted(LAST_RAWS,key=lambda r:not bool(re.search(r'72051|resident evil requiem',r['title'],re.I))):
            if publication.allowed(r) and hub.resellable(r) and (r['category'] not in categories or re.search(r'72051|resident evil requiem',r['title'],re.I)):
                sample.append(r);categories.add(r['category'])
        out['clarity_publication_previews']=[{'source_url':r['url'],'payload':D.build_payload([hub.watch_card(r,{})],components=hub.buttons(r))} for r in sample[:12]]
        out['all_publication_previews']=[{'source_url':r['url'],'route':'opportunities' if __import__('moneyhunter.routing',fromlist=['opportunity']).opportunity(r) else 'research-watch','payload':D.build_payload([hub.watch_card(r,{})],components=hub.buttons(r))} for r in LAST_RAWS if publication.allowed(r) and images.publishable(r)]
        out["fragrance_publication_previews"]=[{"source_url":r["url"],"payload":D.build_payload([hub.watch_card(r,{})],components=hub.buttons(r))} for r in LAST_RAWS if r.get("category")=="fragrance" and publication.allowed(r)]
        out["lego_publication_previews"]=[{"source_url":r["url"],"payload":D.build_payload([hub.watch_card(r,{})],components=hub.buttons(r))} for r in LAST_RAWS if r.get("category")=="lego" and images.publishable(r) and publication.allowed(r)]
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    from .evidence import atomic_write
    atomic_write(path, out); print(f"[export] {path}: {len(out['deals'])} deals")

def cmd_scan(a):
    no_send = getattr(a, "no_send", False)
    if no_send: os.environ["MONEYHUNTER_DISABLE_SEND"] = "1"
    br, tier, graded, affordable, unpriced, stats = run_scan()
    stats["delivery_mode"] = "disabled" if no_send or a.dry_run else "live"
    stats.setdefault("notification_delivery",{"product_messages_delivered":0,"by_route":{}})["mode"]=stats["delivery_mode"]
    stats["execution"] = {"revision": os.getenv("GITHUB_SHA"), "run_id": os.getenv("GITHUB_RUN_ID"),
                          "event": os.getenv("GITHUB_EVENT_NAME"), "parent_run_id": os.getenv("MH_PARENT_RUN_ID") or None}
    who = "Rules: community starter set" if os.getenv("MONEYHUNTER_COMMUNITY") == "1" else f"Bankroll £{br:.2f} → {tier.name}"
    print(f"{who}. eBay API: {ebay_status()}. CeX: no automated quotes (manual exact cash evidence required).")
    print(f"Scanned {stats['scanned']} · priced {stats['priced']} · under cap {stats['affordable']} · A {stats['A']} · B {stats['B']} · rejected {stats['R']} · unpriced {stats['unpriced']}")
    for d, r in graded:
        print(f"  [{r.grade:10}] {d.title[:60]:60} £{r.cost:7.2f} → £{r.plan['target']:.2f} · EV £{r.ev_net:6.2f} · {', '.join(E.gates_failed(r)[:2])}")
    if a.show_all:
        for d in unpriced[:40]: print(f"  [unpriced {d.category:10}] £{d.buy_price:7.2f} {d.title[:70]}")
    seen = _load_seen()
    near = [(d, r) for d, r in affordable if r.grade == "REJECT"][:6]
    from . import hub
    raws = LAST_RAWS
    # Publish real observations without simulating successful alert deliveries.
    if no_send:
        new = set()
        stats["delivery_failures"] = 0
        if not a.dry_run:
            from .evidence import atomic_write
            _, prices = hub.price_drops(raws)
            atomic_write(hub.PRICES, prices)
    else:
        new = hub.route(raws, graded, stats, near, seen, dry=a.dry_run, max_cards=a.max_posts)
    if not a.dry_run:
        from . import runtime as RT
        RT.save(STATE, sorted(seen | new))
        RT.save(OPERATIONAL, LAST_OPERATIONAL)
        RT.save(REVIEW_PATH, {"schema_version": 1, "candidates": LAST_REVIEW})
    if a.export:
        export_public(a.export, stats, graded)
    print(f"[hub] {len(new)} new items routed")

def cmd_digest(a):
    from . import hub; hub.digest(a.deals, dry=a.dry_run)

def cmd_leaderboard(a):
    from . import hub; hub.leaderboard(a.api, dry=a.dry_run)

def private_report(a) -> str:
    """LOCAL ONLY. Never posted to Discord."""
    import datetime as dt
    s = L.summary(); today = dt.date.today(); pd = min(a.period_day, 28)
    start = today.replace(day=pd) if today.day >= pd else (today.replace(day=1) - dt.timedelta(days=1)).replace(day=pd)
    p = L.assessment_period(start.isoformat(), today.isoformat()); uc = B.uc_period(p["receipts"], p["expenses"])
    tier = C.tier_for(s["bankroll"]); xp = int(max(0, s["realised_profit"])) + 25 * s["sold_count"]
    lines = [f"# MONEYHUNTER private report · {today.isoformat()}", "",
             f"- Bankroll: £{s['bankroll']:.2f} ({tier.name}) · cash £{s['cash']:.2f}",
             f"- Open stock: {s['open_items']} items · £{s['stock_cost']:.2f}",
             f"- Realised P&L: £{s['realised_profit']:.2f} · flips sold {s['sold_count']} · XP {xp} · streak {L.streak()} day(s)",
             f"- Trading allowance (gross this tax year): £{s['gross_tax_year']:.2f} / £1,000",
             f"- UC assessment period from {start.isoformat()}: {json.dumps(uc)}",
             f"- Capital: {json.dumps(B.capital_effect(s['cash']))}", "",
             "_Local only. Not tax or benefits advice._"]
    return "\n".join(lines)

def cmd_hud(a):
    out = private_report(a); print(out)
    if a.private:
        path = os.path.join(os.path.dirname(STATE), "private_report.md")
        open(path, "w").write(out + "\n"); print(f"[saved] {path}")

def cmd_test(a):
    emb = {"title": "MONEYHUNTER is live", "color": D.COLORS["T"],
           "description": "Test alert. Deals are graded A (buy), B (numbers work, verify comps and floor) or rejected. Only A/B are posted.",
           "fields": [{"name": "Schedule", "value": E.SCHEDULE, "inline": True}]}
    st = D.post([emb], dry_run=a.dry_run); print(f"[discord] status: {st if st else 'dry-run'}")

def cmd_status(a):
    s = L.summary(); print(json.dumps(s, indent=2))
    print(json.dumps(B.tax_meters(s["gross_tax_year"], s["platform_year"]), indent=2))
    print(json.dumps(B.capital_effect(s["cash"]), indent=2))

def cmd_uc(a):
    p = L.assessment_period(a.start, a.end)
    out = B.uc_period(p["receipts"], p["expenses"], a.loss_bf, a.mif, not a.no_startup, a.nil_limit, a.surplus_bf)
    out["capital"] = B.capital_effect(a.capital if a.capital is not None else L.summary()["cash"])
    print(json.dumps(out, indent=2))

def main(argv=None):
    ap = argparse.ArgumentParser(prog="moneyhunter"); sp = ap.add_subparsers(dest="cmd", required=True)
    s = sp.add_parser("scan"); s.add_argument("--dry-run", action="store_true"); s.add_argument("--no-send", action="store_true", help="persist genuine scan/research state, but disable routing and do not acknowledge alerts"); s.add_argument("--max-posts", type=int, default=5); s.add_argument("--show-all", action="store_true"); s.add_argument("--include-rejects", type=int, default=0); s.add_argument("--summary", action="store_true", help="post the scan report even with no cards"); s.add_argument("--preview", action="store_true"); s.add_argument("--export", help="write community deals JSON, e.g. public/deals.json"); s.set_defaults(f=cmd_scan)
    s = sp.add_parser("import-evidence", help="validate and atomically merge reviewed public sold evidence")
    s.add_argument("file"); s.add_argument("--store", default=os.path.join(os.path.dirname(STATE), "evidence.json"))
    def import_evidence(a):
        from .evidence import ingest
        print(f"Imported {ingest(a.file, a.store)} reviewed record(s). Commit reviewed evidence.json to persist on scheduled scans.")
    s.set_defaults(f=import_evidence)
    s = sp.add_parser("digest"); s.add_argument("--deals", default="public/deals.json"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(f=cmd_digest)
    s = sp.add_parser("leaderboard"); s.add_argument("--api", default="https://moneyhunter-bot.moneyhunter.workers.dev/api/leaderboard"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(f=cmd_leaderboard)
    s = sp.add_parser("hud", help="LOCAL ONLY private report"); s.add_argument("--private", action="store_true", help="also write data/private_report.md"); s.add_argument("--period-day", type=int, default=1, help="day of month your UC assessment period starts"); s.set_defaults(f=cmd_hud)
    s = sp.add_parser("test-webhook"); s.add_argument("--dry-run", action="store_true"); s.set_defaults(f=cmd_test)
    s = sp.add_parser("capital"); s.add_argument("amount", type=float); s.add_argument("note", nargs="?", default="top-up"); s.set_defaults(f=lambda a: L.add_capital(a.amount, a.note))
    s = sp.add_parser("expense"); s.add_argument("amount", type=float); s.add_argument("note"); s.set_defaults(f=lambda a: L.add_expense(a.amount, a.note))
    s = sp.add_parser("buy"); s.add_argument("title"); s.add_argument("category"); s.add_argument("cost", type=float)
    s.add_argument("--source", default=""); s.add_argument("--url", default=""); s.add_argument("--target", type=float); s.add_argument("--floor", type=float)
    s.set_defaults(f=lambda a: print("item id", L.buy(a.title, a.category, a.cost, a.source, a.url, a.target, a.floor)))
    s = sp.add_parser("sell"); s.add_argument("item_id", type=int); s.add_argument("price", type=float); s.add_argument("platform")
    s.add_argument("--fees", type=float); s.add_argument("--postage", type=float, default=0.0); s.add_argument("--packaging", type=float, default=0.5); s.add_argument("--category", default="default")
    s.set_defaults(f=lambda a: L.sell(a.item_id, a.price, a.platform, a.fees if a.fees is not None else platform_fee(a.platform, a.price, a.category), a.postage, a.packaging))
    s = sp.add_parser("status"); s.set_defaults(f=cmd_status)
    s = sp.add_parser("uc"); s.add_argument("start"); s.add_argument("end"); s.add_argument("--mif", type=float); s.add_argument("--no-startup", action="store_true")
    s.add_argument("--nil-limit", type=float); s.add_argument("--loss-bf", type=float, default=0.0); s.add_argument("--surplus-bf", type=float, default=0.0); s.add_argument("--capital", type=float)
    s.set_defaults(f=cmd_uc)
    a = ap.parse_args(argv); a.f(a)

if __name__ == "__main__":
    main()

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
        return COMMUNITY_BANKROLL
    env = os.getenv("MONEYHUNTER_BANKROLL")
    if env: return float(env)
    try:
        s = L.summary()
        if s["capital_in"] > 0: return s["bankroll"]
    except Exception:
        pass
    return 200.0

def build_deal(raw: dict, comp) -> G.Deal:
    d = G.Deal(title=raw["title"], url=raw["url"], buy_price=raw["price"], category=raw["category"],
               source="hotukdeals", merchant=raw["merchant"], delivery=raw["delivery"], heat=raw.get("heat"))
    if comp:
        d.target, d.stretch = comp.low, comp.high     # buy off the downside: target = low end of sold range
        d.floor, d.floor_verified = comp.floor, comp.floor is not None
        d.sold_90d, d.sell_through, d.days_to_sell = comp.sold_90d, comp.sell_through, comp.days_to_sell
        d.comp_note = f"Range £{comp.low:g}–£{comp.high:g}: {comp.evidence} ({comp.source})"
    return d

def _load_seen():
    return set(json.load(open(STATE))) if os.path.exists(STATE) else set()

def _key(d):
    return hotukdeals.dedupe_key(d.title, d.buy_price)

def run_scan():
    br = bankroll(); tier = C.tier_for(br); cap = min(br * tier.max_pct / 100, E.COMMUNITY_MAX_PRICE)
    raws = hotukdeals.scan(); comps = CP.load()
    graded, unpriced = [], []
    for r in raws:
        comp = CP.find(r["title"], comps)
        d = build_deal(r, comp); d.thumb = r.get("thumb", "")
        res = G.grade(d, br)
        if res is None: unpriced.append(d); continue
        if ebay.available():
            try:
                st = ebay.active_stats(comp.match); d.comp_note += f" · eBay active {st['active']}, median ask £{st['median_ask']}"
            except Exception as e:
                print(f"[ebay] {type(e).__name__}")
        graded.append((d, res))
    order = {"A": 0, "B": 1, "R": 2}
    graded.sort(key=lambda x: (order[x[1].grade[0]], -x[1].ev_net))
    affordable = [(d, r) for d, r in graded if r.cost <= cap]
    stats = {"scanned": len(raws), "priced": len(graded), "unpriced": len(unpriced), "affordable": len(affordable),
             "A": sum(r.grade[0] == "A" for _, r in affordable), "B": sum(r.grade[0] == "B" for _, r in affordable),
             "R": sum(r.grade == "REJECT" for _, r in graded)}
    return br, tier, graded, affordable, unpriced, stats

def _public_deal(d, r):
    """Community-safe fields only: no bankroll, stake, tier or ledger data."""
    import re as _re
    e_rev = r.cost + r.ev_net
    return {"title": d.title[:200], "url": d.url, "merchant": d.merchant, "category": d.category, "grade": r.grade[0] if r.grade[0] in "AB" else "R",
            "buy": round(r.cost, 2), "target": round(r.plan["target"], 2), "net": round(r.ev_net, 2), "roi": round(r.ev_roi, 1),
            "worst": round(r.worst, 2), "confidence": int(r.confidence),
            "max_buy": round(max(0.0, min(e_rev - E.COMMUNITY_MIN_NET, e_rev / (1 + E.COMMUNITY_MIN_ROI / 100))), 2),
            "why": E.gates_failed(r)[:2], "thumb": getattr(d, "thumb", ""), "comp": (d.comp_note or "")[:200],
            "ebay_sold": E.ebay_sold_url(E.short_query(d.title)), "vinted": E.vinted_url(E.short_query(d.title)),
            "delivery": d.delivery, "days_to_sell": d.days_to_sell, "under_cap": r.cost <= E.COMMUNITY_MAX_PRICE,
            "plan": {k: r.plan[k] for k in ("list", "target", "quick", "floor", "time_stop_day", "platforms")}}

def export_public(path, stats, graded):
    import datetime as dt
    out = {"generated_utc": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "price_cap": E.COMMUNITY_MAX_PRICE,
           "stats": stats, "deals": [_public_deal(d, r) for d, r in graded[:40]]}
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    json.dump(out, open(path, "w"), indent=1); print(f"[export] {path}: {len(out['deals'])} deals")

def cmd_scan(a):
    br, tier, graded, affordable, unpriced, stats = run_scan()
    who = "Rules: community starter set" if os.getenv("MONEYHUNTER_COMMUNITY") == "1" else f"Bankroll £{br:.2f} → {tier.name}"
    print(f"{who}. eBay API: {'on' if ebay.available() else 'skipped (no keys)'}. CeX: {'reachable' if cex.available() else 'blocked (403)'}.")
    print(f"Scanned {stats['scanned']} · priced {stats['priced']} · under cap {stats['affordable']} · A {stats['A']} · B {stats['B']} · rejected {stats['R']} · unpriced {stats['unpriced']}")
    for d, r in graded:
        print(f"  [{r.grade:10}] {d.title[:60]:60} £{r.cost:7.2f} → £{r.plan['target']:.2f} · EV £{r.ev_net:6.2f} · {', '.join(E.gates_failed(r)[:2])}")
    if a.show_all:
        for d in unpriced[:40]: print(f"  [unpriced {d.category:10}] £{d.buy_price:7.2f} {d.title[:70]}")
    seen = _load_seen()
    cards = [(d, r) for d, r in affordable if r.grade[0] in "AB" and _key(d) not in seen]
    if a.include_rejects and not cards:
        cards = [(d, r) for d, r in affordable if _key(d) not in seen][: a.include_rejects]
    cards = cards[: a.max_posts]
    near = [(d, r) for d, r in affordable if r.grade == "REJECT"][:6]
    posted = []
    summary_due = bool(cards) or a.summary
    if summary_due:
        st = D.post([E.scan_summary(stats, near, a.preview)], dry_run=a.dry_run); print(f"[discord] summary: {st or 'dry-run'}")
    for d, r in cards:
        st = D.post(E.deal_card(d, r, a.preview), dry_run=a.dry_run, components=E.link_buttons(d)); print(f"[discord] card: {st or 'dry-run'}")
        if st and 200 <= st < 300: posted.append(_key(d))
    if posted:
        json.dump(sorted(seen | set(posted)), open(STATE, "w"))
    if a.export:
        export_public(a.export, stats, graded)
    if not summary_due: print("No new A/B deals under your tier cap; nothing posted.")

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
    s = sp.add_parser("scan"); s.add_argument("--dry-run", action="store_true"); s.add_argument("--max-posts", type=int, default=5); s.add_argument("--show-all", action="store_true"); s.add_argument("--include-rejects", type=int, default=0); s.add_argument("--summary", action="store_true", help="post the scan report even with no cards"); s.add_argument("--preview", action="store_true"); s.add_argument("--export", help="write community deals JSON, e.g. public/deals.json"); s.set_defaults(f=cmd_scan)
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

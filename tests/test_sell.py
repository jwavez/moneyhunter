import datetime as dt, os
from moneyhunter import sell as S, embeds as E, hub as H

def test_routes_map():
    assert S.route("trainers", 50)["preferred"].startswith("Vinted")
    assert S.route("trainers", 120)["preferred"].startswith("eBay")
    assert "Depop" in S.route("trainers", 50)["backup"]
    assert S.route("lego")["preferred"].startswith("eBay") and "BrickLink" not in S.platforms_text("lego")
    assert "CeX" in S.route("gaming")["floor"] and "musicMagpie" in S.route("gaming")["floor"]
    assert "Marketplace" in S.route("tools")["backup"]
    assert "exact size" in S.route("fragrance")["preferred"]
    assert "CeX" in S.route("tech")["floor"]
    assert len(S.sell_on_value("trainers", 50)) <= 1024

def test_fast_routing():
    assert S.fast_route("A", "lego", 7) and S.fast_route("B", "tools", 10)
    assert not S.fast_route("A", "lego", 21) and not S.fast_route("R", "lego", 3)
    assert not S.fast_route("B", "trainers", None) and not S.fast_route("A", "gaming", None)
    assert not S.fast_route("A", "lego", None)
    assert S.dts_label("lego", 5).startswith("⚡ FAST")

def test_quiet_key_hourly():
    a = dt.datetime(2026, 11, 6, 12, 7, tzinfo=dt.timezone.utc); b = a.replace(minute=37)
    assert E.quiet_key(a) == E.quiet_key(b) == "quiet:2026-11-06-12"
    assert E.quiet_key(a.replace(hour=13)) != E.quiet_key(a)
    c = E.quiet_card({"scanned": 40, "priced": 3}, "🧱 LEGO 2")
    assert len(c["description"]) <= 4096 and "WATCH" in c["description"]
    for w in ("UC", "tax", "bankroll", "Traders Edge"): assert w not in c["description"]

def test_watch_card_fields():
    for cat in ("gaming", "lego"):
        it = {"title": "Some item name", "url": "https://x", "price": 20.0, "category": cat, "merchant": "Argos"}
        names = [f["name"] for f in H.watch_card(it, {})["fields"]]
        assert "Sell on" in names and "Max hold" in names and "Days to sell" in names
        assert ("Quick-cash floor" in names) == (cat == "gaming")
        assert all(len(f["value"]) <= 1024 for f in H.watch_card(it, {})["fields"])

def test_trending_filter():
    ok = lambda t, c="gaming": H.resellable({"title": t, "category": c})
    assert ok("Nintendo Switch Pro Controller")
    for t in ("Mario Kart pre-order", "Steam key bundle", "Dune 4K UHD Blu-ray", "Harry Potter DVD box set", "Xiaomi electric scooter"):
        assert not ok(t), t
    assert not ok("Lego set", None) and not ok("thing", "scooters")

def test_buttons_by_category():
    labels = lambda c: [b["label"] for b in H.buttons({"title": "x y", "url": "https://x", "category": c})[0]["components"]]
    assert "Vinted" in labels("trainers") and "Vinted" not in labels("lego")
    assert "CeX price" in labels("gaming") and "CeX price" in labels("tech")

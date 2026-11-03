from moneyhunter import embeds as E, config as C

def test_tier_caps(monkeypatch):
    for t, cap in enumerate([60, 120, 300, 600, 1200]):
        monkeypatch.setenv("MH_TIER", str(t))
        assert E.active_tier() == t and E.community_cap() == cap
        br = E.TIER_BANKROLL[t]; tier = C.tier_for(br)
        assert br * tier.max_pct / 100 >= cap          # grading never blocks below the tier cap
    for bad in ("7", "-1", "x", ""):
        monkeypatch.setenv("MH_TIER", bad); assert E.active_tier() == 0 and E.community_cap() == 60

def test_community_bankroll_uses_tier(monkeypatch):
    from moneyhunter import cli
    monkeypatch.setenv("MONEYHUNTER_COMMUNITY", "1"); monkeypatch.setenv("MH_TIER", "2")
    assert cli.bankroll() == 1500.0
    monkeypatch.delenv("MH_TIER"); assert cli.bankroll() == 200.0

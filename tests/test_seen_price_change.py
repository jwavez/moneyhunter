"""Task 17 — re-post priced WATCH cards when buy price moves ≥10% vs last delivery."""
import json
import tempfile
import unittest
from pathlib import Path
from moneyhunter.seen_state import SeenState, decide_watch, PRICE_CHANGE_THRESHOLD
from moneyhunter import hub
from unittest.mock import patch
import contextlib, io


class DecideWatch(unittest.TestCase):
    def test_50_to_50_suppressed(self):
        d = decide_watch(key_in_seen=True, last_delivered_price=50.0, current_price=50.0, priced=True)
        self.assertFalse(d["would_deliver"])
        self.assertEqual(d["reason"], "price_change_under_10pct")
        self.assertFalse(d["is_repost"])

    def test_50_to_47_suppressed(self):
        d = decide_watch(key_in_seen=True, last_delivered_price=50.0, current_price=47.0, priced=True)
        self.assertFalse(d["would_deliver"])
        self.assertAlmostEqual(d["pct_change"], 0.06)
        self.assertEqual(d["reason"], "price_change_under_10pct")

    def test_50_to_44_posts(self):
        d = decide_watch(key_in_seen=True, last_delivered_price=50.0, current_price=44.0, priced=True)
        self.assertTrue(d["would_deliver"])
        self.assertTrue(d["is_repost"])
        self.assertAlmostEqual(d["pct_change"], 0.12)
        self.assertEqual(d["reason"], "price_change_ge_10pct")

    def test_50_to_56_posts(self):
        d = decide_watch(key_in_seen=True, last_delivered_price=50.0, current_price=56.0, priced=True)
        self.assertTrue(d["would_deliver"])
        self.assertTrue(d["is_repost"])
        self.assertAlmostEqual(d["pct_change"], 0.12)

    def test_50_to_46_suppressed(self):
        d = decide_watch(key_in_seen=True, last_delivered_price=50.0, current_price=46.0, priced=True)
        self.assertFalse(d["would_deliver"])
        self.assertAlmostEqual(d["pct_change"], 0.08)
        self.assertEqual(d["reason"], "price_change_under_10pct")

    def test_first_ever_delivery_posts_and_records(self):
        d = decide_watch(key_in_seen=False, last_delivered_price=None, current_price=39.43, priced=True)
        self.assertTrue(d["would_deliver"])
        self.assertTrue(d["record_price"])
        self.assertFalse(d["is_repost"])
        self.assertEqual(d["reason"], "first_delivery")

    def test_unpriced_always_suppressed_even_with_baseline(self):
        d = decide_watch(key_in_seen=True, last_delivered_price=50.0, current_price=20.0, priced=False)
        self.assertFalse(d["would_deliver"])
        self.assertEqual(d["reason"], "unpriced_always_suppressed")
        self.assertFalse(d["record_price"])

    def test_no_baseline_suppress_and_record(self):
        d = decide_watch(key_in_seen=True, last_delivered_price=None, current_price=44.99, priced=True)
        self.assertFalse(d["would_deliver"])
        self.assertTrue(d["record_price"])
        self.assertEqual(d["reason"], "no_baseline_suppress_and_record")

    def test_threshold_constant(self):
        self.assertEqual(PRICE_CHANGE_THRESHOLD, 0.10)


class SeenStateRoundTrip(unittest.TestCase):
    def test_legacy_list_loads_without_prices(self):
        s = SeenState.from_json(["w:ask-model-v1:https://example/1"])
        self.assertIn("w:ask-model-v1:https://example/1", s)
        self.assertIsNone(s.last_delivered_price("w:ask-model-v1:https://example/1"))
        self.assertEqual(s.to_json(), ["w:ask-model-v1:https://example/1"])

    def test_v2_roundtrip_preserves_price(self):
        s = SeenState(["k1"], {"k1": 50.0})
        s.record_price("k1", 44.0)
        data = s.to_json()
        self.assertEqual(data["schema_version"], 2)
        self.assertEqual(data["last_delivered_price"]["k1"], 44.0)
        s2 = SeenState.from_json(data)
        self.assertEqual(s2.last_delivered_price("k1"), 44.0)

    def test_dry_run_must_not_write(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "seen.json"
            path.write_text(json.dumps(["k1"]))
            before = path.read_bytes()
            s = SeenState.load(path)
            d = s.decide("k1", 40.0, priced=True)
            self.assertEqual(d["reason"], "no_baseline_suppress_and_record")
            # dry path: do not record
            self.assertEqual(path.read_bytes(), before)


class Offline75347Simulation(unittest.TestCase):
    """Labelled offline simulation — not a live Actions demonstration."""

    def test_75347_simulated_price_drop_allows_repost(self):
        # Real-ish identity from state; prices are simulated for the rule only.
        key = "w:ask-model-v1:https://www.hotukdeals.com/deals/lego-star-wars-tie-bomber-75347-5025299"
        # Simulate: last delivered £50, current HUKD £44.99 → ~10.02% drop
        d = decide_watch(key_in_seen=True, last_delivered_price=50.0, current_price=44.99, priced=True)
        self.assertTrue(d["would_deliver"], d)
        self.assertTrue(d["is_repost"])
        self.assertGreaterEqual(d["pct_change"], 0.10)
        # Under-threshold control: £47 vs £50
        d2 = decide_watch(key_in_seen=True, last_delivered_price=50.0, current_price=47.0, priced=True)
        self.assertFalse(d2["would_deliver"])

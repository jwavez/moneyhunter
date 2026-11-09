"""Tools getItem slot diagnostic — allocation decisions must stay identical."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moneyhunter import details, market, tools_slot_diagnostic
from moneyhunter.scanners import ebay

NOW = dt.datetime(2026, 11, 9, 12, 0, tzinfo=dt.timezone.utc)


def tool_ident(title="DeWalt DCF887N 18V Bare Tool"):
    return market.identity({"title": title, "category": "tools"})


def snapshot_for(ident, item_id="v1|100|0", price=50.0):
    offer = {
        "item_id": item_id,
        "item_price": price,
        "shipping": 0.0,
        "listed_total": price,
        "url": f"https://www.ebay.co.uk/itm/{item_id.split('|')[1]}",
        "title": ident.match,
        "seller": "toolshop",
        "country": "GB",
        "currency": "GBP",
        "declared_condition": "new",
    }
    return {
        "kind": "active_ask",
        "query": ident.match,
        "offers": [offer],
        "sample_count": 1,
        "status": "indicative_only",
        "observed_at": NOW.isoformat(),
    }


def getitem_payload(title, model):
    return {
        "title": title,
        "conditionId": "1000",
        "price": {"value": "50", "currency": "GBP"},
        "shippingOptions": [
            {"shippingCostType": "FIXED", "shippingCost": {"value": "0", "currency": "GBP"}}
        ],
        "estimatedAvailabilities": [{"estimatedAvailabilityStatus": "IN_STOCK"}],
        "localizedAspects": [
            {"name": "Model", "value": model},
            {"name": "Voltage", "value": "18.0v"},
            {"name": "Battery Included", "value": "No"},
        ],
        "mpn": model,
    }


class SlotAllocationUnchanged(unittest.TestCase):
    def setUp(self):
        details.reset_slot_log()

    def test_instrumentation_preserves_grant_cache_and_slot_exhaustion(self):
        i = tool_ident()
        s = snapshot_for(i)
        data = getitem_payload(i.match, "DCF887N")
        state = {
            "ask_cache": {},
            "detail_run": {"calls": 0, "cached": 0, "errors": [], "reserved_tools": 2},
            "browse_usage": {"date": NOW.date().isoformat(), "calls": 0, "by_purpose": {}},
        }
        with patch.object(ebay, "available", return_value=True), patch.object(
            ebay, "item_details", return_value=data
        ) as api:
            details.inspect_snapshot(s, i, state, NOW)
            details.flush_slot_allocation(state, NOW)
            r1 = details.inspect_snapshot(s, i, state, NOW)
            self.assertEqual(api.call_count, 1)
            self.assertEqual(state["detail_run"]["calls"], 1)
            self.assertNotEqual(r1.get("detail_status"), "awaiting_detail_budget")
            cached_after_first_hit = state["detail_run"]["cached"]
            self.assertGreaterEqual(cached_after_first_hit, 1)
            # Cache hit — no second getItem
            r2 = details.inspect_snapshot(s, i, state, NOW + dt.timedelta(minutes=1))
            self.assertEqual(api.call_count, 1)
            self.assertEqual(state["detail_run"]["cached"], cached_after_first_hit + 1)
            # Exhaust remaining slots (LIMIT=4); tools may use all 4
            state["detail_run"]["calls"] = 4
            state["detail_demands_closed"] = False
            details.inspect_snapshot(
                snapshot_for(i, item_id="v1|999|0", price=40.0),
                i,
                state,
                NOW + dt.timedelta(minutes=2),
            )
            details.flush_slot_allocation(state, NOW + dt.timedelta(minutes=2))
            r3 = details.inspect_snapshot(
                snapshot_for(i, item_id="v1|999|0", price=40.0),
                i,
                state,
                NOW + dt.timedelta(minutes=2),
            )
            self.assertEqual(api.call_count, 1)
            self.assertEqual(r3["detail_status"], "awaiting_detail_budget")
        events = details.SLOT_EVENTS
        grants = [e for e in events if e.get("getitem_granted")]
        caches = [e for e in events if e.get("denial_reason") == "cache_hit"]
        exhausted = [e for e in events if e.get("denial_reason") == "slots_exhausted"]
        self.assertTrue(grants)
        self.assertEqual(grants[0]["slot_index"], 0)
        self.assertTrue(caches)
        self.assertTrue(exhausted)

    def test_fragrance_uses_leftover_slots_only_after_primary(self):
        # Fragrance is Phase-3 leftover; with remaining capacity and no primary demand it can grant.
        from tests.test_value_watchlist import ExactDetails

        i, s, o, d = ExactDetails().fixture()
        state = {
            "ask_cache": {},
            "detail_run": {"calls": 0, "cached": 0, "errors": [], "reserved_tools": 2},
            "browse_usage": {"date": NOW.date().isoformat(), "calls": 10, "by_purpose": {}},
            "detail_demands_closed": False,
        }
        details.reset_slot_log()
        with patch.object(ebay, "available", return_value=True), patch.object(
            ebay, "item_details", return_value=d
        ) as api:
            details.inspect_snapshot(s, i, state, NOW)
            details.flush_slot_allocation(state, NOW)
            self.assertEqual(api.call_count, 1)
            self.assertEqual(state["detail_run"]["calls"], 1)
        self.assertTrue(details.SLOT_EVENTS[-1]["getitem_granted"])


class ToolsSlotDiagnostic(unittest.TestCase):
    def setUp(self):
        details.reset_slot_log()

    def test_logs_all_tools_offers_and_slot_summary(self):
        i1 = tool_ident("DeWalt DCF887N 18V Bare Tool")
        i2 = tool_ident("Makita DGA452Z 18V Angle Grinder Body Only")
        offers = [
            {
                "title": "DeWalt DCF887N 18V XR Brushless Impact Driver (Body Only)",
                "url": "https://hukd.example/dcf887n",
                "category": "tools",
            },
            {
                "title": "Makita DGA452Z 18V LXT 115mm Grinder - Body",
                "url": "https://hukd.example/dga452z-a",
                "category": "tools",
            },
            {
                "title": "Makita DGA452Z 18V LXT 115mm Angle Grinder (Body Only)",
                "url": "https://hukd.example/dga452z-b",
                "category": "tools",
            },
            {
                "title": "Random non-tool",
                "url": "https://hukd.example/lego",
                "category": "lego",
            },
        ]
        # Simulate enrich grouping + one granted slot for DCF887N, denial for DGA452Z.
        details.record_enrich_group(
            "asking-tools", i1, ["https://hukd.example/dcf887n"]
        )
        details.record_enrich_group(
            "asking-tools",
            i2,
            ["https://hukd.example/dga452z-a", "https://hukd.example/dga452z-b"],
        )
        details.SLOT_EVENTS.extend(
            [
                {
                    "phase": "inspect",
                    "category": "tech",
                    "identity": "Google Pixel Buds 2a hazel",
                    "getitem_requested": True,
                    "getitem_granted": True,
                    "slot_index": 0,
                    "denial_reason": None,
                    "note": None,
                    "comparator_item_id": "v1|50|0",
                    "comparator_url": "https://www.ebay.co.uk/itm/50",
                },
                {
                    "phase": "inspect",
                    "category": "tools",
                    "identity": i1.match,
                    "getitem_requested": True,
                    "getitem_granted": True,
                    "slot_index": 1,
                    "denial_reason": None,
                    "note": None,
                    "comparator_item_id": "v1|100|0",
                    "comparator_url": "https://www.ebay.co.uk/itm/100",
                },
                {
                    "phase": "inspect",
                    "category": "tools",
                    "identity": i2.match,
                    "getitem_requested": True,
                    "getitem_granted": False,
                    "slot_index": None,
                    "denial_reason": "slots_exhausted",
                    "note": None,
                    "comparator_item_id": "v1|200|0",
                    "comparator_url": "https://www.ebay.co.uk/itm/200",
                },
            ]
        )
        research = [
            {"url": o["url"], "category": "tools", "ask_context": {"query": "x"}}
            for o in offers
            if o["category"] == "tools"
        ]
        state = {
            "detail_run": {"calls": 2, "cached": 0, "errors": [], "reserved_tools": 2},
            "browse_usage": {"date": NOW.date().isoformat(), "calls": 42, "by_purpose": {}},
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tools_slot_diagnostic.json"
            payload = tools_slot_diagnostic.log_tool_slot_allocation(
                offers=offers, research_rows=research, out_path=str(out), state=state
            )
            self.assertTrue(out.exists())
        self.assertIsNone(payload["error"])
        self.assertEqual(len(payload["entries"]), 3)
        by_url = {e["offer_url"]: e for e in payload["entries"]}
        self.assertTrue(by_url["https://hukd.example/dcf887n"]["getitem_granted"])
        self.assertEqual(by_url["https://hukd.example/dcf887n"]["slot_index"], 1)
        dga = by_url["https://hukd.example/dga452z-a"]
        self.assertFalse(dga["getitem_granted"])
        self.assertEqual(dga["denial_reason"], "slots_exhausted")
        self.assertTrue(dga["deduplicated"])
        self.assertEqual(dga["same_identity_other_offers"], 1)
        summary = payload["slot_summary"]
        self.assertEqual(summary["tool_slots_reserved"], 2)
        self.assertEqual(summary["tool_slots_used"], 1)  # only tools grants
        self.assertEqual(summary["shared_daily_getitem_budget"], 800)
        self.assertNotIn("total_getitem_budget", summary)
        self.assertEqual(summary["total_getitem_used"], 42)
        self.assertTrue(any("tool_slots_reserved is a minimum" in n for n in summary["notes"]))
        self.assertEqual(len(payload["getitem_calls"]), 2)
        self.assertEqual([c["category"] for c in payload["getitem_calls"]], ["tech", "tools"])
        # Per-category distinct identities.
        by_cat = {r["category"]: r for r in payload["per_category_slot_summary"]}
        self.assertIn("tools", by_cat)
        tools = by_cat["tools"]
        self.assertEqual(
            tools["wanted"],
            tools["granted"]
            + tools["denied_slots_exhausted"]
            + tools["denied_cache_hit"]
            + tools["denied_other"],
        )
        self.assertIn("considered", tools)
        self.assertIn("denied_not_risky_lowest", tools)
        self.assertEqual(payload["slot_summary"]["total_wanted"], sum(r["wanted"] for r in payload["per_category_slot_summary"]))
        self.assertEqual(payload["slot_summary"]["total_granted"], sum(r["granted"] for r in payload["per_category_slot_summary"]))
        dga_status = payload["dga452z_publication_status"]
        self.assertIn("research_model_value", dga_status)
        self.assertIn("publication_estimate_value", dga_status)
        self.assertNotIn("supported_estimate_value", dga_status)
        dga = payload["dga452z_publication_status"]
        self.assertTrue(dga["in_this_scan"])
        self.assertIn("DGA452Z", dga["identity"])


if __name__ == "__main__":
    unittest.main()

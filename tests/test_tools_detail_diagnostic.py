"""Tools detail-failure diagnostic only — decisions and gates unchanged."""
import copy
import datetime as dt
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moneyhunter import details, market, publication, tools_detail_diagnostic

NOW = dt.datetime(2026, 11, 9, 10, 0, tzinfo=dt.timezone.utc)


def tool_ident():
    return market.identity({"title": "DeWalt DCF887N 18V Bare Tool", "category": "tools"})


def tool_offer(price=50.0, shipping=0.0):
    return {
        "item_id": "v1|100|0",
        "item_price": price,
        "shipping": shipping,
        "listed_total": price + shipping,
        "url": "https://www.ebay.co.uk/itm/100",
        "title": "DeWalt DCF887N 18V Bare Tool",
        "seller": "toolshop",
        "country": "GB",
        "currency": "GBP",
        "declared_condition": "new",
    }


def tool_getitem(**overrides):
    data = {
        "title": "DeWalt DCF887N 18V Bare Tool",
        "conditionId": "1000",
        "price": {"value": "50", "currency": "GBP"},
        "shippingOptions": [
            {"shippingCostType": "FIXED", "shippingCost": {"value": "0", "currency": "GBP"}}
        ],
        "estimatedAvailabilities": [{"estimatedAvailabilityStatus": "IN_STOCK"}],
        "localizedAspects": [
            {"name": "Model", "value": "DCF887N"},
            {"name": "Battery Included", "value": "No"},
        ],
        "mpn": "DCF887N",
    }
    data.update(overrides)
    return data


class AssessDecisionIdentity(unittest.TestCase):
    """Additive sub_checks must not change status or reasons."""

    CASES = {
        "ok": (tool_getitem(), ("verified_fields", [])),
        "battery_yes": (
            tool_getitem(
                localizedAspects=[
                    {"name": "Model", "value": "DCF887N"},
                    {"name": "Battery Included", "value": "Yes"},
                ]
            ),
            ("conflict", ["battery/charger inclusion contradicts bare tool"]),
        ),
        "model_missing": (
            tool_getitem(localizedAspects=[{"name": "Battery Included", "value": "No"}], mpn=None),
            ("incomplete", ["exact tool model aspect missing"]),
        ),
        "model_wrong": (
            tool_getitem(
                localizedAspects=[
                    {"name": "Model", "value": "DCF887"},
                    {"name": "Battery Included", "value": "No"},
                ]
            ),
            ("conflict", ["tool model mismatch"]),
        ),
        "condition": (tool_getitem(conditionId="3000"), ("conflict", ["condition not NEW"])),
        "price": (
            tool_getitem(price={"value": "1", "currency": "GBP"}),
            ("conflict", ["price changed or currency unknown"]),
        ),
        "no_ship": (
            tool_getitem(shippingOptions=[]),
            ("incomplete", ["fixed detail shipping not supplied"]),
        ),
        "ship_mismatch": (
            tool_getitem(
                shippingOptions=[
                    {
                        "shippingCostType": "FIXED",
                        "shippingCost": {"value": "5", "currency": "GBP"},
                    }
                ]
            ),
            ("conflict", ["delivered price changed"]),
        ),
        "oos": (
            tool_getitem(estimatedAvailabilities=[{"estimatedAvailableQuantity": 0}]),
            ("conflict", ["out of stock", "current availability not supplied"]),
        ),
        "title": (
            tool_getitem(title="DeWalt DCF809N 18V Bare Tool"),
            ("conflict", ["detail title contradicts exact identity"]),
        ),
    }

    def test_status_and_reasons_identical_to_pre_subcheck_baseline(self):
        i = tool_ident()
        o = tool_offer()
        for name, (data, expected) in self.CASES.items():
            with self.subTest(name=name):
                result = details.assess(data, o, i, NOW)
                self.assertEqual((result["status"], result["reasons"]), expected)
                # Side channel present without affecting decision fields.
                self.assertIn("sub_checks", result)
                if expected[0] == "verified_fields":
                    self.assertEqual(result["sub_checks"], [])
                else:
                    self.assertTrue(result["sub_checks"])
                    self.assertEqual(
                        [s["reason"] for s in result["sub_checks"]], expected[1]
                    )


class ToolsDetailDiagnostic(unittest.TestCase):
    def _row(self, detail_status="conflict", detail=None):
        offer = {
            "title": "DeWalt DCF887N 18V XR Brushless Impact Driver (Body Only)",
            "category": "tools",
            "url": "https://www.hotukdeals.com/deals/fixture-dcf887n",
            "price": 49.99,
            "merchant": "Screwfix",
            "online_eligible": True,
        }
        low = tool_offer()
        detail = detail or details.assess(
            tool_getitem(
                localizedAspects=[
                    {"name": "Model", "value": "DCF887N"},
                    {"name": "Battery Included", "value": "Yes"},
                ]
            ),
            low,
            tool_ident(),
            NOW,
        )
        # Build a publication-eligible ask_estimate shape except detail_status.
        sources = []
        for n in range(3):
            sources.append(
                {
                    "url": f"https://www.ebay.co.uk/itm/{100 + n}",
                    "title": "DeWalt DCF887N 18V Bare Tool",
                    "listed_total": 60.0 + n,
                    "shipping": 0.0,
                    "item_price": 60.0 + n,
                    "seller": f"seller{n}",
                    "country": "GB",
                    "currency": "GBP",
                    "declared_condition": "new",
                    "item_id": f"v1|{100 + n}|0",
                }
            )
        sources[0] = {**sources[0], **low, "url": low["url"]}
        ask_estimate = {
            "model": "competitor-asks-v1",
            "observed_at": NOW.isoformat(),
            "suggested_listing": 60.0,
            "estimated_resale": 60.0,
            "detail_status": detail_status,
            "query": "DeWalt DCF887N bare tool 18V",
            "sources": sources,
            "competitor_coupon_unknown": False,
        }
        ask_context = {
            "query": ask_estimate["query"],
            "offers": sources,
            "detail_required": True,
            "detail_status": detail_status,
            "lowest_detail": detail,
            "observed_at": NOW.isoformat(),
            "sample_count": 3,
            "status": "indicative_only",
        }
        offer["ask_estimate"] = ask_estimate
        offer["ask_context"] = ask_context
        research = {
            "url": offer["url"],
            "category": "tools",
            "ask_estimate": ask_estimate,
            "ask_context": ask_context,
            "title": offer["title"],
        }
        return offer, research

    def test_records_sub_checks_for_detail_check_failed_only(self):
        offer, research = self._row()
        # Sanity: publication classifies this as the detail hold.
        self.assertEqual(
            publication.proof(offer)["reason"], "detail_check_failed"
        )
        other = {
            "title": "Makita B-53811 bits",
            "category": "tools",
            "url": "https://example.com/bits",
            "ask_estimate": None,
        }
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tools_detail_diagnostic.json"
            with patch.object(details, "assess") as assess:
                payload = tools_detail_diagnostic.log_tool_detail_failures(
                    offers=[offer, other],
                    research_rows=[research],
                    out_path=str(out),
                )
                assess.assert_not_called()  # no re-check / no extra getItem path
            self.assertIsNone(payload["error"])
            self.assertEqual(len(payload["entries"]), 1)
            entry = payload["entries"][0]
            self.assertEqual(entry["offer_url"], offer["url"])
            self.assertEqual(entry["identity"], "DeWalt DCF887N bare tool 18V")
            self.assertEqual(entry["comparator_url"], "https://www.ebay.co.uk/itm/100")
            self.assertEqual(entry["comparator_title"], "DeWalt DCF887N 18V Bare Tool")
            self.assertEqual(entry["comparator_condition"], "1000")
            self.assertEqual(entry["comparator_price"], 50.0)
            self.assertEqual(entry["comparator_shipping"], 0.0)
            self.assertTrue(entry["sub_checks"])
            self.assertEqual(entry["sub_checks"][0]["sub_check_failed"], "variation_mismatch")
            self.assertEqual(entry["sub_check_failed"], "variation_mismatch")
            self.assertIn("title", entry["getitem_fields_present"])
            # Task 8 Part A: failed entries expose read-only comparator_candidates.
            cands = entry["comparator_candidates"]
            self.assertGreaterEqual(len(cands), 1)
            self.assertLessEqual(len(cands), 3)
            self.assertEqual(cands[0]["rank_by_price"], 1)
            self.assertTrue(cands[0]["getitem_ran"])
            self.assertIs(cands[0]["detail_would_pass"], False)
            self.assertIsNotNone(cands[0]["detail_fail_reason"])
            if len(cands) > 1:
                self.assertFalse(cands[1]["getitem_ran"])
                self.assertIsNone(cands[1]["detail_would_pass"])
            self.assertIn("pr34_categorization_check", payload)
            self.assertIn("near_publish_diagnostic", payload)
            self.assertIn("dga452z", payload["near_publish_diagnostic"])

    def test_maps_legacy_cached_reasons_without_refetch(self):
        legacy = {
            "item_id": "v1|100|0",
            "status": "incomplete",
            "reasons": ["exact tool model aspect missing", "fixed detail shipping not supplied"],
            "checked_item_price": 50.0,
            "condition_id": "1000",
            "source_url": "https://www.ebay.co.uk/itm/100",
            # title/shipping/inventory intentionally absent — must be recorded as missing
        }
        offer, research = self._row(detail_status="incomplete", detail=legacy)
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tools_detail_diagnostic.json"
            payload = tools_detail_diagnostic.log_tool_detail_failures(
                offers=[offer], research_rows=[research], out_path=str(out)
            )
        names = [f["sub_check_failed"] for f in payload["entries"][0]["sub_checks"]]
        self.assertEqual(names, ["title_model_number_missing", "shipping_unknown"])
        note = payload["entries"][0]["note"] or ""
        self.assertIn("comparator_availability not retained", note)
        self.assertIn("getitem field inventory not retained", note)
        # Title may still come from the retained ask offer; shipping may come from that offer too.
        self.assertIsNotNone(payload["entries"][0]["comparator_title"])



class Task8DiagnosticExtensions(unittest.TestCase):
    def test_comparator_candidates_sorted_and_read_only(self):
        diag = ToolsDetailDiagnostic()
        offer, research = diag._row()
        # Add a cheaper wrong-model candidate already "checked" vs a higher un-checked one.
        ctx = research["ask_context"]
        offers = [
            {
                "item_id": "v1|100|0",
                "item_price": 50.0,
                "shipping": 0.0,
                "listed_total": 50.0,
                "url": "https://www.ebay.co.uk/itm/100",
                "title": "DeWalt DCF887N 18V Bare Tool",
                "seller": "a",
                "country": "GB",
                "currency": "GBP",
                "declared_condition": "new",
            },
            {
                "item_id": "v1|200|0",
                "item_price": 55.0,
                "shipping": 0.0,
                "listed_total": 55.0,
                "url": "https://www.ebay.co.uk/itm/200",
                "title": "DeWalt DCF887N 18V XR",
                "seller": "b",
                "country": "GB",
                "currency": "GBP",
                "declared_condition": "new",
            },
            {
                "item_id": "v1|300|0",
                "item_price": 70.0,
                "shipping": 0.0,
                "listed_total": 70.0,
                "url": "https://www.ebay.co.uk/itm/300",
                "title": "DeWalt DCF887N kit",
                "seller": "c",
                "country": "GB",
                "currency": "GBP",
                "declared_condition": "new",
            },
        ]
        ctx["offers"] = offers
        research["ask_context"] = ctx
        offer["ask_context"] = ctx
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(details, "assess") as assess:
                payload = tools_detail_diagnostic.log_tool_detail_failures(
                    offers=[offer], research_rows=[research], out_path=str(Path(tmp) / "x.json")
                )
                assess.assert_not_called()
        cands = payload["entries"][0]["comparator_candidates"]
        self.assertEqual([c["rank_by_price"] for c in cands], [1, 2, 3])
        self.assertEqual([c["price"] for c in cands], [50.0, 55.0, 70.0])
        self.assertTrue(cands[0]["getitem_ran"])
        self.assertFalse(cands[1]["getitem_ran"])
        self.assertIsNone(cands[1]["observed_model_number"])

    def test_pr34_check_and_near_publish_explanation(self):
        details.reset_slot_log()
        # Simulate post-PR34 tools slot log: 5 wanted + 2 inspect_skip for DTD/DUB.
        for i, ident in enumerate(
            [
                "DeWalt DCF887N bare tool 18V",
                "Makita DGA452Z bare tool 18V",
                "DeWalt DCS565N bare tool 18V",
                "Makita DHP484Z bare tool 18V",
                "Makita DTD154Z bare tool 18V",
            ]
        ):
            details.SLOT_EVENTS.append(
                {
                    "phase": "inspect",
                    "category": "tools",
                    "identity": ident,
                    "getitem_requested": True,
                    "getitem_granted": i < 2,
                    "denial_reason": None if i < 2 else "slots_exhausted",
                    "near_publish": ident.endswith("DGA452Z bare tool 18V") and False,
                }
            )
        # Force near_publish false on DGA event
        for e in details.SLOT_EVENTS:
            if "DGA452Z" in (e.get("identity") or ""):
                e["near_publish"] = False
        for ident in ("Makita DTD152Z bare tool 18V", "Makita DUB185Z bare tool 18V"):
            details.SLOT_EVENTS.append(
                {
                    "phase": "inspect_skip",
                    "category": "tools",
                    "identity": ident,
                    "getitem_requested": False,
                    "getitem_granted": False,
                    "denial_reason": "not_risky_lowest",
                    "note": "not risky or no comparator offers",
                }
            )
        dga_offer = {
            "title": "Makita DGA452Z 18V Angle Grinder Body Only",
            "url": "https://hukd.example/dga",
            "category": "tools",
            "ask_context": {
                "query": "Makita DGA452Z bare tool 18V",
                "sample_count": 2,
                "offers": [
                    {
                        "item_id": "v1|1|0",
                        "listed_total": 80.0,
                        "item_price": 80.0,
                        "shipping": 0.0,
                        "seller": "s1",
                        "title": "Makita DGA452Z",
                        "url": "https://www.ebay.co.uk/itm/1",
                        "declared_condition": "new",
                        "country": "GB",
                        "currency": "GBP",
                    },
                    {
                        "item_id": "v1|2|0",
                        "listed_total": 85.0,
                        "item_price": 85.0,
                        "shipping": 0.0,
                        "seller": "s2",
                        "title": "Makita DGA452Z body",
                        "url": "https://www.ebay.co.uk/itm/2",
                        "declared_condition": "new",
                        "country": "GB",
                        "currency": "GBP",
                    },
                ],
                "detail_status": "awaiting_detail_budget",
            },
            "ask_estimate": {
                "model": "competitor-asks-v1",
                "sample_count": 2,
                "seller_count": 2,
                "low_price_supporting_sellers": 2,
                "estimated_resale": 77.59,
                "detail_status": "awaiting_detail_budget",
                "checks": ["Lowest comparator details unverified/conflicting: awaiting_detail_budget"],
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = tools_detail_diagnostic.log_tool_detail_failures(
                offers=[dga_offer],
                research_rows=[dga_offer],
                out_path=str(Path(tmp) / "x.json"),
            )
        check = payload["pr34_categorization_check"]
        self.assertEqual(check["tools_wanted"], 5)
        self.assertEqual(check["dtd152z_categorized_as"], "not_risky_lowest")
        self.assertEqual(check["dub185z_categorized_as"], "not_risky_lowest")
        self.assertTrue(check["passes"])
        dga = payload["near_publish_diagnostic"]["dga452z"]
        self.assertFalse(dga["near_publish_flag"])
        self.assertTrue(dga["research_model_present"])
        self.assertEqual(dga["comparator_depth"], 2)
        self.assertIn("sample_count=2", dga["explanation"])



if __name__ == "__main__":
    unittest.main()

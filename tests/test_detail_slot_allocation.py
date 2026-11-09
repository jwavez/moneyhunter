"""Task 7 — Option B refined detail-slot allocation + diagnostic label splits."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moneyhunter import details, market, publication, tools_slot_diagnostic
from moneyhunter.scanners import ebay

NOW = dt.datetime.now(dt.timezone.utc).replace(minute=0, second=0, microsecond=0) - dt.timedelta(hours=1)


def demand(cat, identity, near_publish=False):
    return {"category": cat, "identity": identity, "near_publish": near_publish}


def grants_by_cat(rows):
    out = {}
    for r in rows:
        out[r["category"]] = out.get(r["category"], 0) + 1
    return out


class PlanSlotGrants(unittest.TestCase):
    def test_1_round_robin_three_categories_four_slots(self):
        rows = (
            [demand("tools", f"t{i}") for i in range(10)]
            + [demand("trainers", f"r{i}") for i in range(5)]
            + [demand("tech", f"e{i}") for i in range(3)]
        )
        grants = details.plan_slot_grants(rows)
        self.assertEqual(len(grants), 4)
        by = grants_by_cat(grants)
        self.assertGreaterEqual(by.get("tools", 0), 1)
        self.assertGreaterEqual(by.get("trainers", 0), 1)
        self.assertGreaterEqual(by.get("tech", 0), 1)

    def test_2_round_robin_one_category_all_to_tools(self):
        rows = [demand("tools", f"t{i}") for i in range(10)]
        grants = details.plan_slot_grants(rows)
        self.assertEqual(len(grants), 4)
        self.assertEqual(grants_by_cat(grants), {"tools": 4})

    def test_3_round_robin_uneven_no_starvation(self):
        rows = (
            [demand("tools", f"t{i}") for i in range(3)]
            + [demand("trainers", "r0")]
            + [demand("tech", "e0")]
        )
        grants = details.plan_slot_grants(rows)
        self.assertEqual(len(grants), 4)
        by = grants_by_cat(grants)
        # No category with demand gets 0 while another gets >1 beyond fair floor+RR.
        for cat in ("tools", "trainers", "tech"):
            self.assertGreaterEqual(by.get(cat, 0), 1, cat)
        # tools may get 2 via floor; trainers/tech get 1 each — no zero-while-another>1 unfairly
        self.assertTrue(all(v >= 1 for v in by.values()))

    def test_4_fragrance_excluded_from_primary_leftover_only(self):
        rows = [demand("fragrance", f"f{i}") for i in range(5)] + [
            demand("tools", f"t{i}") for i in range(3)
        ]
        grants = details.plan_slot_grants(rows)
        self.assertEqual(len(grants), 4)
        by = grants_by_cat(grants)
        self.assertEqual(by.get("tools"), 3)
        self.assertEqual(by.get("fragrance"), 1)

    def test_5_near_publish_priority_within_category(self):
        rows = [
            demand("tools", "plain", near_publish=False),
            demand("tools", "near", near_publish=True),
        ]
        grants = details.plan_slot_grants(rows, limit=1)
        self.assertEqual(len(grants), 1)
        self.assertEqual(grants[0]["identity"], "near")

    def test_6_no_near_publish_preserves_existing_order(self):
        rows = [
            demand("tools", "first", near_publish=False),
            demand("tools", "second", near_publish=False),
        ]
        grants = details.plan_slot_grants(rows, limit=1)
        self.assertEqual(grants[0]["identity"], "first")


class DetailCheckLabels(unittest.TestCase):
    def _ask(self, detail_status, sources=3):
        src = [
            {
                "url": f"https://www.ebay.co.uk/itm/{100 + n}",
                "title": "DeWalt DCF887N 18V Bare Tool",
                "listed_total": 50 + n,
                "item_price": 50 + n,
                "shipping": 0.0,
                "seller": f"s{n}",
                "country": "GB",
                "currency": "GBP",
                "declared_condition": "new",
            }
            for n in range(sources)
        ]
        return {
            "title": "DeWalt DCF887N 18V XR Brushless Impact Driver (Body Only)",
            "category": "tools",
            "url": "https://hukd.example/dcf887n",
            "ask_estimate": {
                "model": "competitor-asks-v1",
                "suggested_listing": 50.0,
                "estimated_resale": 48.0,
                "observed_at": NOW.isoformat(),
                "detail_status": detail_status,
                "query": "DeWalt DCF887N bare tool 18V",
                "sources": src,
            },
        }

    def test_7_pending_vs_failed_both_block_publication(self):
        pending = publication.proof(self._ask("awaiting_detail_budget"))
        failed = publication.proof(self._ask("conflict"))
        self.assertEqual(pending.get("reason"), "detail_check_pending")
        self.assertEqual(failed.get("reason"), "detail_check_failed")
        self.assertFalse(pending.get("ok"))
        self.assertFalse(failed.get("ok"))
        self.assertNotEqual(pending.get("reason"), "exact_item_details_unverified")
        self.assertNotEqual(failed.get("reason"), "exact_item_details_unverified")


class DiagnosticLabels(unittest.TestCase):
    def test_8_research_model_value_rename(self):
        details.reset_slot_log()
        offers = [
            {
                "title": "Makita DGA452Z 18V Angle Grinder Body Only",
                "url": "https://hukd.example/dga",
                "category": "tools",
            }
        ]
        research = [
            {
                "url": "https://hukd.example/dga",
                "category": "tools",
                "ask_estimate": {
                    "model": "competitor-asks-v1",
                    "suggested_listing": 40.0,
                    "estimated_resale": 38.0,
                    "observed_at": NOW.isoformat(),
                    "detail_status": "awaiting_detail_budget",
                    "query": "Makita DGA452Z bare tool 18V",
                    "sources": [],
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tools_slot_diagnostic.json"
            payload = tools_slot_diagnostic.log_tool_slot_allocation(
                offers=offers,
                research_rows=research,
                out_path=str(out),
                state={"detail_run": {"calls": 0, "reserved_tools": 2}, "browse_usage": {"date": NOW.date().isoformat(), "calls": 1}},
            )
        dga = payload["dga452z_publication_status"]
        self.assertIn("research_model_value", dga)
        self.assertNotIn("supported_estimate_value", dga)
        self.assertIn("publication_estimate_value", dga)
        # Not publication-qualified → publication_estimate_value is null
        self.assertIsNone(dga["publication_estimate_value"])

    def test_9_wanted_vs_considered(self):
        details.reset_slot_log()
        # 3 wanted tools + 7 inspect_skip in same category log
        for i in range(3):
            details.SLOT_EVENTS.append(
                {
                    "phase": "inspect",
                    "category": "tools",
                    "identity": f"wanted-{i}",
                    "getitem_requested": True,
                    "getitem_granted": False,
                    "denial_reason": "slots_exhausted",
                }
            )
        for i in range(7):
            details.SLOT_EVENTS.append(
                {
                    "phase": "inspect_skip",
                    "category": "tools",
                    "identity": f"skip-{i}",
                    "getitem_requested": False,
                    "getitem_granted": False,
                    "denial_reason": "not_risky_lowest",
                }
            )
        with tempfile.TemporaryDirectory() as tmp:
            payload = tools_slot_diagnostic.log_tool_slot_allocation(
                offers=[],
                research_rows=[],
                out_path=str(Path(tmp) / "x.json"),
                state={"detail_run": {"calls": 0, "reserved_tools": 2}},
            )
        by = {r["category"]: r for r in payload["per_category_slot_summary"]}
        tools = by["tools"]
        self.assertEqual(tools["considered"], 10)
        self.assertEqual(tools["wanted"], 3)
        self.assertEqual(tools["denied_not_risky_lowest"], 7)
        self.assertEqual(
            tools["wanted"],
            tools["granted"]
            + tools["denied_slots_exhausted"]
            + tools["denied_cache_hit"]
            + tools["denied_other"],
        )


class LimitUnchanged(unittest.TestCase):
    def test_detail_limit_still_four(self):
        self.assertEqual(details.LIMIT, 4)


if __name__ == "__main__":
    unittest.main()

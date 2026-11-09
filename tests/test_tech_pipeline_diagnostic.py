"""Tech pipeline diagnostic — read-only; never changes gates/parsers."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from moneyhunter import details, tech_pipeline_diagnostic

NOW = dt.datetime(2026, 11, 9, 14, 0, tzinfo=dt.timezone.utc)


class TechParsers(unittest.TestCase):
    def test_brand_other_vs_unknown_rule(self):
        self.assertEqual(tech_pipeline_diagnostic.parse_tech_brand("Random bluetooth earbuds"), "other")
        self.assertEqual(tech_pipeline_diagnostic.parse_tech_brand("Just text"), "unknown")
        self.assertEqual(tech_pipeline_diagnostic.parse_tech_brand(""), "unknown")
        self.assertEqual(tech_pipeline_diagnostic.parse_tech_brand(None), "unknown")

    def test_named_brands(self):
        cases = [
            ("Soundcore P40I Black", "soundcore"),
            ("Anker Soundcore R50I", "soundcore"),
            ("Bose QuietComfort Ultra", "bose"),
            ("Sony WF-C510 Yellow", "sony"),
            ("JBL Tune Buds", "jbl"),
            ("Sennheiser Accentum", "sennheiser"),
            ("Google Pixel Buds Pro", "google"),
            ("Samsung Galaxy Buds2", "samsung"),
            ("Apple AirPods Pro", "apple"),
            ("Beats Fit Pro", "beats"),
        ]
        for title, brand in cases:
            self.assertEqual(tech_pipeline_diagnostic.parse_tech_brand(title), brand, title)

    def test_colour_ambiguous(self):
        self.assertEqual(
            tech_pipeline_diagnostic.parse_tech_colour("Sony WH-1000XM5 Black or Silver"),
            "ambiguous",
        )
        self.assertEqual(tech_pipeline_diagnostic.parse_tech_colour("Sony WF-C510 Yellow"), "yellow")


class TechPipelineDiagnostic(unittest.TestCase):
    def setUp(self):
        details.reset_slot_log()

    def test_by_stage_and_parse_readiness_sum(self):
        offers = [
            {
                "title": "Soundcore P40I Black Wireless Earbuds",
                "url": "https://hukd.example/sc1",
                "category": "tech",
                "price": 39.99,
            },
            {
                "title": "Sony WF-C510 Yellow",
                "url": "https://hukd.example/sony1",
                "category": "tech",
                "price": 49.0,
            },
            {
                "title": "Refurbished Sony WF-C510 Black",
                "url": "https://hukd.example/refurb",
                "category": "tech",
                "price": 29.0,
            },
            {
                "title": "Random bluetooth earbuds",
                "url": "https://hukd.example/other",
                "category": "tech",
                "price": 15.0,
            },
            {"title": "Nike shoe", "url": "https://hukd.example/nike", "category": "trainers", "price": 40},
        ]
        research = [
            {
                "url": "https://hukd.example/sony1",
                "category": "tech",
                "ask_estimate": {
                    "model": "competitor-asks-v1",
                    "observed_at": NOW.isoformat(),
                    "suggested_listing": 55.0,
                    "estimated_resale": 53.0,
                    "detail_status": "verified_fields",
                    "query": "Sony WFC510 yellow",
                    "sources": [],
                    "seller_count": 2,
                    "sample_count": 2,
                    "low_price_supporting_sellers": 1,
                    "competitor_coupon_unknown": False,
                    "estimated_opportunity": False,
                    "worth_reviewing": False,
                    "checks": ["Fewer than five independent sellers"],
                },
                "ask_context": {
                    "query": "Sony WFC510 yellow",
                    "offers": [{"seller": "a", "listed_total": 55.0}, {"seller": "b", "listed_total": 56.0}],
                    "sample_count": 2,
                    "detail_status": "verified_fields",
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            payload = tech_pipeline_diagnostic.log_tech_pipeline(
                offers=offers, research_rows=research, out_path=str(Path(tmp) / "x.json")
            )
        self.assertIsNone(payload["error"])
        agg = payload["aggregate"]
        self.assertEqual(agg["total_offers"], 4)
        self.assertEqual(sum(agg["by_stage"].values()), agg["total_offers"])
        self.assertEqual(sum(agg["by_parse_readiness"].values()), agg["total_offers"])
        for stage in tech_pipeline_diagnostic.STAGES:
            self.assertIn(stage, agg["by_stage"])
        for brand in tech_pipeline_diagnostic.BRAND_KEYS:
            self.assertIn(brand, agg["by_brand"])
            self.assertIn(brand, payload["brand_comparison"])
        # Refurbished excluded stage present
        refurb = [e for e in payload["entries"] if e["offer_url"].endswith("/refurb")]
        self.assertEqual(refurb[0]["identity_match"], "refurbished_excluded")
        self.assertEqual(refurb[0]["failure_stage"], "refurbished_excluded")
        self.assertEqual(len(payload["tech_offers"]), 4)

    def test_slots_exhausted_forces_detail_check_pending(self):
        details.reset_slot_log()
        offer = {
            "title": "Sony WF-C510 Yellow",
            "url": "https://hukd.example/sony-slot",
            "category": "tech",
            "price": 49.0,
        }
        # Ensure identity matches so we can reach slot logic.
        details.SLOT_EVENTS.append(
            {
                "phase": "inspect",
                "category": "tech",
                "identity": "Sony WFC510 yellow",
                "getitem_requested": True,
                "getitem_granted": False,
                "denial_reason": "slots_exhausted",
            }
        )
        research = {
            "url": offer["url"],
            "category": "tech",
            "ask_context": {"query": "Sony WFC510 yellow", "offers": [], "sample_count": 0},
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = tech_pipeline_diagnostic.log_tech_pipeline(
                offers=[offer], research_rows=[research], out_path=str(Path(tmp) / "x.json")
            )
        entry = payload["entries"][0]
        if entry["identity_match"] == "matched":
            self.assertTrue(entry["getitem_denied_slots_exhausted"])
            self.assertEqual(entry["failure_stage"], "detail_check_pending")


if __name__ == "__main__":
    unittest.main()

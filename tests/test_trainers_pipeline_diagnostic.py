"""Trainers pipeline diagnostic — read-only; never changes gates/parsers."""
import datetime as dt
import tempfile
import unittest
from pathlib import Path

from moneyhunter import details, publication, trainers_pipeline_diagnostic

NOW = dt.datetime(2026, 11, 9, 13, 0, tzinfo=dt.timezone.utc)


def nike_offer(**kw):
    base = {
        "title": "Nike Air Max HJ5996-003 UK 5.5 Mens Black",
        "url": "https://hukd.example/nike-1",
        "category": "trainers",
        "price": 49.99,
        "merchant": "Footasylum",
    }
    base.update(kw)
    return base


def adidas_offer(**kw):
    base = {
        "title": "adidas Samba IH4316 UK 3.5",
        "url": "https://hukd.example/adidas-1",
        "category": "trainers",
        "price": 55.0,
        "merchant": "JD",
    }
    base.update(kw)
    return base


class TrainersPipelineDiagnostic(unittest.TestCase):
    def setUp(self):
        details.reset_slot_log()

    def test_by_stage_sums_to_total_and_nike_matched(self):
        offers = [
            nike_offer(),
            adidas_offer(),
            {
                "title": "Random canvas shoes UK 8",
                "url": "https://hukd.example/other",
                "category": "trainers",
                "price": 20.0,
            },
            {
                "title": "Nike Dunk multi UK 8 / 9 Mens",
                "url": "https://hukd.example/ambig",
                "category": "trainers",
                "price": 40.0,
            },
            # Non-trainer ignored
            {"title": "DeWalt tool", "url": "https://hukd.example/tool", "category": "tools", "price": 10},
        ]
        # Give Nike a research model that fails depth.
        sources = [
            {
                "url": f"https://www.ebay.co.uk/itm/{i}",
                "title": "Nike HJ5996-003 UK 5.5",
                "listed_total": 70.0 + i,
                "item_price": 70.0 + i,
                "shipping": 0.0,
                "seller": f"s{i}",
                "country": "GB",
                "currency": "GBP",
                "declared_condition": "new",
                "item_id": f"v1|{i}|0",
            }
            for i in range(2)
        ]
        research = [
            {
                "url": "https://hukd.example/nike-1",
                "category": "trainers",
                "title": offers[0]["title"],
                "item_price": 49.99,
                "ask_estimate": {
                    "model": "competitor-asks-v1",
                    "observed_at": NOW.isoformat(),
                    "suggested_listing": 70.0,
                    "estimated_resale": 68.0,
                    "detail_status": "not_required",
                    "query": "Nike HJ5996-003 UK 5.5",
                    "sources": sources,
                    "seller_count": 2,
                    "sample_count": 2,
                    "low_price_supporting_sellers": 1,
                    "competitor_coupon_unknown": False,
                    "estimated_opportunity": False,
                    "worth_reviewing": False,
                    "checks": ["Fewer than five independent sellers"],
                },
                "ask_context": {
                    "query": "Nike HJ5996-003 UK 5.5",
                    "offers": sources,
                    "sample_count": 2,
                    "detail_status": "not_required",
                },
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "trainers_pipeline_diagnostic.json"
            payload = trainers_pipeline_diagnostic.log_trainer_pipeline(
                offers=offers, research_rows=research, out_path=str(out)
            )
        self.assertIsNone(payload["error"])
        agg = payload["aggregate"]
        self.assertEqual(agg["total_offers"], 4)
        self.assertEqual(sum(agg["by_stage"].values()), agg["total_offers"])
        # All vocabulary keys present (zeros included).
        for stage in trainers_pipeline_diagnostic.STAGES:
            self.assertIn(stage, agg["by_stage"])
        bc = payload["brand_comparison"]
        self.assertGreater(bc["nike"]["identity_matched"], 0)
        self.assertEqual(bc["adidas"]["identity_matched"], 0)
        self.assertEqual(len(payload["trainer_offers"]), 4)
        # Nike matched entry exists.
        nike_entries = [e for e in payload["entries"] if e["brand_parsed"] == "nike" and e["identity_match"] == "matched"]
        self.assertTrue(nike_entries)
        self.assertTrue(nike_entries[0]["canonical_identity"].startswith("Nike "))

    def test_ambiguous_vs_not_supported_stages(self):
        offers = [
            {
                "title": "Nike Dunk UK 8 / 9 Mens FJ1234-001",
                "url": "https://hukd.example/ambig2",
                "category": "trainers",
                "price": 40.0,
            },
            {
                "title": "Puma running shoes",
                "url": "https://hukd.example/puma",
                "category": "trainers",
                "price": 30.0,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            payload = trainers_pipeline_diagnostic.log_trainer_pipeline(
                offers=offers, research_rows=[], out_path=str(Path(tmp) / "x.json")
            )
        by_url = {e["offer_url"]: e for e in payload["entries"]}
        self.assertEqual(by_url["https://hukd.example/ambig2"]["identity_match"], "ambiguous")
        self.assertEqual(by_url["https://hukd.example/ambig2"]["failure_stage"], "identity_ambiguous")
        self.assertEqual(by_url["https://hukd.example/puma"]["identity_match"], "not_supported")
        self.assertEqual(by_url["https://hukd.example/puma"]["failure_stage"], "identity_not_supported")

    def test_no_extra_getitem_or_publication_mutation(self):
        offer = nike_offer()
        with tempfile.TemporaryDirectory() as tmp:
            payload = trainers_pipeline_diagnostic.log_trainer_pipeline(
                offers=[offer], research_rows=[], out_path=str(Path(tmp) / "x.json")
            )
        self.assertIsNone(payload["error"])
        # Diagnostic must not invent publication_qualified without proof.
        self.assertFalse(payload["entries"][0]["publication_qualified"])



    def test_getitem_denied_slots_exhausted_forces_detail_check_pending(self):
        """Invariant: slot exhaustion is detail_check_pending, not no_comparators_found."""
        details.reset_slot_log()
        offer = nike_offer(url="https://hukd.example/nike-slot")
        # Matched Nike identity with empty comparators would previously look like no_comparators.
        details.SLOT_EVENTS.append(
            {
                "phase": "inspect",
                "category": "trainers",
                "identity": "Nike HJ5996-003 UK 5.5",
                "getitem_requested": True,
                "getitem_granted": False,
                "denial_reason": "slots_exhausted",
            }
        )
        research = {
            "url": offer["url"],
            "category": "trainers",
            "ask_context": {"query": "Nike HJ5996-003 UK 5.5", "offers": [], "sample_count": 0},
            "ask_status": "not queried",
        }
        with tempfile.TemporaryDirectory() as tmp:
            payload = trainers_pipeline_diagnostic.log_trainer_pipeline(
                offers=[offer], research_rows=[research], out_path=str(Path(tmp) / "x.json")
            )
        entry = payload["entries"][0]
        self.assertTrue(entry["getitem_denied_slots_exhausted"])
        self.assertEqual(entry["failure_stage"], "detail_check_pending")

if __name__ == "__main__":
    unittest.main()

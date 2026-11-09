"""Task 16 Part D — approximate_priced retired in favour of research_model_only."""
import unittest
from moneyhunter import pricing_labels as L

class PricingLabels(unittest.TestCase):
    def test_exact_priced_has_listing(self):
        row={'ask_estimate':{'suggested_listing':15.13,'estimated_resale':15.0}}
        self.assertEqual(L.classify(row),'exact_priced')
    def test_research_model_only_when_no_selling_price(self):
        row={'ask_estimate':{'model':'competitor-asks-v1','estimated_resale':None,'suggested_listing':None}}
        self.assertEqual(L.classify(row),'research_model_only')
    def test_unpriced_without_estimate(self):
        self.assertEqual(L.classify({}),'unpriced')
    def test_summarize_drops_approximate_alias(self):
        rows=[
            {'ask_estimate':{'suggested_listing':10.0}},
            {'ask_estimate':{'model':'competitor-asks-v1'}},
            {},
        ]
        s=L.summarize(rows)
        self.assertEqual(s['exact_priced'],1)
        self.assertEqual(s['research_model_only'],1)
        self.assertEqual(s['unpriced'],1)
        self.assertIsNone(s['approximate_priced'])

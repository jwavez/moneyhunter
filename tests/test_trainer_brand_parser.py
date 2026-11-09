"""Deterministic trainer brand labels — diagnostic only."""
import unittest

from moneyhunter.trainers_pipeline_diagnostic import NAMED_TRAINER_BRANDS, parse_trainer_brand


class TrainerBrandParser(unittest.TestCase):
    CASES = [
        ("nike", ["Nike Air Max", "NIKE dunk", "nike free"]),
        ("adidas", ["adidas Samba", "Adidas Originals", "ADIDAS run"]),
        ("asics", ["ASICS Gel", "Asics Gel-Lyte", "asics contend"]),
        ("new balance", ["New Balance 480", "NEW BALANCE Arishi", "new balance 574"]),
        ("reebok", ["Reebok Classic", "REEBOK Club"]),
        ("vans", ["VANS Old Skool", "Vans Authentic"]),
        ("puma", ["Puma RS-X", "PUMA Suede"]),
        ("saucony", ["Saucony Ride", "SAUCONY Jazz"]),
        ("veja", ["Veja Esplar", "VEJA Campo"]),
        ("skechers", ["Skechers Summits", "Women's Skechers"]),
        ("boss", ["BOSS Aiden", "Boss trainers"]),
        ("helly hansen", ["Helly Hansen Buzzard", "HELLY HANSEN shoe"]),
        ("on running", ["On Running Cloudsurfer", "ON RUNNING cloud"]),
        ("hoka", ["HOKA Clifton", "Hoka Bondi"]),
        ("under armour", ["Under Armour HOVR", "UNDER ARMOUR flow"]),
        ("fila", ["Fila Disruptor", "FILA trainers"]),
        ("converse", ["Converse Chuck", "CONVERSE All Star"]),
        ("salomon", ["Salomon XT", "SALOMON trail"]),
        ("brooks", ["Brooks Ghost", "BROOKS Glycerin"]),
    ]

    def test_named_brands_case_variants(self):
        self.assertEqual(len(NAMED_TRAINER_BRANDS), 19)
        for expected, titles in self.CASES:
            for title in titles:
                self.assertEqual(
                    parse_trainer_brand(title),
                    expected,
                    msg=f"{title!r} should map to {expected!r}",
                )

    def test_other_and_unknown(self):
        self.assertEqual(parse_trainer_brand("Random canvas shoes UK 8"), "other")
        self.assertEqual(parse_trainer_brand(""), "unknown")
        self.assertEqual(parse_trainer_brand(None), "unknown")
        self.assertEqual(parse_trainer_brand("Just some text"), "unknown")


if __name__ == "__main__":
    unittest.main()

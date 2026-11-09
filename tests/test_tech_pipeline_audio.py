"""Task 12 — audio brand/model/colour/is_audio diagnostic parsers (read-only)."""
import tempfile
import unittest
from pathlib import Path

from moneyhunter import tech_pipeline_diagnostic as T


class AudioBrandParsing(unittest.TestCase):
    def test_each_audio_brand_sample(self):
        cases = [
            ("Soundcore P40i Black Earbuds", "soundcore"),
            ("Bose QuietComfort Ultra Headphones", "bose"),
            ("Sony WF-C510 Yellow", "sony"),
            ("JBL Tune 205 Black", "jbl"),
            ("Sennheiser Accentum Wireless", "sennheiser"),
            ("Google Pixel Buds Pro Hazel", "google"),
            ("Samsung Galaxy Buds FE Graphite", "samsung"),
            ("Apple AirPods Pro 2", "apple"),
            ("Beats Fit Pro Black", "beats"),
            ("Bowers & Wilkins PX7 S2e Black", "bowers_wilkins"),
            ("Skullcandy Crusher 720 Black", "skullcandy"),
            ("Nothing Ear (2) White", "nothing"),
            ("CMF Headphone Pro Black", "cmf"),
            ("Sonos Ace Black Headphones", "sonos"),
            ("Marshall Major IV Brown", "marshall"),
            ("JVC Gumy Wireless Blue", "jvc"),
            ("TCL CrystalClip Headphones", "tcl"),
            ("Technics EAH-AZ60M2 Black", "technics"),
            ("Shure AONIC 50 Black", "shure"),
            ("AKG K371 Black Headphones", "akg"),
        ]
        self.assertEqual(len(cases), 20)
        for title, brand in cases:
            self.assertEqual(T.parse_tech_brand(title), brand, title)

    def test_nothing_and_apple_guards(self):
        self.assertEqual(T.parse_tech_brand("Nothing has changed in this SIM deal"), "unknown")
        self.assertEqual(T.parse_tech_brand("Big Apple Bundle Phone Case"), "unknown")
        self.assertEqual(T.parse_tech_brand("Honor Magic V3 vs Apple prices"), "honor")


class AudioModelParsing(unittest.TestCase):
    def test_sample_models(self):
        cases = [
            ("Soundcore P40i Black", "soundcore", "P40i"),
            ("soundcore Anker R50i True Wireless", "soundcore", "R50i"),
            ("Bose QuietComfort Ultra Headphones", "bose", "QuietComfort Ultra"),
            ("Sony WF-C510 Yellow", "sony", "WF-C510"),
            ("JBL Tune 205, Wired In-Ear Headphones - Black", "jbl", "Tune 205"),
            ("Samsung Galaxy Buds FE Graphite", "samsung", "Galaxy Buds FE"),
            ("Apple AirPods Pro 2", "apple", "AirPods Pro"),
            ("Bowers & Wilkins PX7 S2e Noise Cancelling", "bowers_wilkins", "PX7 S2e"),
            ("Skullcandy Crusher 720 Wireless", "skullcandy", "Crusher 720"),
            ("Skullcandy Smokin' Buds 360 Wireless", "skullcandy", "Smokin' Buds 360"),
            ("TCL CrystalClip Clip On", "tcl", "CrystalClip"),
            ("Google Pixel Buds 2a hazel", "google", "Pixel Buds 2a"),
        ]
        for title, brand, model in cases:
            self.assertEqual(T.parse_tech_brand(title), brand, title)
            self.assertEqual(T.parse_tech_model(title, brand), model, title)


class AudioColourParsing(unittest.TestCase):
    def test_colour_cases(self):
        cases = [
            ("JBL Tune 205, Wired In-Ear Headphones - Black", "jbl", "Tune 205", "black"),
            ("Sony WF-C510 Yellow", "sony", "WF-C510", "yellow"),
            ("Apple AirPods Max - Starlight / Purple / Orange", "apple", "AirPods Max", "ambiguous"),
            ("Oracle Red Bull Racing True Wireless 110 Earphones", "other", None, None),
            ("Sony WH-1000XM5 Black or Silver", "sony", "WH-1000XM5", "ambiguous"),
        ]
        for title, brand, model, colour in cases:
            self.assertEqual(T.parse_tech_colour(title, brand=brand, model=model), colour, title)


class IsAudioClassification(unittest.TestCase):
    def test_is_audio_true_false(self):
        true_cases = [
            "JBL Tune 205, Wired In-Ear Headphones - Black",
            "Bowers & Wilkins PX7 S2e Noise Cancelling Wireless Headphones Anthracite Black",
            "Skullcandy Crusher 720 Wireless Sensory Bass Headphones (True Black)",
            "Apple AirPods 4 Wireless Earbuds",
            "Sony WF-C510 Yellow",
        ]
        false_cases = [
            "Apple MacBook Pro 14-inch M4",
            "Apple iPhone 16 128GB",
            "EE SIM Only Deal 24 Months",
            "HP OMEN 16L Gaming Desktop, AMD Ryzen 5 , 16GB, 1TB, NVIDIA GeForce RTX 5060 Ti 8GB, with Xbox Game Pass with code",
            "Samsung Galaxy Watch 7 40mm",
        ]
        for title in true_cases:
            brand = T.parse_tech_brand(title)
            model = T.parse_tech_model(title, brand)
            self.assertTrue(T.classify_is_audio(title, brand, model), title)
        for title in false_cases:
            brand = T.parse_tech_brand(title)
            model = T.parse_tech_model(title, brand)
            self.assertFalse(T.classify_is_audio(title, brand, model), f"{title} -> {brand}/{model}")


class AudioSubsetAggregate(unittest.TestCase):
    def test_audio_subset_sums(self):
        offers = [
            {
                "title": "JBL Tune 205, Wired In-Ear Headphones - Black",
                "url": "https://hukd.example/jbl",
                "category": "tech",
                "price": 7.87,
            },
            {
                "title": "Apple MacBook Pro 14 M4",
                "url": "https://hukd.example/mbp",
                "category": "tech",
                "price": 1499.0,
            },
            {
                "title": "HP OMEN 16L Gaming Desktop",
                "url": "https://hukd.example/hp",
                "category": "tech",
                "price": 1196.1,
            },
            {
                "title": "Skullcandy Crusher 720 Wireless Sensory Bass Headphones (True Black)",
                "url": "https://hukd.example/sc",
                "category": "tech",
                "price": 99.99,
            },
        ]
        with tempfile.TemporaryDirectory() as tmp:
            payload = T.log_tech_pipeline(offers, [], out_path=str(Path(tmp) / "x.json"))
        self.assertIsNone(payload["error"])
        audio = payload["aggregate"]["audio_subset"]
        self.assertEqual(audio["total_audio_offers"], 2)
        self.assertEqual(sum(audio["by_parse_readiness_audio"].values()), audio["total_audio_offers"])
        by_url = {e["offer_url"]: e for e in payload["entries"]}
        self.assertTrue(by_url["https://hukd.example/jbl"]["is_audio"])
        self.assertEqual(by_url["https://hukd.example/jbl"]["model_parsed"], "Tune 205")
        self.assertEqual(by_url["https://hukd.example/jbl"]["colour_parsed"], "black")
        self.assertFalse(by_url["https://hukd.example/mbp"]["is_audio"])
        self.assertFalse(by_url["https://hukd.example/hp"]["is_audio"])


if __name__ == "__main__":
    unittest.main()

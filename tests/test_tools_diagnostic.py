"""Tools publication diagnostic only — no gate or routing behaviour changes."""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from moneyhunter import tools_diagnostic, publication


class ToolsDiagnostic(unittest.TestCase):
    def test_records_existing_publication_reason_without_changing_proof(self):
        offers = [
            {
                "title": "Makita DUB185Z 18V LXT Blower Body Only",
                "category": "tools",
                "url": "https://example.com/tools/dub185z",
                "ask_estimate": {"query": "Makita DUB185Z"},
                "publication_proof": {"ok": False, "reason": "fewer_than_three_exact_independent_comparators"},
            },
            {
                "title": "LEGO 72051 ignored",
                "category": "lego",
                "url": "https://example.com/lego",
                "publication_proof": {"ok": True},
            },
            {
                "title": "Unknown tool no identity",
                "category": "tools",
                "url": "https://example.com/tools/other",
                "publication_proof": {"ok": False, "reason": "no_supported_resale_estimate"},
            },
        ]
        research = [
            {
                "url": "https://example.com/tools/dub185z",
                "ask_estimate": {"query": "Makita DUB185Z"},
                "publication_proof": {"ok": False, "reason": "fewer_than_three_exact_independent_comparators"},
            }
        ]
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tools_diagnostic.json"
            with patch.object(publication, "proof") as proof:
                payload = tools_diagnostic.log_tool_publication_reasons(
                    offers=offers,
                    research_rows=research,
                    publication_rows=offers,
                    out_path=str(out),
                )
                proof.assert_not_called()
            self.assertTrue(out.exists())
            data = json.loads(out.read_text())
            self.assertIsNone(data["error"])
            self.assertEqual(len(data["entries"]), 2)
            first = data["entries"][0]
            self.assertEqual(first["title"], offers[0]["title"])
            self.assertEqual(first["identity"], "Makita DUB185Z bare tool 18V")
            self.assertTrue(first["model_generated"])
            self.assertFalse(first["publication_qualified"])
            self.assertEqual(first["blocker_field"], "reason")
            self.assertEqual(first["blocker_reason"], "fewer_than_three_exact_independent_comparators")
            second = data["entries"][1]
            self.assertEqual(second["identity"], "none")
            self.assertFalse(second["model_generated"])
            self.assertEqual(second["blocker_reason"], "no_supported_resale_estimate")
            self.assertEqual(payload, data)

    def test_call_site_errors_are_written_not_raised(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "tools_diagnostic.json"
            # Force a failure inside the diagnostic body by passing a non-iterable offers value
            # after the function starts; the public API still returns a payload and writes the file.
            with patch.object(tools_diagnostic, "_identity_string", side_effect=RuntimeError("boom")):
                payload = tools_diagnostic.log_tool_publication_reasons(
                    offers=[{"title": "x", "category": "tools", "url": "https://example.com/x"}],
                    research_rows=[],
                    publication_rows=[],
                    out_path=str(out),
                )
            self.assertTrue(out.exists())
            self.assertIn("RuntimeError", payload["error"])
            self.assertEqual(payload["entries"], [])


if __name__ == "__main__":
    unittest.main()

"""Regressions learned from live execution; fixtures remain synthetic."""
import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error
import urllib.parse
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import research as r

class LiveRegressionTests(unittest.TestCase):
    def test_cursor_sort_compatible_with_publication_window(self):
        requests = []
        def fetch(url):
            requests.append(urllib.parse.parse_qs(urllib.parse.urlsplit(url).query))
            return {"message": {"items": []}}
        with tempfile.TemporaryDirectory() as d:
            result = r.search("fixture", "2026-08-01", "2026-09-01", Path(d)/"out", fetch=fetch)
        self.assertEqual(requests[0]["sort"], ["indexed"])
        self.assertIn("from-pub-date:2026-08-01", requests[0]["filter"][0])
        self.assertEqual(result["server_sort"], "indexed")

    def test_http_validation_detail_survives(self):
        error = urllib.error.HTTPError("https://api.crossref.org/v1/works", 400, "Bad Request", {}, io.BytesIO(b"synthetic validation error"))
        with patch("research.urllib.request.urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, "synthetic validation error"):
                r.get_json("https://api.crossref.org/v1/works")

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            r.search("fixture", "2026-08-01", "2026-09-01", "unused", mode="invalid")

if __name__ == "__main__":
    unittest.main()

"""Integration smoke tests: execute real Streamlit pages against shipped SQLite.

No API keys, network calls or future-fixture modeling required.
The tests use Streamlit's official AppTest harness, not screenshot claims.
"""
import hashlib
import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parent
DATABASE = ROOT / "football.db"
PAGE_CASES = (
    ("app.py", "Football Analytics"),
    ("pages/7_ChatGPT_Research_Export.py", "Historical Research Export"),
    ("pages/8_Historical_Fixture_Link_Review.py", "Historical Fixture Link Review"),
    ("pages/11_Multi_Season_Historical_Evaluation.py", "Multi-Season"),
    ("pages/12_Historical_xG_Analysis.py", "Historical xG"),
    ("pages/13_Historical_Coverage_Audit.py", "Coverage"),
    ("pages/14_Historical_Import_Gap_Planner.py", "Import Gap Planner"),
)


class StreamlitSmokeTests(unittest.TestCase):
    def test_main_and_research_pages_render_from_shipped_database(self):
        self.assertTrue(DATABASE.exists(), "Shipped football.db is required")
        before = hashlib.sha256(DATABASE.read_bytes()).hexdigest()
        for relative, expected in PAGE_CASES:
            with self.subTest(page=relative):
                page = ROOT / relative
                self.assertTrue(page.is_file())
                app = AppTest.from_file(
                    str(page), default_timeout=60
                ).run()
                problems = [str(e.message) for e in app.exception]
                self.assertEqual(problems, [], f"{relative}: {problems}")
                headings = " | ".join(
                    str(item.value) for item in app.title
                )
                self.assertIn(expected, headings)
        after = hashlib.sha256(DATABASE.read_bytes()).hexdigest()
        self.assertEqual(before, after, "Streamlit pages changed football.db")


if __name__ == "__main__":
    unittest.main()

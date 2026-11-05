"""Offline coverage classification tests using fictional historical fixtures."""
import sqlite3
import unittest

from confirm_historical_link import confirm_link
from historical_season_quality import (
    QUALITY_ORDER, build_quality_report, quality_markdown,
)
from sportmonks_historical_import import ensure_schema, store_finished_fixture
from test_historical_score_evidence import sample_fixture


class SeasonQualityTests(unittest.TestCase):
    def setUp(self):
        self.db = sqlite3.connect(":memory:")
        self.db.execute("""
            CREATE TABLE matches (
                match_id INTEGER PRIMARY KEY, date TEXT, competition TEXT,
                home_team TEXT, away_team TEXT, home_goals INTEGER,
                away_goals INTEGER, status TEXT
            )
        """)
        ensure_schema(self.db)

    def tearDown(self):
        self.db.close()

    def make(self, mid, sid, day, home, away, score=(2,1), xg=True):
        self.db.execute(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
            (mid, f"2024-10-{day:02d}T18:00:00Z",
             "Premier League",home+" FC",away+" FC",2,1,"FINISHED")
        )
        if sid is not None:
            f=sample_fixture(score=score,fid=sid)
            f["starting_at"]=f"2024-10-{day:02d} 18:00:00"
            f["name"]=home+" vs "+away
            f["participants"][0]["name"]=home
            f["participants"][1]["name"]=away
            if not xg:
                f["xgfixture"]=[]
            store_finished_fixture(self.db,f)

    def test_grades_exclude_unreviewed_xg_and_count_only_local_matches(self):
        self.make(101,9001,3,"Arsenal","Everton")
        self.make(102,9002,4,"Chelsea","Liverpool",xg=False)
        self.make(103,None,5,"Brighton","Fulham")
        self.make(104,9004,6,"Newcastle","Wolves",score=(3,1))
        self.db.execute(
            "INSERT INTO matches VALUES (?,?,?,?,?,?,?,?)",
            (999,"2024-10-07T18:00:00Z","Premier League",
             "Arsenal FC","Everton FC",3,1,"SCHEDULED")
        )
        before=build_quality_report(self.db,"Premier League",2024)
        self.assertEqual(before["locally_recorded_results"],4)
        self.assertEqual(before["grades"],{
            "A":0,"B":0,"C":2,"D":1,"U":1
        })
        self.assertEqual(before["reviewed_xg_coverage_pct"],0)
        confirm_link(self.db,9001,101,"operator",True)
        confirm_link(self.db,9002,102,"operator",True)
        after=build_quality_report(self.db,"Premier League",2024)
        self.assertEqual(after["grades"],{
            "A":1,"B":1,"C":0,"D":1,"U":1
        })
        self.assertEqual(after["reviewed_link_coverage_pct"],50)
        self.assertEqual(after["reviewed_xg_coverage_pct"],25)
        self.assertEqual(after["source_ids_by_grade"]["A"],[101])
        self.assertEqual(after["source_ids_by_grade"]["B"],[102])
        self.assertEqual(after["source_ids_by_grade"]["D"],[104])
        self.assertEqual(after["source_ids_by_grade"]["U"],[103])
        self.assertEqual(sum(x["recorded_results"]
            for x in after["by_team"]),8)
        self.assertEqual(after["by_month"][0]["month"],"2024-10")
        self.assertEqual(after["by_month"][0]["recorded_results"],4)
        md=quality_markdown(after)
        self.assertIn("Historical Season Source-Quality Audit",md)
        self.assertIn("25.00%",md)
        self.assertIn("Arsenal FC",md)

    def test_no_results_is_honestly_unavailable(self):
        report=build_quality_report(self.db,"Premier League",2024)
        self.assertEqual(report["grades"],{grade:0 for grade in QUALITY_ORDER})
        self.assertEqual(report["by_month"],[])
        self.assertEqual(report["by_team"],[])
        self.assertIsNone(report["reviewed_xg_coverage_pct"])
        self.assertIn("N/A",quality_markdown(report))

    def test_quality_audit_does_not_mutate_source_data(self):
        self.make(101,9001,3,"Arsenal","Everton")
        before=list(self.db.iterdump())
        first=build_quality_report(self.db,"Premier League",2024)
        self.assertEqual(first,build_quality_report(
            self.db,"Premier League",2024
        ))
        self.assertEqual(before,list(self.db.iterdump()))


if __name__=="__main__":
    unittest.main()

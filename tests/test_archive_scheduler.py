import importlib.util
import subprocess
import tempfile
import unittest
from datetime import date, datetime, time
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "archive_scheduler", Path(__file__).resolve().parents[1] / "docker/archive_scheduler.py")
scheduler = importlib.util.module_from_spec(spec)
spec.loader.exec_module(scheduler)


class ArchiveSchedulerTests(unittest.TestCase):
    def test_due_at_midnight_and_year_boundary(self):
        self.assertEqual(scheduler.latest_due(datetime(2027, 1, 1, 0, 9), time(0, 10)), date(2026, 12, 30))
        self.assertEqual(scheduler.latest_due(datetime(2027, 1, 1, 0, 10), time(0, 10)), date(2026, 12, 31))

    def test_publish_only_on_success(self):
        with tempfile.TemporaryDirectory() as root:
            output = Path(root)
            target = output / "2026/08/2026-08-30.md"
            target.parent.mkdir(parents=True)
            target.write_text("old")
            def download(args, **kwargs):
                staged = Path(args[-1]) / "2026/08/2026-08-30.md"
                staged.parent.mkdir(parents=True)
                staged.write_text("complete")
            with patch.object(scheduler.subprocess, "run", side_effect=subprocess.CalledProcessError(1, "cli")):
                with self.assertRaises(subprocess.CalledProcessError):
                    scheduler.archive(date(2026, 8, 30), output)
            self.assertEqual(target.read_text(), "old")
            with patch.object(scheduler.subprocess, "run", side_effect=download):
                scheduler.archive(date(2026, 8, 30), output)
            self.assertEqual(target.read_text(), "complete")
            self.assertEqual(list(output.glob(".archive-*")), [])

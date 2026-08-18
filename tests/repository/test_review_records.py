"""Repository policy for the tracked, redacted review-record corpus."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORDS = ROOT / "docs" / "internal" / "review-records"
INDEX = RECORDS / "README.md"
HEAD_RE = re.compile(r"^(?:[0-9a-f]{40}|UNCOMMITTED-ARTIFACT)$")
SOURCE_COUNT_RE = re.compile(r"^source_count: (\d+)$", re.MULTILINE)
RECORD_COUNT_RE = re.compile(r"^record_count: (\d+)$", re.MULTILINE)


class ReviewRecordPolicyTests(unittest.TestCase):
    def test_records_are_one_verdict_one_head_and_redacted(self) -> None:
        self.assertTrue(RECORDS.is_dir(), f"missing tracked record directory: {RECORDS}")
        self.assertTrue(INDEX.is_file(), f"missing record manifest: {INDEX}")

        manifest = INDEX.read_text(encoding="utf-8")
        self.assertEqual(SOURCE_COUNT_RE.findall(manifest), ["31"])
        self.assertEqual(RECORD_COUNT_RE.findall(manifest), ["34"])

        records = sorted(RECORDS.glob("record-*.md"))
        self.assertEqual(len(records), 34)
        source_items: set[str] = set()
        for path in records:
            text = path.read_text(encoding="utf-8")
            source_matches = re.findall(r"^source_item: (\d+)$", text, re.MULTILINE)
            self.assertEqual(len(source_matches), 1, path)
            source_items.add(source_matches[0])
            self.assertEqual(len(re.findall(r"^verdict: .+$", text, re.MULTILINE)), 1, path)
            heads = re.findall(r"^head: (.+)$", text, re.MULTILINE)
            self.assertEqual(len(heads), 1, path)
            self.assertRegex(heads[0], HEAD_RE, path)
            self.assertEqual(len(re.findall(r"^SIGNED-OFF$", text, re.MULTILINE)), 1, path)
            self.assertNotRegex(text, r"(?i)https?://|github\.com|SUPERSEDED|bearer\s+ey")
            self.assertNotRegex(
                text, r"(?i)(?:ghp_|xox[baprs]-|AKIA[0-9A-Z]{16}|BEGIN [A-Z ]+ PRIVATE KEY)"
            )
        self.assertEqual(source_items, {f"{number:02d}" for number in range(1, 32)})

    def test_record_only_commit_scope_is_explicit_and_machine_checkable(self) -> None:
        self.assertTrue(INDEX.is_file(), f"missing record manifest: {INDEX}")
        manifest = INDEX.read_text(encoding="utf-8")
        self.assertIn("allowed_commit_path: docs/internal/review-records/", manifest)
        self.assertIn("git diff --name-only <sha>^ <sha>", manifest)
        self.assertIn("record-only commit", manifest)


if __name__ == "__main__":
    unittest.main()

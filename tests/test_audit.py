import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from rag_siap import audit_corpus


class AuditCorpusTests(unittest.TestCase):
    def test_reports_empty_short_long_markdown_and_normalized_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "a.md").write_text("# Guide\n" + "Useful text " * 12, encoding="utf-8")
            (root / "b.txt").write_text("  # GUIDE   " + "Useful   text " * 12, encoding="utf-8")
            (root / "empty.txt").write_text(" \n\t", encoding="utf-8")
            (root / "short.md").write_text("tiny", encoding="utf-8")
            (root / "long.txt").write_text("x" * 130, encoding="utf-8")

            report = audit_corpus(root, min_chars=20, max_chars=100)
            by_path = {document.path: document for document in report.documents}
            self.assertEqual(set(by_path), {"a.md", "b.txt", "empty.txt", "long.txt", "short.md"})
            self.assertIn("duplicate", {finding.code for finding in by_path["b.txt"].findings})
            self.assertEqual(next(f for f in by_path["b.txt"].findings if f.code == "duplicate").related_path, "a.md")
            self.assertIn("empty", {finding.code for finding in by_path["empty.txt"].findings})
            self.assertIn("too_short", {finding.code for finding in by_path["short.md"].findings})
            self.assertIn("too_long", {finding.code for finding in by_path["long.txt"].findings})
            self.assertEqual(by_path["a.md"].headings, 1)
            self.assertEqual(report.summary()["files"], 5)

    def test_detects_markdown_without_heading_and_invalid_utf8_without_content(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "plain.md").write_text("A long enough paragraph that has no markdown heading.", encoding="utf-8")
            (root / "broken.txt").write_bytes(b"\xff\xfe\xff")
            report = audit_corpus(root, min_chars=1)
            by_path = {document.path: document for document in report.documents}
            self.assertIn("no_headings", {f.code for f in by_path["plain.md"].findings})
            self.assertEqual(by_path["broken.txt"].findings[0].code, "invalid_utf8")
            self.assertEqual(by_path["broken.txt"].characters, 0)

    def test_excludes_common_generated_directories_and_unsupported_extensions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".git").mkdir()
            (root / ".git" / "README.md").write_text("generated", encoding="utf-8")
            (root / "node_modules").mkdir()
            (root / "node_modules" / "vendor.txt").write_text("generated", encoding="utf-8")
            (root / "image.png").write_bytes(b"not a text file")
            (root / "docs").mkdir()
            (root / "docs" / "source.MD").write_text("# Source\nDocument body.", encoding="utf-8")
            report = audit_corpus(root)
            self.assertEqual([document.path for document in report.documents], ["docs/source.MD"])

    def test_rejects_invalid_thresholds_and_non_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            file_path = Path(directory) / "file.txt"
            file_path.write_text("text", encoding="utf-8")
            with self.assertRaises(ValueError):
                audit_corpus(directory, min_chars=10, max_chars=2)
            with self.assertRaises(ValueError):
                audit_corpus(file_path)
            with self.assertRaises(ValueError):
                audit_corpus(directory, min_chars=-1)


class CliTests(unittest.TestCase):
    def test_json_output_and_strict_exit_code(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "tiny.txt").write_text("brief", encoding="utf-8")
            command = [sys.executable, "-m", "rag_siap", str(root), "--json"]
            result = subprocess.run(command, text=True, capture_output=True, check=True)
            parsed = json.loads(result.stdout)
            self.assertEqual(parsed["root"], ".")
            self.assertNotIn(str(root), result.stdout)
            self.assertNotIn("sha256", result.stdout)
            self.assertEqual(parsed["summary"]["files"], 1)
            self.assertIn("too_short", parsed["summary"]["by_code"])

            strict = subprocess.run(command + ["--strict"], text=True, capture_output=True)
            self.assertEqual(strict.returncode, 1)
            self.assertEqual(json.loads(strict.stdout)["summary"]["findings"], 1)

    def test_empty_directory_is_valid_and_invalid_arguments_fail(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run([sys.executable, "-m", "rag_siap", directory], text=True, capture_output=True, check=True)
            self.assertIn("Tidak ada file", result.stdout)
            invalid = subprocess.run(
                [sys.executable, "-m", "rag_siap", directory, "--min-chars", "9", "--max-chars", "2"],
                text=True,
                capture_output=True,
            )
            self.assertEqual(invalid.returncode, 2)
            self.assertEqual(invalid.stdout, "")


if __name__ == "__main__":
    unittest.main()

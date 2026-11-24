"""Audit a local Markdown/TXT corpus before indexing it for retrieval."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt"}
EXCLUDED_DIRECTORIES = {".git", ".venv", "venv", "node_modules", "__pycache__"}
_HEADING = re.compile(r"^ {0,3}#{1,6}[ \t]+\S", re.MULTILINE)
_WHITESPACE = re.compile(r"\s+")


@dataclass(frozen=True)
class Finding:
    code: str
    severity: str
    message: str
    related_path: str | None = None


@dataclass
class DocumentReport:
    path: str
    characters: int
    words: int
    headings: int
    findings: list[Finding] = field(default_factory=list)


@dataclass
class AuditReport:
    root: str
    min_chars: int
    max_chars: int
    documents: list[DocumentReport]

    def summary(self) -> dict[str, Any]:
        findings = [finding for doc in self.documents for finding in doc.findings]
        return {
            "files": len(self.documents),
            "findings": len(findings),
            "by_severity": {
                severity: sum(item.severity == severity for item in findings)
                for severity in ("error", "warning", "info")
            },
            "by_code": {
                code: sum(item.code == code for item in findings)
                for code in sorted({item.code for item in findings})
            },
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "min_chars": self.min_chars,
            "max_chars": self.max_chars,
            "summary": self.summary(),
            "documents": [
                {
                    "path": doc.path,
                    "characters": doc.characters,
                    "words": doc.words,
                    "headings": doc.headings,
                    "findings": [asdict(finding) for finding in doc.findings],
                }
                for doc in self.documents
            ],
        }


def _normalized_hash(text: str) -> str:
    normalized = _WHITESPACE.sub(" ", text).strip().casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _candidate_paths(root: Path) -> list[Path]:
    candidates: list[Path] = []
    for directory, dirnames, filenames in os.walk(root, followlinks=False):
        base = Path(directory)
        dirnames[:] = sorted(
            name for name in dirnames
            if name not in EXCLUDED_DIRECTORIES and not (base / name).is_symlink()
        )
        for filename in filenames:
            path = base / filename
            if path.is_symlink() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
                continue
            candidates.append(path)
    return sorted(candidates, key=lambda path: path.relative_to(root).as_posix().casefold())


def audit_corpus(root: str | Path, min_chars: int = 80, max_chars: int = 12000) -> AuditReport:
    """Inspect local text files using simple, transparent RAG-readiness heuristics."""
    if isinstance(min_chars, bool) or not isinstance(min_chars, int) or min_chars < 0:
        raise ValueError("min_chars harus bilangan bulat >= 0")
    if isinstance(max_chars, bool) or not isinstance(max_chars, int) or max_chars < 1:
        raise ValueError("max_chars harus bilangan bulat > 0")
    if min_chars > max_chars:
        raise ValueError("min_chars tidak boleh melebihi max_chars")

    root_path = Path(root).expanduser().resolve()
    if not root_path.exists() or not root_path.is_dir():
        raise ValueError("path korpus harus direktori yang tersedia")

    documents: list[DocumentReport] = []
    first_by_hash: dict[str, str] = {}
    for path in _candidate_paths(root_path):
        relative = path.relative_to(root_path).as_posix()
        findings: list[Finding] = []
        try:
            text = path.read_text(encoding="utf-8-sig")
        except UnicodeError:
            documents.append(DocumentReport(relative, 0, 0, 0, [
                Finding("invalid_utf8", "error", "File bukan teks UTF-8 yang valid."),
            ]))
            continue
        except OSError:
            documents.append(DocumentReport(relative, 0, 0, 0, [
                Finding("unreadable", "error", "File tidak dapat dibaca."),
            ]))
            continue

        character_count = len(text)
        word_count = len(text.split())
        heading_count = len(_HEADING.findall(text)) if path.suffix.lower() in {".md", ".markdown"} else 0
        normalized = _WHITESPACE.sub(" ", text).strip()
        digest = _normalized_hash(text)

        if not normalized:
            findings.append(Finding("empty", "error", "File kosong atau hanya berisi whitespace."))
        else:
            if character_count < min_chars:
                findings.append(Finding("too_short", "warning", f"Konten lebih pendek dari ambang {min_chars} karakter."))
            if character_count > max_chars:
                findings.append(Finding("too_long", "warning", f"Konten lebih panjang dari ambang {max_chars} karakter."))
            if path.suffix.lower() in {".md", ".markdown"} and heading_count == 0:
                findings.append(Finding("no_headings", "info", "Markdown tidak memiliki heading; periksa apakah strukturnya sesuai untuk chunking."))
            prior = first_by_hash.get(digest)
            if prior is not None:
                findings.append(Finding("duplicate", "warning", "Konten sama setelah normalisasi whitespace dan kapitalisasi.", prior))
            else:
                first_by_hash[digest] = relative

        documents.append(DocumentReport(relative, character_count, word_count, heading_count, findings))

    return AuditReport(".", min_chars, max_chars, documents)


def _render_text(report: AuditReport) -> str:
    summary = report.summary()
    lines = [
        "RAG-Siap — audit korpus lokal",
        f"File teks: {summary['files']} | temuan: {summary['findings']}",
    ]
    if not report.documents:
        lines.append("Tidak ada file .md, .markdown, atau .txt yang ditemukan.")
    for doc in report.documents:
        lines.append(f"\n{doc.path} — {doc.characters} karakter, {doc.words} kata, {doc.headings} heading")
        for finding in doc.findings:
            related = f" (duplikat dari {finding.related_path})" if finding.related_path else ""
            lines.append(f"  [{finding.severity.upper()}:{finding.code}] {finding.message}{related}")
    lines.append("\nCatatan: hasil ini heuristik struktur, bukan jaminan kualitas atau relevansi jawaban RAG.")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="rag-siap-id",
        description="Audit korpus Markdown/TXT secara lokal sebelum diindeks ke sistem RAG.",
    )
    parser.add_argument("directory", help="direktori korpus lokal")
    parser.add_argument("--min-chars", type=int, default=80, help="peringatkan dokumen non-kosong yang lebih pendek (default: 80)")
    parser.add_argument("--max-chars", type=int, default=12000, help="peringatkan dokumen lebih panjang; bukan batas tokenizer (default: 12000)")
    parser.add_argument("--json", action="store_true", help="cetak laporan JSON untuk otomasi")
    parser.add_argument("--strict", action="store_true", help="kembalikan status 1 jika ada error atau warning")
    args = parser.parse_args(argv)

    try:
        report = audit_corpus(args.directory, args.min_chars, args.max_chars)
    except (OSError, ValueError) as error:
        print(f"rag-siap-id: {error}.", file=sys.stderr)
        return 2

    output = json.dumps(report.to_dict(), ensure_ascii=False, indent=2) if args.json else _render_text(report)
    print(output)
    if args.strict and any(f.severity in {"error", "warning"} for doc in report.documents for f in doc.findings):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

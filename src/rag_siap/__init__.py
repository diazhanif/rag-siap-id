"""Pemeriksaan ringan korpus teks lokal sebelum ingestion RAG."""

from .core import AuditReport, DocumentReport, Finding, audit_corpus

__all__ = ["AuditReport", "DocumentReport", "Finding", "audit_corpus"]
__version__ = "0.1.0"

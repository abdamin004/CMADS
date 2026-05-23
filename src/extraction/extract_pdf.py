"""Phase 2: PDF → text → LLM extract.

pdfplumber gives us page-by-page text + table extraction. Lab reports
often have tables (test name | value | unit | reference range), so
we concatenate per-page text + per-page rendered table text.
"""
from __future__ import annotations
import io
from typing import Any

import structlog
from src.extraction.extract_text import extract_text, MAX_TEXT_BYTES
from src.extraction.guards import assert_pdf_signature, assert_pdf_page_count

logger = structlog.get_logger(__name__)

MAX_PDF_BYTES = 5 * 1024 * 1024  # 5 MB cap per spec


def extract_pdf(content: bytes, filename: str = "uploaded.pdf") -> dict[str, Any]:
    """Parse a PDF, extract text + tables, then run the same LLM
    extraction as the text path. Returns the canonical extractor dict."""
    if len(content) > MAX_PDF_BYTES:
        raise ValueError(f"PDF exceeds {MAX_PDF_BYTES} bytes ({len(content)})")
    # Magic-byte sniff — defeats .pdf-renamed-malware uploads.
    assert_pdf_signature(content)
    try:
        import pdfplumber
    except ImportError as e:
        raise RuntimeError(
            "pdfplumber not installed. Run: pip install pdfplumber"
        ) from e
    # Page-count cap — defeats PDF bombs (massive page count, no useful text).
    assert_pdf_page_count(content)

    text_parts: list[str] = []
    with pdfplumber.open(io.BytesIO(content)) as pdf:
        for page in pdf.pages:
            t = page.extract_text() or ""
            if t.strip():
                text_parts.append(t)
            # Tables — formatted as plain pipe-separated rows
            for table in (page.extract_tables() or []):
                for row in table:
                    cells = [c if c is not None else "" for c in row]
                    text_parts.append(" | ".join(cells))

    combined = "\n".join(text_parts).strip()
    if not combined:
        raise ValueError(
            "no extractable text in PDF — may be a scanned image. "
            "Try the Image tab instead."
        )
    if len(combined.encode("utf-8")) > MAX_TEXT_BYTES:
        # Truncate to the cap and add a tail marker
        truncated = combined.encode("utf-8")[:MAX_TEXT_BYTES - 200].decode(
            "utf-8", errors="ignore"
        )
        combined = truncated + "\n\n[... text truncated to fit extraction cap ...]"
        logger.info("pdf_text_truncated", filename=filename,
                    original_bytes=len(combined.encode("utf-8")))

    result = extract_text(combined)
    # Tag the source so the audit log shows it came from a PDF
    result["source"] = {"kind": "pdf", "filename": filename, "extracted_chars": len(combined)}
    return result

"""Binary document → text. GROBID-based structured PDF parsing lives in `ingest/grobid.py`;
this module is the dependency-light fallback."""

from __future__ import annotations

import io
import re

MAX_PDF_PAGES = 300
# pdfium marks a hyphenation point at a line end with U+FFFE (sometimes a soft hyphen, U+00AD),
# often followed by the line break: "quan\ufffe\ntile" is the word "quantile". Left in, it breaks
# title matching (a real reference looks like it has a typo).
_SOFT_HYPHEN = re.compile(r"[\u00ad\ufffe]\r?\n?")


def strip_soft_hyphens(text: str) -> str:
    return _SOFT_HYPHEN.sub("", text)


PDF_MAGIC = b"%PDF-"
ZIP_MAGIC = b"PK\x03\x04"


class UnsupportedDocumentError(ValueError):
    pass


def sniff_kind(data: bytes, filename: str | None = None) -> str:
    """Decide the input kind from magic bytes first, extension second."""
    name = (filename or "").lower()
    if data.startswith(PDF_MAGIC):
        return "pdf"
    if data.startswith(ZIP_MAGIC) and (name.endswith(".docx") or b"word/" in data[:4000]):
        return "docx"
    if name.endswith(".bib"):
        return "bibtex"
    if name.endswith(".tex"):
        return "latex"
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UnsupportedDocumentError("Unsupported binary file type") from exc
    stripped = text.lstrip()
    if stripped.startswith("@") and "{" in stripped[:200]:
        return "bibtex"
    if "\\begin{document}" in text or "\\bibitem" in text:
        return "latex"
    return "text"


def pdf_to_text(data: bytes, max_pages: int = MAX_PDF_PAGES) -> str:
    import pypdfium2 as pdfium

    pdf = pdfium.PdfDocument(io.BytesIO(data))
    try:
        if len(pdf) > max_pages:
            raise UnsupportedDocumentError(f"PDF has {len(pdf)} pages (limit {max_pages})")
        pages = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            pages.append(textpage.get_text_range())
            textpage.close()
            page.close()
        return strip_soft_hyphens("\n".join(strip_running_headers(pages)))
    finally:
        pdf.close()


_EDGE_LINES = 4  # how many lines at the top and bottom of a page can be a running header/footer


def _normalise_line(line: str) -> str:
    return re.sub(r"\d+", "#", " ".join(line.split())).lower()


def strip_running_headers(pages: list[str]) -> list[str]:
    """Remove page headers/footers ("Scientific Reports | (2023) 13:14045 | …", bare page
    numbers). They repeat on most pages, and when left in they get glued onto the neighbouring
    reference, which then looks like a wrong DOI or a fabricated "citation"."""
    if len(pages) < 3:
        return pages
    split = [p.replace("\r\n", "\n").split("\n") for p in pages]
    counts: dict[str, int] = {}
    for lines in split:
        content = [ln for ln in lines if ln.strip()]
        edge = content[:_EDGE_LINES] + content[-_EDGE_LINES:]
        for key in {_normalise_line(ln) for ln in edge}:
            counts[key] = counts.get(key, 0) + 1
    threshold = max(3, int(len(pages) * 0.4))
    repeated = {k for k, n in counts.items() if n >= threshold and len(k) > 3}
    cleaned = []
    for lines in split:
        content_idx = [i for i, ln in enumerate(lines) if ln.strip()]
        edge_idx = set(content_idx[:_EDGE_LINES] + content_idx[-_EDGE_LINES:])
        keep = []
        for i, ln in enumerate(lines):
            if i in edge_idx and (
                _normalise_line(ln) in repeated or re.fullmatch(r"\s*\d{1,4}\s*", ln)
            ):
                continue
            keep.append(ln)
        cleaned.append("\n".join(keep))
    return cleaned


def docx_to_text(data: bytes) -> str:
    import docx

    document = docx.Document(io.BytesIO(data))
    return "\n".join(p.text for p in document.paragraphs)

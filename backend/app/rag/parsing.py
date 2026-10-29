"""Text extraction for supported upload types: .txt, .md, .pdf.

Parsing is pure (bytes in, text out) so it can be unit-tested without a DB.
"""

from pathlib import PurePosixPath

SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}


class DocumentParseError(Exception):
    """The file could not be turned into text (message is user-facing)."""


def extension_of(filename: str) -> str:
    """Lower-cased extension, or '' when there is none."""
    return PurePosixPath(filename).suffix.lower()


def extract_text(filename: str, data: bytes) -> str:
    ext = extension_of(filename)
    if ext not in SUPPORTED_EXTENSIONS:
        raise DocumentParseError(
            f"Unsupported file type {ext or '(none)'}; supported: "
            f"{', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )
    if ext == ".pdf":
        return _extract_pdf(data)
    return _extract_text(data)


def _extract_text(data: bytes) -> str:
    if not data.strip():
        raise DocumentParseError("File is empty")
    # utf-8-sig strips a BOM; errors="replace" keeps odd encodings usable
    text = data.decode("utf-8-sig", errors="replace")
    if not text.strip():
        raise DocumentParseError("File contains no readable text")
    return text


def _extract_pdf(data: bytes) -> str:
    import io

    from pypdf import PdfReader

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise DocumentParseError("PDF is password-protected")
        pages = []
        for number, page in enumerate(reader.pages, start=1):
            pages.append(f"[page {number}]\n{page.extract_text() or ''}")
    except DocumentParseError:
        raise
    except Exception as exc:  # pypdf raises a wide mix of error types
        raise DocumentParseError(f"Could not read PDF: {exc}") from exc

    text = "\n\n".join(pages).strip()
    if not text or text == "[page 1]":
        raise DocumentParseError(
            "PDF has no extractable text (scanned images are not supported)"
        )
    return text

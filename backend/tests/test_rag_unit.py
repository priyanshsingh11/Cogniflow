"""Pure unit tests for parsing, chunking and local storage (no DB needed)."""

import pytest

from app.rag.chunking import chunk_text, token_count
from app.rag.parsing import DocumentParseError, extension_of, extract_text
from app.storage.local import LocalStorage, StorageError


def minimal_pdf(text: str) -> bytes:
    """One-page PDF with a Tj text operator (pypdf extracts it directly)."""
    content = f"BT /F1 24 Tf 100 700 Td ({text}) Tj ET".encode()
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = []
    for i, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    trailer = f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
    out += (trailer + f"startxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)


# ---- parsing ---------------------------------------------------------------


def test_extension_of():
    assert extension_of("notes.md") == ".md"
    assert extension_of("REPORT.PDF") == ".pdf"
    assert extension_of("archive.tar.gz") == ".gz"
    assert extension_of("noextension") == ""


def test_extract_plain_text_and_markdown_with_bom():
    assert extract_text("a.txt", b"hello world") == "hello world"
    assert extract_text("a.md", b"\xef\xbb\xbf# Title\n\ntext") == "# Title\n\ntext"


def test_extract_rejects_unsupported_empty_and_broken():
    with pytest.raises(DocumentParseError, match="Unsupported"):
        extract_text("sheet.xlsx", b"anything")
    with pytest.raises(DocumentParseError, match="empty"):
        extract_text("a.txt", b"   \n  ")
    with pytest.raises(DocumentParseError):
        extract_text("a.pdf", b"%PDF-1.4 truncated garbage")


def test_extract_pdf_with_text_and_without():
    text = extract_text("doc.pdf", minimal_pdf("Cogniflow RAG test document about penguins"))
    assert "penguins" in text and "[page 1]" in text
    with pytest.raises(DocumentParseError, match="no extractable text"):
        extract_text("scan.pdf", minimal_pdf(""))  # blank page = nothing to index


# ---- chunking --------------------------------------------------------------


def test_chunk_short_text_is_single_chunk():
    assert chunk_text("one short paragraph", size=100, overlap=20) == ["one short paragraph"]


def test_chunk_covers_long_text_with_overlap():
    text = "\n\n".join(f"Paragraph {i}: " + "x" * 200 for i in range(12))
    chunks = chunk_text(text, size=500, overlap=100)
    assert len(chunks) > 1
    # every chunk is bounded (size + overlap slack) and content is preserved
    assert all(len(c) <= 500 + 100 + 1 for c in chunks)
    stripped = " ".join(chunks)
    assert "Paragraph 0" in stripped and "Paragraph 11" in stripped


def test_chunk_uses_default_settings_and_handles_blank():
    assert chunk_text("") == []
    assert chunk_text("   \n  ") == []
    from app.config import settings

    chunks = chunk_text("word " * 2000)
    assert all(len(c) <= settings.chunk_size + settings.chunk_overlap + 1 for c in chunks)


def test_chunk_rejects_bad_config():
    with pytest.raises(ValueError):
        chunk_text("x" * 10, size=10, overlap=10)
    with pytest.raises(ValueError):
        chunk_text("x" * 10, size=0, overlap=0)


def test_token_count_is_approximate():
    assert token_count("") == 0
    assert token_count("abcd efgh") == 2


# ---- local storage ---------------------------------------------------------


def test_storage_roundtrip_and_idempotent_delete(tmp_path):
    store = LocalStorage(tmp_path)

    async def go():
        await store.save("ws/doc/file.md", b"bytes")
        assert await store.load("ws/doc/file.md") == b"bytes"
        await store.delete("ws/doc/file.md")
        await store.delete("ws/doc/file.md")  # missing = no error

    import asyncio

    asyncio.run(go())
    assert not (tmp_path / "ws" / "doc" / "file.md").exists()


def test_storage_rejects_path_traversal(tmp_path):
    store = LocalStorage(tmp_path)

    async def go():
        for key in ("../escape", "a/../../b", "/abs/path", "", "a//b"):
            with pytest.raises(StorageError):
                await store.save(key, b"x")

    import asyncio

    asyncio.run(go())

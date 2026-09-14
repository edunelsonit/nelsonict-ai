"""One bounded subprocess per PDF, invoked by the durable worker."""
import io
import sys
from pypdf import PdfReader
from . import db
from .config import settings
from .retrieval import chunk_text, embed


def extract_pages(pdf):
    reader = PdfReader(io.BytesIO(pdf))
    if reader.is_encrypted:
        raise ValueError("Password-protected PDFs are not supported. Upload an unlocked copy.")
    if len(reader.pages) > settings.max_pages:
        raise ValueError(f"PDF exceeds the {settings.max_pages}-page limit.")
    rendered = None
    try:
        for index, page in enumerate(reader.pages):
            text = page.extract_text() or ""
            if len(text.strip()) < 30:
                try:
                    import pypdfium2 as pdfium
                    import pytesseract
                    if rendered is None:
                        rendered = pdfium.PdfDocument(pdf)
                    render_page = rendered[index]
                    width, height = render_page.get_size()
                    scale = min(2.0, 2400 / max(width, height))
                    bitmap = render_page.render(scale=scale)
                    try:
                        image = bitmap.to_pil()
                        try:
                            ocr = pytesseract.image_to_string(image, lang=settings.ocr_language, timeout=45)
                            if len(ocr.strip()) > len(text.strip()):
                                text = ocr
                        finally:
                            image.close()
                    finally:
                        bitmap.close()
                        render_page.close()
                except ImportError:
                    if not text.strip():
                        raise ValueError("Scanned PDF needs OCR. Install requirements-ocr.txt and Tesseract.")
            yield index + 1, text, len(reader.pages)
    finally:
        if rendered:
            rendered.close()


def index_document(identifier):
    row = db.one("SELECT pdf,kb_id FROM documents WHERE id=? AND status='processing'", (identifier,))
    if not row:
        return
    parts = []
    total_pages = 0
    for page, text, total in extract_pages(row["pdf"]):
        total_pages = total
        parts.extend((page, chunk) for chunk in chunk_text(text))
        if len(parts) > settings.max_chunks:
            raise ValueError("PDF contains too many passages. Split it into smaller documents.")
        db.execute("UPDATE documents SET progress=?,pages=? WHERE id=?",
                   (int(page / total * 75), total, identifier))
    if not parts:
        raise ValueError("No readable text was found in this PDF.")
    vectors = []
    identity = None
    for start in range(0, len(parts), 32):
        batch, identity = embed([text for _, text in parts[start:start+32]])
        vectors.extend([None] * len(parts[start:start+32]) if batch is None else [v.tobytes() for v in batch])
    with db.connect() as conn:
        conn.execute("BEGIN IMMEDIATE")
        if not conn.execute("SELECT id FROM documents WHERE id=? AND status='processing'", (identifier,)).fetchone():
            return
        existing = conn.execute(
            "SELECT count(*) FROM chunks c JOIN documents d ON d.id=c.document_id WHERE d.kb_id=? AND d.id!=?",
            (row["kb_id"], identifier)).fetchone()[0]
        if existing + len(parts) > settings.max_chunks:
            raise ValueError("Knowledge base passage limit reached. Create another knowledge base.")
        conn.execute("DELETE FROM chunks WHERE document_id=?", (identifier,))
        conn.executemany("INSERT INTO chunks(document_id,page,text,vector,embedding_id) VALUES(?,?,?,?,?)",
                         [(identifier, page, text, vectors[i], identity) for i, (page, text) in enumerate(parts)])
        conn.execute("UPDATE documents SET status='ready',progress=100,error=NULL,pages=? WHERE id=?",
                     (total_pages, identifier))


if __name__ == "__main__":
    try:
        index_document(int(sys.argv[1]))
    except Exception as exc:
        # Only a short diagnostic is stored; document contents are not logged.
        db.execute("UPDATE documents SET status='failed',error=? WHERE id=?", (str(exc)[:500], int(sys.argv[1])))
        raise SystemExit(1)

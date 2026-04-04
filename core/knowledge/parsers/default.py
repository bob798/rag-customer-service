from core.interfaces import BaseChunker, BaseParser


class DefaultParser(BaseParser):
    """Default parser for PDF, Word, and plain text documents."""

    def __init__(self, chunker: BaseChunker) -> None:
        self.chunker = chunker

    def can_handle(self, file_type: str, content_hint: str = "") -> bool:
        return file_type in ("pdf", "docx", "txt", "text")

    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        file_type = file_path.rsplit(".", 1)[-1].lower()
        text = self._extract_text(file_path, file_type=file_type)
        return self.chunker.chunk(text, doc_id, metadata)

    def _extract_text(self, file_path: str, file_type: str) -> str:
        if file_type == "pdf":
            return self._extract_pdf(file_path)
        elif file_type == "docx":
            return self._extract_docx(file_path)
        else:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()

    def _extract_pdf(self, file_path: str) -> str:
        import fitz  # PyMuPDF — lazy import so tests can patch without module-level issues

        doc = fitz.open(file_path)
        pages = [page.get_text() for page in doc]
        doc.close()
        return "\n\n".join(pages)

    def _extract_docx(self, file_path: str) -> str:
        from docx import Document  # python-docx — lazy import

        doc = Document(file_path)
        return "\n\n".join(para.text for para in doc.paragraphs if para.text.strip())

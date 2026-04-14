"""DOCX parser with PaddleOCR support for images containing Chinese text.

Uses python-docx to extract text and tables directly (high accuracy),
and PaddleOCR PP-OCRv5 to OCR images embedded in the document.

Image-text position is preserved by iterating doc._element.body in
document order (same approach validated by RAGFlow).
"""
from __future__ import annotations

import io
import logging
import uuid

from core.interfaces import BaseChunker, BaseParser

logger = logging.getLogger(__name__)

# OOXML namespaces for XPath queries
_NSMAP = {
    "w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
    "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
    "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pic": "http://schemas.openxmlformats.org/drawingml/2006/picture",
}


class DocxParser(BaseParser):
    """Parses DOCX documents: text/tables via python-docx, image OCR via PaddleOCR.

    Produces typed chunks with content_type metadata:
      - text: paragraphs and headings -> sent to chunker
      - table: markdown tables -> atomic chunk
      - image: OCR'd text from embedded images -> atomic chunk
    """

    def __init__(self, chunker: BaseChunker, ocr_engine=None) -> None:
        """
        Args:
            chunker: text chunker for splitting long text segments.
            ocr_engine: optional pre-initialized PaddleOCR engine.
                        If None, lazily created on first image encounter.
        """
        self.chunker = chunker
        self._ocr_engine = ocr_engine

    def can_handle(self, file_type: str, content_hint: str = "") -> bool:
        return file_type == "docx"

    @staticmethod
    def is_available() -> bool:
        """Check if python-docx is installed."""
        try:
            import docx  # noqa: F401
            return True
        except ImportError:
            return False

    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        from docx import Document

        doc = Document(file_path)
        elements = self._walk_body(doc)
        return self._elements_to_chunks(elements, doc_id, metadata)

    # ------------------------------------------------------------------
    # Body traversal — preserves document order
    # ------------------------------------------------------------------

    def _walk_body(self, doc) -> list[dict]:
        """Walk doc body in XML order, yielding typed elements."""
        from docx.table import Table
        from docx.text.paragraph import Paragraph

        elements: list[dict] = []
        # Heading stack: [(level, text), ...] for building section paths
        heading_stack: list[tuple[int, str]] = []

        def _current_section() -> str:
            return " > ".join(t for _, t in heading_stack)

        for child in doc.element.body:
            tag = child.tag.split("}")[-1]

            if tag == "p":
                para = Paragraph(child, doc)

                # Update heading context with level-aware stack
                is_heading = (para.style and para.style.name
                              and para.style.name.startswith("Heading"))
                if is_heading:
                    heading_text = para.text.strip()
                    if heading_text:
                        # Extract level from style name: "Heading 1" -> 1
                        try:
                            level = int(para.style.name.split()[-1])
                        except (ValueError, IndexError):
                            level = 1
                        # Pop headings at same or deeper level
                        while heading_stack and heading_stack[-1][0] >= level:
                            heading_stack.pop()
                        heading_stack.append((level, heading_text))
                    section = _current_section()
                    elements.append({
                        "type": "heading",
                        "content": heading_text if heading_text else section,
                        "section": section,
                    })

                # Extract images from this paragraph (inline + floating)
                section = _current_section()
                images = self._extract_images_from_paragraph(para, doc)
                for img_blob, alt_text in images:
                    ocr_text = self._ocr_image(img_blob)
                    content = ocr_text if ocr_text else alt_text or "[图片]"
                    elements.append({
                        "type": "image",
                        "content": content,
                        "section": section,
                        "alt": alt_text,
                    })

                # Extract text
                text = para.text.strip()
                if text and not is_heading:
                    elements.append({
                        "type": "text",
                        "content": text,
                        "section": section,
                    })

            elif tag == "tbl":
                table = Table(child, doc)
                md = self._render_table_markdown(table)
                if md:
                    elements.append({
                        "type": "table",
                        "content": md,
                        "section": _current_section(),
                    })

        return elements

    # ------------------------------------------------------------------
    # Image extraction — inline + floating via XPath
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_images_from_paragraph(paragraph, doc) -> list[tuple[bytes, str]]:
        """Extract all image blobs from a paragraph (inline + floating).

        Returns list of (blob, alt_text) tuples.
        """
        images = []
        for pic in paragraph._element.findall(".//pic:pic", _NSMAP):
            # Get embed relationship ID
            blip = pic.find(".//a:blip", _NSMAP)
            if blip is None:
                continue
            embed = blip.get(f'{{{_NSMAP["r"]}}}embed')
            if not embed:
                continue

            try:
                related_part = doc.part.related_parts.get(embed)
                if related_part is None:
                    continue
                blob = related_part.image.blob
            except Exception:
                logger.debug("Failed to extract image blob for embed=%s", embed)
                continue

            # Get alt text from docPr — walk up from pic:pic to wp:inline/wp:anchor
            alt_text = ""
            ancestor = pic.getparent()
            for _ in range(5):  # walk up at most 5 levels
                if ancestor is None:
                    break
                doc_pr = ancestor.find(
                    "wp:docPr", {"wp": _NSMAP["wp"]}
                )
                if doc_pr is not None:
                    alt_text = doc_pr.get("descr", "") or doc_pr.get("name", "")
                    break
                ancestor = ancestor.getparent()

            images.append((blob, alt_text))

        return images

    # ------------------------------------------------------------------
    # PaddleOCR for image blobs
    # ------------------------------------------------------------------

    def _get_ocr_engine(self):
        """Lazy-load PaddleOCR engine."""
        if self._ocr_engine is None:
            try:
                from paddleocr import PaddleOCR
                self._ocr_engine = PaddleOCR(
                    use_textline_orientation=True, lang="ch",
                )
            except ImportError:
                logger.warning("paddleocr not installed, image OCR disabled")
                self._ocr_engine = False  # sentinel: tried and failed
        return self._ocr_engine

    # Maximum image size to OCR (pixels). Larger images are skipped.
    MAX_IMAGE_PIXELS = 20_000_000  # ~5000x4000

    def _ocr_image(self, blob: bytes) -> str:
        """Run PaddleOCR on an image blob, return recognized text."""
        engine = self._get_ocr_engine()
        if not engine:
            return ""

        try:
            import numpy as np
            from PIL import Image

            image = Image.open(io.BytesIO(blob)).convert("RGB")

            # Guard against huge images that could OOM
            if image.width * image.height > self.MAX_IMAGE_PIXELS:
                logger.warning(
                    "Skipping oversized image (%dx%d) for OCR",
                    image.width, image.height,
                )
                return ""

            img_array = np.array(image)

            # PaddleOCR 3.x: predict() accepts numpy array or file path
            result = engine.predict(img_array)

            lines = []
            # predict() returns a generator of OCRResult (dict subclass)
            for page_result in result:
                if not page_result:
                    continue
                rec_texts = page_result.get("rec_texts", [])
                for text in rec_texts:
                    if text and text.strip():
                        lines.append(text.strip())

            return "\n".join(lines)

        except Exception as e:
            logger.warning("OCR failed for image: %s", e)
            return ""

    # ------------------------------------------------------------------
    # Table rendering
    # ------------------------------------------------------------------

    @staticmethod
    def _render_table_markdown(table) -> str:
        """Render a python-docx Table as Markdown."""
        if not table.rows:
            return ""

        # Track vertically merged master cells to deduplicate across rows.
        # python-docx merge() can duplicate text in the master cell.
        seen_vmerge_text: set[str] = set()

        rows_data = []
        for row in table.rows:
            seen_tc = set()
            cells = []
            for cell in row.cells:
                tc_id = id(cell._tc)
                # Skip horizontally merged duplicates (same _tc in one row)
                if tc_id in seen_tc:
                    continue
                seen_tc.add(tc_id)

                tc_pr = cell._tc.tcPr
                has_vmerge = False
                is_restart = False
                if tc_pr is not None:
                    v_merge = tc_pr.find(f'{{{_NSMAP["w"]}}}vMerge')
                    if v_merge is not None:
                        has_vmerge = True
                        is_restart = v_merge.get(
                            f'{{{_NSMAP["w"]}}}val', ''
                        ) == 'restart'

                if has_vmerge and not is_restart:
                    # Pure continuation cell — empty placeholder
                    cells.append("")
                    continue

                text = cell.text.strip().replace("|", "\\|")

                if has_vmerge and is_restart:
                    # Master of vertical merge — deduplicate repeated lines
                    # (python-docx merge() concatenates text from merged cells)
                    lines = text.split("\n")
                    seen = set()
                    deduped = []
                    for line in lines:
                        stripped = line.strip()
                        if stripped and stripped not in seen:
                            seen.add(stripped)
                            deduped.append(stripped)
                    text = "\n".join(deduped)

                    # Skip if this exact text was already output in a previous row
                    if text in seen_vmerge_text:
                        cells.append("")
                        continue
                    seen_vmerge_text.add(text)

                cells.append(text)
            rows_data.append(cells)

        if not rows_data:
            return ""

        # Normalize column count
        max_cols = max(len(r) for r in rows_data)
        for row in rows_data:
            while len(row) < max_cols:
                row.append("")

        lines = []
        # Header row
        lines.append("| " + " | ".join(rows_data[0]) + " |")
        # Separator
        lines.append("| " + " | ".join(["---"] * max_cols) + " |")
        # Data rows
        for row in rows_data[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Elements -> chunks
    # ------------------------------------------------------------------

    def _elements_to_chunks(
        self,
        elements: list[dict],
        doc_id: str,
        metadata: dict,
    ) -> list[dict]:
        chunks: list[dict] = []

        # Merge consecutive text elements under the same section
        text_buffer: list[str] = []
        text_section = ""

        def flush_text():
            nonlocal text_buffer, text_section
            if text_buffer:
                merged = "\n\n".join(text_buffer)
                text_chunks = self.chunker.chunk(
                    merged, doc_id, {**metadata, "content_type": "text",
                                     "section": text_section, "page": None},
                )
                chunks.extend(text_chunks)
                text_buffer = []

        def _get_context(index: int) -> tuple[str, str]:
            """Gather context_above and context_below for non-text elements."""
            above_parts = []
            for j in range(index - 1, -1, -1):
                e = elements[j]
                if e["type"] == "text":
                    above_parts.insert(0, e["content"])
                    if len("\n".join(above_parts)) > 150:
                        break
                elif e["type"] == "heading":
                    above_parts.insert(0, e["content"])
                    break
                else:
                    break

            below_parts = []
            for j in range(index + 1, len(elements)):
                e = elements[j]
                if e["type"] == "text":
                    below_parts.append(e["content"])
                    if len("\n".join(below_parts)) > 150:
                        break
                elif e["type"] == "heading":
                    below_parts.append(e["content"])
                    break
                else:
                    break

            return "\n".join(above_parts), "\n".join(below_parts)

        for i, elem in enumerate(elements):
            etype = elem["type"]
            section = elem.get("section", "")

            if etype == "heading":
                flush_text()
                text_section = section
                continue

            if etype == "text":
                if section != text_section:
                    flush_text()
                    text_section = section
                text_buffer.append(elem["content"])
                continue

            # Non-text element: flush text buffer first
            flush_text()
            text_section = section

            # Gather surrounding text context
            ctx_above, ctx_below = _get_context(i)

            if etype == "table":
                parts = []
                if ctx_above:
                    parts.append(ctx_above)
                parts.append(f"[表格]\n{elem['content']}")
                if ctx_below:
                    parts.append(ctx_below)
                content = "\n\n".join(parts)
                chunks.append(self._make_chunk(content, doc_id, {
                    **metadata, "content_type": "table",
                    "section": section, "page": None,
                }))

            elif etype == "image":
                parts = []
                if ctx_above:
                    parts.append(ctx_above)
                parts.append(f"[图片] {elem['content']}")
                if ctx_below:
                    parts.append(ctx_below)
                content = "\n\n".join(parts)
                chunks.append(self._make_chunk(content, doc_id, {
                    **metadata, "content_type": "image",
                    "section": section, "page": None,
                    "alt_text": elem.get("alt", ""),
                }))

        flush_text()

        # Re-index
        for idx, chunk in enumerate(chunks):
            chunk["metadata"]["chunk_index"] = idx

        return chunks

    @staticmethod
    def _make_chunk(content: str, doc_id: str, metadata: dict) -> dict:
        return {
            "chunk_id": str(uuid.uuid4()),
            "doc_id": doc_id,
            "content": content,
            "metadata": {**metadata, "chunk_index": 0},
        }

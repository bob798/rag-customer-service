"""PaddleOCR PP-StructureV3 based document parser.

Uses PaddleOCR 3.x to parse PDF into structured Markdown, then extracts
typed segments (text/table/image/formula) for chunking.

Requires: `pip install paddleocr`
No torch dependency — uses PaddlePaddle framework.
"""
from __future__ import annotations

import re
import uuid
from pathlib import Path
from typing import Optional

from core.interfaces import BaseChunker, BaseParser


class PaddleOCRParser(BaseParser):
    """Parses PDF documents using PaddleOCR PP-StructureV3.

    Produces typed chunks with content_type metadata:
      - text: regular paragraphs → sent to chunker
      - table: markdown tables → atomic chunk (not split)
      - image: image references → atomic chunk
      - formula: LaTeX formulas → atomic chunk
      - heading: tracked for section path, not stored as chunk
    """

    def __init__(
        self,
        chunker: BaseChunker,
        device: str = "cpu",
    ) -> None:
        self.chunker = chunker
        self.device = device
        self._engine = None

    def can_handle(self, file_type: str, content_hint: str = "") -> bool:
        return file_type in ("pdf",)

    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        markdown = self._run_paddleocr(file_path)
        segments = self._parse_markdown(markdown)
        section_paths = self._build_section_paths(segments)
        return self._segments_to_chunks(segments, section_paths, doc_id, metadata)

    # ------------------------------------------------------------------
    # PaddleOCR invocation
    # ------------------------------------------------------------------

    def _get_engine(self):
        """Lazy-load PaddleOCR engine."""
        if self._engine is None:
            import os
            os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
            from paddleocr import PaddleOCR
            self._engine = PaddleOCR(
                use_doc_orientation_classify=False,
                use_doc_unwarping=False,
                use_textline_orientation=False,
                device=self.device,
            )
        return self._engine

    def _run_paddleocr(self, file_path: str) -> str:
        """Run PaddleOCR on a PDF and return markdown string."""
        engine = self._get_engine()
        result = engine.predict(file_path, return_markdown=True)

        # PaddleOCR returns list of page results
        # Each page result contains markdown text
        md_parts = []
        for page_result in result:
            if hasattr(page_result, "markdown") and page_result.markdown:
                md_parts.append(page_result.markdown)
            elif isinstance(page_result, dict) and "markdown" in page_result:
                md_parts.append(page_result["markdown"])
            elif isinstance(page_result, str):
                md_parts.append(page_result)

        return "\n\n".join(md_parts)

    # ------------------------------------------------------------------
    # Markdown → typed segments
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_markdown(markdown: str) -> list[dict]:
        """Parse PaddleOCR markdown output into typed segments.

        Returns: [{"type": str, "content": str, "level": int|None}]
        """
        segments: list[dict] = []
        current_text: list[str] = []
        in_table = False
        table_lines: list[str] = []

        def flush_text():
            if current_text:
                text = "\n".join(current_text).strip()
                if text:
                    segments.append({"type": "text", "content": text, "level": None})
                current_text.clear()

        def flush_table():
            nonlocal in_table
            if table_lines:
                segments.append({"type": "table", "content": "\n".join(table_lines), "level": None})
                table_lines.clear()
            in_table = False

        for line in markdown.split("\n"):
            stripped = line.strip()

            # Heading
            heading_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if heading_match:
                flush_text()
                flush_table()
                level = len(heading_match.group(1))
                segments.append({"type": "heading", "content": heading_match.group(2), "level": level})
                continue

            # Table line (starts with | or is a separator like |---|)
            if stripped.startswith("|") or re.match(r'^\|[\s\-:|]+\|$', stripped):
                flush_text()
                in_table = True
                table_lines.append(stripped)
                continue

            # End of table (non-table line after table)
            if in_table and not stripped.startswith("|"):
                flush_table()

            # Image — standard markdown: ![alt](path)
            img_match = re.match(r'!\[([^\]]*)\]\(([^)]+)\)', stripped)
            if img_match:
                flush_text()
                alt = img_match.group(1)
                path = img_match.group(2)
                segments.append({
                    "type": "image",
                    "content": alt if alt else "[图片]",
                    "level": None,
                    "image_path": path,
                })
                continue

            # Image — HTML format from PaddleOCR: <div...><img src="..." .../></div>
            html_img_match = re.search(r'<img\s+[^>]*src="([^"]+)"[^>]*/?\s*>', stripped)
            if html_img_match and stripped.startswith("<div") and stripped.endswith("</div>"):
                flush_text()
                path = html_img_match.group(1)
                alt_match = re.search(r'alt="([^"]*)"', stripped)
                alt = alt_match.group(1) if alt_match else ""
                segments.append({
                    "type": "image",
                    "content": alt if alt and alt != "Image" else "[图片]",
                    "level": None,
                    "image_path": path,
                })
                continue

            # Formula block ($$...$$)
            if stripped.startswith("$$") and stripped.endswith("$$") and len(stripped) > 4:
                flush_text()
                segments.append({"type": "formula", "content": stripped[2:-2].strip(), "level": None})
                continue

            # HTML table (<table>...</table>)
            if "<table" in stripped.lower():
                flush_text()
                # Accumulate until </table>
                html_buf = [stripped]
                # Single-line HTML table
                if "</table>" in stripped.lower():
                    segments.append({"type": "table", "content": stripped, "level": None})
                    continue
                # Multi-line — this case is handled by the caller accumulating
                # For simplicity, treat as text (PaddleOCR typically outputs markdown tables, not HTML)
                current_text.append(stripped)
                continue

            # Regular text
            current_text.append(line)

        # Flush remaining
        flush_text()
        flush_table()

        return segments

    # ------------------------------------------------------------------
    # Section path tracking (reused from MinerUParser pattern)
    # ------------------------------------------------------------------

    @staticmethod
    def _build_section_paths(segments: list[dict]) -> list[str]:
        """Compute heading hierarchy path for each segment."""
        section_stack: list[tuple[int, str]] = []
        paths: list[str] = []

        for seg in segments:
            if seg["type"] == "heading" and seg.get("level"):
                level = seg["level"]
                title = seg["content"].strip()
                while section_stack and section_stack[-1][0] >= level:
                    section_stack.pop()
                section_stack.append((level, title))

            path = " > ".join(t for _, t in section_stack)
            paths.append(path)

        return paths

    # ------------------------------------------------------------------
    # Segments → chunks
    # ------------------------------------------------------------------

    def _segments_to_chunks(
        self,
        segments: list[dict],
        section_paths: list[str],
        doc_id: str,
        metadata: dict,
    ) -> list[dict]:
        chunks: list[dict] = []

        for i, seg in enumerate(segments):
            seg_type = seg["type"]
            base_meta = {
                **metadata,
                "page": None,  # PaddleOCR markdown doesn't have page markers
                "section": section_paths[i] if i < len(section_paths) else None,
            }

            if seg_type == "text":
                text = seg["content"]
                if text:
                    text_chunks = self.chunker.chunk(
                        text, doc_id, {**base_meta, "content_type": "text"},
                    )
                    chunks.extend(text_chunks)

            elif seg_type == "heading":
                # Captured in section_paths, not stored as chunk
                pass

            elif seg_type == "table":
                content = f"[表格]\n{seg['content']}"
                chunks.append(self._make_chunk(content, doc_id, {
                    **base_meta, "content_type": "table",
                }))

            elif seg_type == "image":
                content = f"[图片] {seg['content']}"
                chunks.append(self._make_chunk(content, doc_id, {
                    **base_meta,
                    "content_type": "image",
                    "image_path": seg.get("image_path"),
                }))

            elif seg_type == "formula":
                content = f"[公式] {seg['content']}"
                chunks.append(self._make_chunk(content, doc_id, {
                    **base_meta, "content_type": "formula",
                }))

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

    # ------------------------------------------------------------------
    # Availability check
    # ------------------------------------------------------------------

    @staticmethod
    def is_available() -> bool:
        """Check if paddleocr is installed."""
        try:
            import paddleocr  # noqa: F401
            return True
        except ImportError:
            return False

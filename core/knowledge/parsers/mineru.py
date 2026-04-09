"""MinerU-based document parser for high-quality PDF extraction.

Uses MinerU CLI to produce structured content_list.json, then processes
each element by type (text/table/image/formula/code) into chunks.

Requires: `mineru` CLI installed (`uv pip install -U "mineru[all]"`).
Falls back to DefaultParser when MinerU is unavailable.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import uuid
from pathlib import Path

from core.interfaces import BaseChunker, BaseParser


class MinerUParser(BaseParser):
    """Parses documents via MinerU CLI, producing typed chunks with rich metadata."""

    def __init__(
        self,
        chunker: BaseChunker,
        output_dir: str = "./data/mineru_output",
    ) -> None:
        self.chunker = chunker
        self.output_dir = Path(output_dir)

    def can_handle(self, file_type: str, content_hint: str = "") -> bool:
        return file_type in ("pdf",)

    def parse(self, file_path: str, doc_id: str, metadata: dict) -> list[dict]:
        content_list = self._run_mineru(file_path)
        section_paths = self._build_section_paths(content_list)
        return self._content_list_to_chunks(content_list, section_paths, doc_id, metadata)

    # ------------------------------------------------------------------
    # MinerU invocation
    # ------------------------------------------------------------------

    def _run_mineru(self, file_path: str) -> list[dict]:
        """Call MinerU CLI and return parsed content_list."""
        stem = Path(file_path).stem
        out_dir = self.output_dir / stem
        out_dir.mkdir(parents=True, exist_ok=True)

        result = subprocess.run(
            [
                "mineru",
                "-p", str(file_path),
                "-o", str(out_dir),
                "-b", "pipeline",
            ],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(f"MinerU CLI failed (exit {result.returncode}): {result.stderr[:500]}")

        # MinerU outputs: out_dir/<stem>/<stem>_content_list.json
        cl_candidates = list(out_dir.rglob("*_content_list.json"))
        if not cl_candidates:
            # Fallback: try content_list_v2.json
            cl_candidates = list(out_dir.rglob("*_content_list_v2.json"))
        if not cl_candidates:
            raise RuntimeError(f"MinerU produced no content_list in {out_dir}")

        with open(cl_candidates[0], "r", encoding="utf-8") as f:
            return json.load(f)

    # ------------------------------------------------------------------
    # Section path tracking
    # ------------------------------------------------------------------

    @staticmethod
    def _build_section_paths(content_list: list[dict]) -> list[str]:
        """Compute the heading hierarchy path for each element."""
        section_stack: list[tuple[int, str]] = []
        paths: list[str] = []

        for item in content_list:
            if item.get("type") == "text" and item.get("text_level", 0) > 0:
                level = item["text_level"]
                title = item.get("text", "").strip()
                # Pop same-level and lower headings
                while section_stack and section_stack[-1][0] >= level:
                    section_stack.pop()
                section_stack.append((level, title))

            path = " > ".join(t for _, t in section_stack)
            paths.append(path)

        return paths

    # ------------------------------------------------------------------
    # Content list → chunks
    # ------------------------------------------------------------------

    def _content_list_to_chunks(
        self,
        content_list: list[dict],
        section_paths: list[str],
        doc_id: str,
        metadata: dict,
    ) -> list[dict]:
        chunks: list[dict] = []

        for i, item in enumerate(content_list):
            item_type = item.get("type", "")
            base_meta = {
                **metadata,
                "page": item.get("page_idx"),
                "section": section_paths[i] if i < len(section_paths) else None,
                "bbox": item.get("bbox"),
            }

            if item_type == "text" and item.get("text_level", 0) == 0:
                text = item.get("text", "").strip()
                if text:
                    text_chunks = self.chunker.chunk(
                        text, doc_id, {**base_meta, "content_type": "text"},
                    )
                    chunks.extend(text_chunks)

            elif item_type == "text" and item.get("text_level", 0) > 0:
                # Headings are captured in section_paths, not stored as chunks
                pass

            elif item_type == "table":
                caption = " ".join(item.get("table_caption", []))
                footnote = " ".join(item.get("table_footnote", []))
                html = item.get("table_body", "")
                content = f"[表格] {caption}\n{html}" if caption else f"[表格]\n{html}"
                if footnote:
                    content += f"\n注：{footnote}"
                chunks.append(self._make_chunk(content, doc_id, {
                    **base_meta,
                    "content_type": "table",
                    "table_caption": caption,
                }))

            elif item_type == "image":
                caption = " ".join(item.get("image_caption", []))
                content = f"[图片] {caption}" if caption else "[图片]"
                chunks.append(self._make_chunk(content, doc_id, {
                    **base_meta,
                    "content_type": "image",
                    "image_path": item.get("img_path"),
                }))

            elif item_type == "equation":
                latex = item.get("text", "")
                content = f"[公式] {latex}"
                chunks.append(self._make_chunk(content, doc_id, {
                    **base_meta,
                    "content_type": "formula",
                }))

            elif item_type == "code":
                code = item.get("code_body", "")
                code_caption = " ".join(item.get("code_caption", []))
                content = f"[代码] {code_caption}\n{code}" if code_caption else f"[代码]\n{code}"
                chunks.append(self._make_chunk(content, doc_id, {
                    **base_meta,
                    "content_type": "code",
                }))

            elif item_type == "list":
                items = item.get("list_items", [])
                text = "\n".join(items) if items else item.get("text", "")
                if text:
                    text_chunks = self.chunker.chunk(
                        text, doc_id, {**base_meta, "content_type": "text"},
                    )
                    chunks.extend(text_chunks)

            # header/footer/page_number/aside_text → discard

        # Re-index chunk_index across all chunks
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
    # Utility: check if MinerU CLI is available
    # ------------------------------------------------------------------

    @staticmethod
    def is_available() -> bool:
        """Check if MinerU CLI is installed and accessible."""
        return shutil.which("mineru") is not None

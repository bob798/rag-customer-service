"""生成测试用 DOCX 文件 — 包含文本、表格、带中文文字的图片。

用于 DocxParser 冒烟测试：验证真实 python-docx 解析 + PaddleOCR 图片 OCR。
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def create_chinese_text_image(text: str, filename: str) -> str:
    """用 PIL 生成一张包含中文文字的图片。"""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (400, 80), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Try to find a Chinese font
    font = None
    font_paths = [
        "/System/Library/Fonts/PingFang.ttc",           # macOS
        "/System/Library/Fonts/STHeiti Medium.ttc",      # macOS fallback
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",  # Linux
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    ]
    for fp in font_paths:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, 28)
                break
            except Exception:
                continue

    if font is None:
        # Fallback: default font (may not render Chinese well)
        font = ImageFont.load_default()
        print(f"  [警告] 未找到中文字体，使用默认字体（中文可能显示为方块）")

    draw.text((20, 20), text, fill=(0, 0, 0), font=font)

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    out_path = Path(__file__).parent.parent / "tests" / "data" / "docx" / "images" / filename
    out_path.write_bytes(buf.getvalue())
    print(f"  生成图片: {out_path.name} ({len(buf.getvalue())} bytes)")
    return str(out_path)


def create_test_docx():
    """生成测试 DOCX 文件。"""
    from docx import Document
    from docx.shared import Inches

    doc = Document()

    # 1. 标题
    doc.add_heading("BLV-D1 蓝牙功放说明书", level=1)

    # 2. 正文段落
    doc.add_paragraph(
        "BLV-D1 是一款高性能蓝牙数字功放，支持蓝牙 5.0 和 USB 音频输入。"
        "适用于家庭影院、桌面音箱等场景。"
    )

    # 3. 二级标题 + 表格
    doc.add_heading("技术规格", level=2)
    doc.add_paragraph("以下是 BLV-D1 的主要技术参数：")

    table = doc.add_table(rows=5, cols=2, style="Table Grid")
    specs = [
        ("参数", "规格"),
        ("输出功率", "50W × 2"),
        ("输入电压", "DC 12-24V"),
        ("蓝牙版本", "5.0"),
        ("信噪比", "≥95dB"),
    ]
    for i, (k, v) in enumerate(specs):
        table.rows[i].cells[0].text = k
        table.rows[i].cells[1].text = v

    # 4. 带中文文字的图片
    doc.add_heading("产品外观", level=2)
    doc.add_paragraph("下图展示了产品面板上的标识信息：")

    img_path = create_chinese_text_image(
        "BLV-D1 蓝牙功放 50W",
        "test_label_image.png",
    )
    doc.add_picture(img_path, width=Inches(3.5))

    # 5. 另一张带中文的图片
    doc.add_heading("安装步骤", level=2)
    doc.add_paragraph("请按照以下步骤完成安装：")

    img_path2 = create_chinese_text_image(
        "步骤一 连接电源 DC 12V",
        "test_step_image.png",
    )
    doc.add_picture(img_path2, width=Inches(3.5))

    doc.add_paragraph("连接完成后，蓝色指示灯将亮起，表示设备已就绪。")

    # 6. 更多文本
    doc.add_heading("常见问题", level=2)
    doc.add_paragraph("问：设备无法开机怎么办？")
    doc.add_paragraph("答：请检查电源适配器是否连接正确，确认输入电压在 12-24V 范围内。")

    # 保存
    out_path = Path(__file__).parent.parent / "tests" / "data" / "docx" / "功放说明书.docx"
    doc.save(str(out_path))
    print(f"\n生成测试文档: {out_path}")
    print(f"  内容: 标题 + 2段文本 + 1个表格(5行2列) + 2张带中文图片 + FAQ")


if __name__ == "__main__":
    create_test_docx()

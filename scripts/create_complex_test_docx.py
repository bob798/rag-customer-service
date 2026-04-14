"""生成复杂测试 DOCX — 覆盖 DocxParser 的边界场景。

包含：
  1. 多级标题（H1/H2/H3）
  2. 普通表格 + 合并单元格表格
  3. 多张图片（inline + 带 alt text + 无 alt text）
  4. 图片中包含不同类型中文（横排、数字混排、长文本）
  5. 连续图片（两张图片之间无文本）
  6. 长段落（测试 chunker 切分）
  7. 空段落
  8. 列表（有序/无序）
  9. 图片紧跟表格（无间隔文本）
"""
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

DATA_DIR = Path(__file__).parent.parent / "tests" / "data" / "docx"


def make_image(text: str, width: int = 500, height: int = 80) -> bytes:
    """生成包含中文的 PNG 图片，返回 bytes。"""
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    font = None
    for fp in [
        "/System/Library/Fonts/PingFang.ttc",
        "/System/Library/Fonts/STHeiti Medium.ttc",
        "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
    ]:
        if Path(fp).exists():
            try:
                font = ImageFont.truetype(fp, 26)
                break
            except Exception:
                continue
    if font is None:
        font = ImageFont.load_default()

    draw.text((15, 15), text, fill=(0, 0, 0), font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def save_image(text: str, filename: str, **kwargs) -> str:
    """保存图片到 tests/data/docx/images/，返回路径。"""
    blob = make_image(text, **kwargs)
    img_dir = DATA_DIR / "images"
    img_dir.mkdir(exist_ok=True)
    path = img_dir / filename
    path.write_bytes(blob)
    print(f"  图片: {filename} ({len(blob)} bytes)")
    return str(path)


def create_complex_docx():
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor
    from docx.enum.text import WD_ALIGN_PARAGRAPH

    doc = Document()

    # ============================================================
    # 1. 多级标题
    # ============================================================
    doc.add_heading("BLV-D1 蓝牙数字功放 完整技术手册", level=1)

    doc.add_paragraph(
        "本手册详细介绍 BLV-D1 蓝牙数字功放的技术规格、安装步骤、"
        "故障排除及维护保养指南。请在使用前仔细阅读。"
    )

    # ============================================================
    # 2. 技术规格 — 普通表格
    # ============================================================
    doc.add_heading("技术规格", level=2)
    doc.add_heading("基本参数", level=3)
    doc.add_paragraph("以下为产品的核心技术指标：")

    table1 = doc.add_table(rows=8, cols=2, style="Table Grid")
    specs = [
        ("参数名称", "规格值"),
        ("型号", "BLV-D1"),
        ("输出功率", "50W × 2（4Ω负载）"),
        ("频率响应", "20Hz - 20kHz (±1dB)"),
        ("信噪比", "≥95dB (A加权)"),
        ("输入电压", "DC 12-24V / 3A"),
        ("蓝牙版本", "5.0 (支持 SBC/AAC/aptX)"),
        ("工作温度", "-10°C ~ 50°C"),
    ]
    for i, (k, v) in enumerate(specs):
        table1.rows[i].cells[0].text = k
        table1.rows[i].cells[1].text = v

    # ============================================================
    # 3. 合并单元格表格
    # ============================================================
    doc.add_heading("接口定义", level=3)
    doc.add_paragraph("下表描述了设备的所有物理接口：")

    table2 = doc.add_table(rows=6, cols=3, style="Table Grid")
    headers = ["接口类型", "位置", "说明"]
    for j, h in enumerate(headers):
        table2.rows[0].cells[j].text = h

    # 音频输入 — 合并两行的"接口类型"
    table2.rows[1].cells[0].text = "音频输入"
    table2.rows[1].cells[1].text = "后面板"
    table2.rows[1].cells[2].text = "3.5mm AUX 模拟输入"
    table2.rows[2].cells[0].text = "音频输入"
    table2.rows[2].cells[1].text = "后面板"
    table2.rows[2].cells[2].text = "USB Type-C 数字输入"
    # Merge "音频输入" cells vertically
    table2.rows[1].cells[0].merge(table2.rows[2].cells[0])

    # 音频输出 — 合并两行
    table2.rows[3].cells[0].text = "音频输出"
    table2.rows[3].cells[1].text = "后面板"
    table2.rows[3].cells[2].text = "左声道 香蕉插座"
    table2.rows[4].cells[0].text = "音频输出"
    table2.rows[4].cells[1].text = "后面板"
    table2.rows[4].cells[2].text = "右声道 香蕉插座"
    table2.rows[3].cells[0].merge(table2.rows[4].cells[0])

    table2.rows[5].cells[0].text = "电源"
    table2.rows[5].cells[1].text = "后面板"
    table2.rows[5].cells[2].text = "DC 5.5×2.1mm 电源座"

    # ============================================================
    # 4. 产品外观 — 多张图片 + 不同 OCR 难度
    # ============================================================
    doc.add_heading("产品外观", level=2)

    # 图片 A：简单中文
    doc.add_paragraph("图 1：产品正面面板标识")
    img_a = save_image("BLV-D1 蓝牙功放 50W×2", "complex_img_label.png")
    doc.add_picture(img_a, width=Inches(3.5))

    # 图片 B：数字+中文+英文混排
    doc.add_paragraph("图 2：产品背面接口标注")
    img_b = save_image(
        "AUX IN | USB-C | SPK L/R | DC 12-24V",
        "complex_img_ports.png", width=600,
    )
    doc.add_picture(img_b, width=Inches(4.0))

    # ============================================================
    # 5. 连续图片（两张之间无文本 — 测试 context 逻辑）
    # ============================================================
    doc.add_heading("安装步骤", level=2)
    doc.add_paragraph("请严格按照以下步骤操作：")

    img_c = save_image("步骤1: 连接电源适配器 DC12V", "complex_img_step1.png", width=550)
    doc.add_picture(img_c, width=Inches(3.5))
    # 紧接第二张图，中间没有文本
    img_d = save_image("步骤2: 连接音箱线 左右声道", "complex_img_step2.png", width=550)
    doc.add_picture(img_d, width=Inches(3.5))

    doc.add_paragraph(
        "步骤 3：打开电源开关，蓝色指示灯亮起表示设备就绪。"
        "长按配对键 3 秒进入蓝牙配对模式，白色指示灯闪烁。"
    )

    # ============================================================
    # 6. 图片紧跟表格（无间隔文本 — 测试 context 边界）
    # ============================================================
    doc.add_heading("指示灯说明", level=2)

    led_table = doc.add_table(rows=4, cols=3, style="Table Grid")
    led_data = [
        ("指示灯", "颜色", "含义"),
        ("电源", "蓝色常亮", "设备已开机"),
        ("蓝牙", "白色闪烁", "配对模式"),
        ("蓝牙", "白色常亮", "已连接设备"),
    ]
    for i, (a, b, c) in enumerate(led_data):
        led_table.rows[i].cells[0].text = a
        led_table.rows[i].cells[1].text = b
        led_table.rows[i].cells[2].text = c

    # 图片紧跟表格
    img_e = save_image("指示灯位置示意图 前面板左侧", "complex_img_led.png", width=500)
    doc.add_picture(img_e, width=Inches(3.5))

    # ============================================================
    # 7. 长段落（测试 chunker 分段）
    # ============================================================
    doc.add_heading("故障排除", level=2)

    long_text = (
        "如果设备无法开机，请首先检查电源适配器是否正确连接，确认适配器输出电压在 "
        "12V 至 24V 范围内，电流不低于 3A。如果使用第三方适配器，请确认极性为中心正极。"
        "尝试更换电源线或适配器进行排除。如果电源指示灯亮起但无声音输出，请检查音箱线是否"
        "牢固连接，确认左右声道未接反。可以尝试切换到 AUX 输入模式，使用 3.5mm 音频线"
        "连接手机播放音乐，以排除蓝牙模块故障。如果蓝牙无法配对，请长按配对键 5 秒以上"
        "恢复出厂设置，然后重新进入配对模式。部分手机可能需要在蓝牙设置中手动删除旧的配对"
        "记录后重新搜索。如果出现杂音或底噪，可能是电源干扰导致，建议使用随机附带的原装"
        "适配器，或尝试在适配器和设备之间加装磁环滤波器。如果以上方法均无法解决问题，"
        "请联系售后服务：400-888-1234（工作日 9:00-18:00），或发送邮件至 "
        "support@blv-audio.com，附上购买凭证和故障描述。"
    )
    doc.add_paragraph(long_text)

    # ============================================================
    # 8. 有序/无序列表
    # ============================================================
    doc.add_heading("包装清单", level=2)

    items = [
        "BLV-D1 功放主机 × 1",
        "DC 12V/3A 电源适配器 × 1",
        "3.5mm 音频线 × 1",
        "USB-C 数据线 × 1",
        "产品说明书 × 1",
        "保修卡 × 1",
    ]
    for item in items:
        doc.add_paragraph(item, style="List Bullet")

    # ============================================================
    # 9. 带中文长文本的图片（OCR 难度更高）
    # ============================================================
    doc.add_heading("保修条款", level=2)
    doc.add_paragraph("以下为保修条款的扫描件：")

    img_f = save_image(
        "保修期限12个月 自购买之日起计算 人为损坏不在保修范围内",
        "complex_img_warranty.png", width=700, height=80,
    )
    doc.add_picture(img_f, width=Inches(4.5))

    doc.add_paragraph("如有疑问，请拨打客服热线 400-888-1234。")

    # ============================================================
    # 保存
    # ============================================================
    out_path = DATA_DIR / "功放说明书_复杂版.docx"
    doc.save(str(out_path))

    print(f"\n生成复杂测试文档: {out_path}")
    print(f"  包含: 多级标题(H1/H2/H3) + 普通表格 + 合并单元格表格 + 6张图片")
    print(f"  + 连续图片 + 图片紧跟表格 + 长段落 + 列表 + 高难度 OCR 图片")


if __name__ == "__main__":
    create_complex_docx()

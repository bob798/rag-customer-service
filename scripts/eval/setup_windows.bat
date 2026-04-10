@echo off
REM PaddleOCR 评测环境快速搭建（Windows）
REM 用法：双击运行或在 cmd 中执行

echo ========================================
echo   PaddleOCR 评测环境搭建
echo ========================================

REM 检查 Python
python --version 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10-3.12.
    pause
    exit /b 1
)

REM 创建虚拟环境（如果不存在）
if not exist .venv (
    echo Creating virtual environment...
    python -m venv .venv
)

echo Activating venv...
call .venv\Scripts\activate.bat

echo Installing dependencies...
pip install --upgrade pip
pip install paddleocr paddlepaddle
pip install PyMuPDF python-docx jieba rank_bm25 chromadb sentence-transformers FlagEmbedding

echo.
echo ========================================
echo   Setup complete! Run:
echo   .venv\Scripts\python scripts\eval\eval_paddleocr_parsing.py
echo ========================================
pause

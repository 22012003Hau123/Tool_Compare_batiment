@echo off
echo ========================================
echo Tool Compare - Launcher
echo ========================================
echo.

REM Kiểm tra Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python chua duoc cai dat!
    echo Vui long cai dat Python tu: https://www.python.org/downloads/
    pause
    exit /b 1
)

echo Dang kiem tra va cai dat dependencies...
echo.

REM Cài đặt dependencies
python -m pip install --quiet --upgrade pip
python -m pip install --quiet PyMuPDF openai tkinterdnd2

if errorlevel 1 (
    echo.
    echo ERROR: Khong the cai dat dependencies!
    echo Vui long chay thu cong: pip install PyMuPDF openai tkinterdnd2
    pause
    exit /b 1
)

echo.
echo ========================================
echo Dang khoi dong Tool Compare...
echo ========================================
echo.

python tool_compare_app.py

if errorlevel 1 (
    echo.
    echo ERROR: Co loi xay ra khi chay ung dung!
    pause
)


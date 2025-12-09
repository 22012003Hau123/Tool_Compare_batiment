@echo off
echo ========================================
echo Tool Compare - Cai dat Dependencies
echo ========================================
echo.

REM Kiểm tra Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python chua duoc cai dat!
    echo.
    echo Vui long:
    echo 1. Tai Python tu: https://www.python.org/downloads/
    echo 2. Khi cai dat, NHO TICK vao "Add Python to PATH"
    echo 3. Chay lai file nay
    echo.
    pause
    exit /b 1
)

echo Python da duoc cai dat!
python --version
echo.

echo Dang cai dat cac thu vien can thiet...
echo.

python -m pip install --upgrade pip
python -m pip install PyMuPDF openai tkinterdnd2

if errorlevel 1 (
    echo.
    echo ERROR: Co loi khi cai dat!
    pause
    exit /b 1
)

echo.
echo ========================================
echo CAI DAT THANH CONG!
echo ========================================
echo.
echo Ban co the chay ung dung bang cach:
echo - Double-click vao file "run.bat"
echo - Hoac chay: python tool_compare_app.py
echo.
pause


@echo off
cd /d "%~dp0"
echo ============================================================
echo   Setting up dedicated Python 3.12 virtual environment...
echo ============================================================
echo.

py --list
echo.

py -3.12 -m venv venv312
if errorlevel 1 (
    echo [ERROR] Python 3.12 was not found by the 'py' launcher.
    echo Please download and install Python 3.12 from:
    echo https://www.python.org/downloads/release/python-3120/
    echo (Make sure to check "Add Python to PATH" during installation)
    pause
    exit /b 1
)

call "%~dp0venv312\Scripts\activate.bat"

echo.
echo Installing pre-built binary dependencies into venv312...
pip install "PyMuPDF>=1.24.0" "rapidocr-onnxruntime==1.2.3" "numpy>=1.24.0,<2.0.0"
pip install -r requirements.txt

echo.
echo ============================================================
echo   Verifying installation inside venv312:
echo ============================================================
python -c "import fitz, rapidocr_onnxruntime, numpy; print('All OK, numpy', numpy.__version__)"

echo.
echo ============================================================
echo   Virtual environment setup complete!
echo ============================================================

@echo off
title Invoice Extractor
cd /d "%~dp0"

REM --- Activate Python 3.12 virtual environment ---
if exist "%~dp0venv312\Scripts\activate.bat" (
    call "%~dp0venv312\Scripts\activate.bat"
)

REM --- stop Streamlit's first-run "enter your email" question, once and for all ---
if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
  > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
  >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

REM --- Verify OCR dependencies on Windows ---
python -c "import fitz, rapidocr_onnxruntime" >nul 2>&1
if errorlevel 1 (
    echo.
    echo [NOTICE] OCR packages missing or incomplete. Installing/Updating dependencies...
    pip install "PyMuPDF>=1.24.0" "rapidocr-onnxruntime>=1.2.0,<1.3.0" "numpy>=1.24.0,<2.0.0"
    if errorlevel 1 (
        echo [ERROR] Failed to install OCR dependencies. Please check network or pip permissions.
        pause
        exit /b 1
    )
    echo [SUCCESS] OCR dependencies verified and installed successfully.
    echo.
)


echo ============================================================
echo   Invoice Extractor is starting...
echo   A browser tab will open automatically in a few seconds.
echo   Leave this black window open while you use the tool.
echo   To quit: close the browser tab, then close this window.
echo ============================================================
echo.

python -m streamlit run app.py
if errorlevel 1 (
  echo.
  echo Trying the alternate Python launcher...
  py -m streamlit run app.py
)

echo.
echo The app has stopped. You can close this window.
pause

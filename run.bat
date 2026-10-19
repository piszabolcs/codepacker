@echo off
rem this starts the app from source, handy during development
rem if you already have an exe, use that instead

cd /d "%~dp0"

rem use the project's virtual environment when there is one, otherwise the python on PATH
set "PYTHON_DIR="
if exist ".venv\Scripts\pythonw.exe" set "PYTHON_DIR=.venv\Scripts\"

rem pythonw is the silent variant, it doesn't open a black console window
"%PYTHON_DIR%pythonw" main.py 2>nul
if %errorlevel% equ 0 goto end

"%PYTHON_DIR%python" main.py
if %errorlevel% equ 0 goto end

echo.
echo Could not start the app.
echo Set up the virtual environment once, then run this again:
echo    py -3.12 -m venv .venv
echo    .venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
pause

:end

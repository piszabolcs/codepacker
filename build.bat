@echo off
rem this builds a standalone exe from the app, with the project's virtual environment
rem (nothing is installed globally: the pinned tools come from requirements-dev.txt)

cd /d "%~dp0"

echo ============================================
echo   CodePacker - building the exe
echo ============================================
echo.

if not exist ".venv\Scripts\python.exe" (
    echo The virtual environment is missing. Create it once with:
    echo    py -3.12 -m venv .venv
    echo    .venv\Scripts\python.exe -m pip install -r requirements-dev.txt
    pause
    exit /b 1
)

echo [1/3] checking dependencies...
".venv\Scripts\python.exe" -m pip install -r requirements-dev.txt
if %errorlevel% neq 0 (
    echo.
    echo Failed to install the dependencies.
    pause
    exit /b 1
)

echo.
echo [2/3] removing the old build...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo.
echo [3/3] building the exe, this can take a couple of minutes...
".venv\Scripts\pyinstaller.exe" codepacker.spec --noconfirm
if %errorlevel% neq 0 (
    echo.
    echo The build failed, check the error message above.
    pause
    exit /b 1
)

echo.
echo ============================================
echo   DONE
echo   the exe is here: dist\CodePacker.exe
echo ============================================
echo.

rem open the dist folder so you can see it right away
if exist dist explorer dist

pause

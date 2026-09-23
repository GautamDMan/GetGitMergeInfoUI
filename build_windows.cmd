@echo off
setlocal EnableExtensions EnableDelayedExpansion

REM ============================================================
REM GetGitMergeInfoUI - Windows EXE Builder
REM ============================================================

set "APP_NAME=GetGitMergeInfoUI"
set "ENTRY_POINT=app.py"
set "VENV_DIR=.venv"
set "DIST_DIR=dist"
set "BUILD_DIR=build"

echo.
echo ============================================================
echo   %APP_NAME% - Windows Executable Builder
echo ============================================================
echo.

REM ------------------------------------------------------------
REM 1. Verify Python
REM ------------------------------------------------------------
where python >nul 2>&1
if errorlevel 1 (
echo [ERROR] Python was not found on PATH.
echo Install Python 3.8+ and make sure it is available on PATH.
exit /b 1
)

python --version
if errorlevel 1 (
echo [ERROR] Unable to execute Python.
exit /b 1
)

REM ------------------------------------------------------------
REM 2. Verify Git
REM ------------------------------------------------------------
where git >nul 2>&1
if errorlevel 1 (
echo [ERROR] Git was not found on PATH.
echo GetGitMergeInfoUI requires Git at runtime.
exit /b 1
)

git --version

REM ------------------------------------------------------------
REM 3. Verify application files
REM ------------------------------------------------------------
if not exist "%ENTRY_POINT%" (
echo [ERROR] %ENTRY_POINT% was not found.
echo Run this script from the repository root.
exit /b 1
)

if not exist "templates\index.html" (
echo [ERROR] templates\index.html was not found.
echo The Flask UI template is required by the executable.
exit /b 1
)

if not exist "requirements.txt" (
echo [ERROR] requirements.txt was not found.
exit /b 1
)

REM ------------------------------------------------------------
REM 4. Create virtual environment
REM ------------------------------------------------------------
if not exist "%VENV_DIR%\Scripts\python.exe" (
echo.
echo [INFO] Creating virtual environment...
python -m venv "%VENV_DIR%"
if errorlevel 1 (
echo [ERROR] Failed to create virtual environment.
exit /b 1
)
)

set "PYTHON=%CD%%VENV_DIR%\Scripts\python.exe"

echo.
echo [INFO] Using:
echo        %PYTHON%

REM ------------------------------------------------------------
REM 5. Upgrade packaging tools
REM ------------------------------------------------------------
echo.
echo [INFO] Updating pip/setuptools/wheel...
"%PYTHON%" -m pip install --upgrade pip setuptools wheel
if errorlevel 1 (
echo [ERROR] Failed to update packaging tools.
exit /b 1
)

REM ------------------------------------------------------------
REM 6. Install application dependencies
REM ------------------------------------------------------------
echo.
echo [INFO] Installing application dependencies...
"%PYTHON%" -m pip install -r requirements.txt
if errorlevel 1 (
echo [ERROR] Failed to install requirements.
exit /b 1
)

REM ------------------------------------------------------------
REM 7. Install PyInstaller
REM ------------------------------------------------------------
echo.
echo [INFO] Installing PyInstaller...
"%PYTHON%" -m pip install --upgrade pyinstaller
if errorlevel 1 (
echo [ERROR] Failed to install PyInstaller.
exit /b 1
)

REM ------------------------------------------------------------
REM 8. Clean previous build
REM ------------------------------------------------------------
echo.
echo [INFO] Cleaning previous build artifacts...

if exist "%BUILD_DIR%" (
rmdir /s /q "%BUILD_DIR%"
)

if exist "%DIST_DIR%" (
rmdir /s /q "%DIST_DIR%"
)

if exist "%APP_NAME%.spec" (
del /q "%APP_NAME%.spec"
)

REM ------------------------------------------------------------
REM 9. Build executable
REM ------------------------------------------------------------
echo.
echo [INFO] Building %APP_NAME%.exe...
echo.

"%PYTHON%" -m PyInstaller ^
--noconfirm ^
--clean ^
--onedir ^
--windowed ^
--name "%APP_NAME%" ^
--add-data "templates;templates" ^
"%ENTRY_POINT%"

if errorlevel 1 (
echo.
echo [ERROR] PyInstaller build failed.
exit /b 1
)

REM ------------------------------------------------------------
REM 10. Verify executable
REM ------------------------------------------------------------
if not exist "%DIST_DIR%%APP_NAME%%APP_NAME%.exe" (
echo.
echo [ERROR] Build completed but executable was not found.
exit /b 1
)

REM ------------------------------------------------------------
REM 11. Copy README if present
REM ------------------------------------------------------------
if exist "README.md" (
copy /y "README.md" "%DIST_DIR%%APP_NAME%" >nul
)

REM ------------------------------------------------------------
REM 12. Create launcher next to executable
REM ------------------------------------------------------------
(
echo @echo off
echo start "" "%%~dp0%APP_NAME%.exe"
) > "%DIST_DIR%%APP_NAME%\Run_%APP_NAME%.cmd"

REM ------------------------------------------------------------
REM 13. Success
REM ------------------------------------------------------------
echo.
echo ============================================================
echo   BUILD SUCCESSFUL
echo ============================================================
echo.
echo Executable:
echo   %CD%%DIST_DIR%%APP_NAME%%APP_NAME%.exe
echo.
echo Distribution folder:
echo   %CD%%DIST_DIR%%APP_NAME%
echo.
echo IMPORTANT:
echo   Git must be installed on the target Windows machine.
echo.
echo The application is configured as a local Flask application.
echo Open:
echo   http://127.0.0.1:5000
echo.
echo ============================================================
echo.

exit /b 0

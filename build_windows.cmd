@echo off
setlocal EnableExtensions

REM ============================================================
REM GetGitMergeInfoUI - Windows EXE Builder
REM ============================================================

set "APP_NAME=GetGitMergeInfoUI"
set "ROOT=%~dp0"
set "VENV=%ROOT%.venv"
set "PYTHON=%VENV%\Scripts\python.exe"
set "DIST=%ROOT%dist"
set "BUILD=%ROOT%build"

echo.
echo ============================================================
echo   %APP_NAME% - Windows EXE Builder
echo ============================================================
echo.
echo Repository:
echo   %ROOT%
echo.

REM ------------------------------------------------------------
REM 1. Check Python
REM ------------------------------------------------------------

where python >nul 2>&1

if errorlevel 1 (
echo [ERROR] Python was not found.
echo.
echo Install Python 3.10+ and make sure:
echo   "Add Python to PATH"
echo is enabled during installation.
echo.
pause
exit /b 1
)

echo [INFO] Python:
python --version

REM ------------------------------------------------------------
REM 2. Check Git
REM ------------------------------------------------------------

where git >nul 2>&1

if errorlevel 1 (
echo.
echo [ERROR] Git was not found on PATH.
echo.
echo GetGitMergeInfoUI requires Git on the target machine.
echo.
pause
exit /b 1
)

echo [INFO] Git:
git --version

REM ------------------------------------------------------------
REM 3. Check application files
REM ------------------------------------------------------------

if not exist "%ROOT%app.py" (
echo.
echo [ERROR] app.py was not found.
echo Make sure this CMD file is in the repository root.
echo.
pause
exit /b 1
)

if not exist "%ROOT%templates\index.html" (
echo.
echo [ERROR] templates\index.html was not found.
echo.
pause
exit /b 1
)

if not exist "%ROOT%requirements.txt" (
echo.
echo [ERROR] requirements.txt was not found.
echo.
pause
exit /b 1
)

echo [OK] Application files found.

REM ------------------------------------------------------------
REM 4. Create virtual environment
REM ------------------------------------------------------------

if not exist "%PYTHON%" (
echo.
echo [INFO] Creating virtual environment...
echo   %VENV%
echo.

```
python -m venv "%VENV%"

if errorlevel 1 (
    echo.
    echo [ERROR] Failed to create virtual environment.
    echo.
    pause
    exit /b 1
)
```

)

if not exist "%PYTHON%" (
echo.
echo [ERROR] Virtual environment Python was not created:
echo   %PYTHON%
echo.
pause
exit /b 1
)

echo.
echo [OK] Virtual environment:
echo   %PYTHON%

REM ------------------------------------------------------------
REM 5. Upgrade pip
REM ------------------------------------------------------------

echo.
echo [INFO] Updating pip...

"%PYTHON%" -m pip install --upgrade pip

if errorlevel 1 (
echo.
echo [ERROR] Failed to update pip.
echo.
echo Try running:
echo.
echo   "%PYTHON%" -m ensurepip --upgrade
echo.
pause
exit /b 1
)

REM ------------------------------------------------------------
REM 6. Install requirements
REM ------------------------------------------------------------

echo.
echo [INFO] Installing application requirements...

"%PYTHON%" -m pip install -r "%ROOT%requirements.txt"

if errorlevel 1 (
echo.
echo [ERROR] Failed to install application requirements.
echo.
pause
exit /b 1
)

REM ------------------------------------------------------------
REM 7. Install PyInstaller
REM ------------------------------------------------------------

echo.
echo [INFO] Installing PyInstaller...

"%PYTHON%" -m pip install --upgrade pyinstaller

if errorlevel 1 (
echo.
echo [ERROR] Failed to install PyInstaller.
echo.
pause
exit /b 1
)

REM ------------------------------------------------------------
REM 8. Clean previous build
REM ------------------------------------------------------------

echo.
echo [INFO] Cleaning previous build...

if exist "%BUILD%" (
rmdir /s /q "%BUILD%"
)

if exist "%DIST%" (
rmdir /s /q "%DIST%"
)

if exist "%ROOT%%APP_NAME%.spec" (
del /q "%ROOT%%APP_NAME%.spec"
)

REM ------------------------------------------------------------
REM 9. Build executable
REM ------------------------------------------------------------

echo.
echo ============================================================
echo   Building %APP_NAME%.exe
echo ============================================================
echo.

"%PYTHON%" -m PyInstaller ^
--clean ^
--noconfirm ^
--onedir ^
--windowed ^
--name "%APP_NAME%" ^
--add-data "%ROOT%templates;templates" ^
"%ROOT%app.py"

if errorlevel 1 (
echo.
echo [ERROR] PyInstaller build failed.
echo.
pause
exit /b 1
)

REM ------------------------------------------------------------
REM 10. Verify build
REM ------------------------------------------------------------

if not exist "%DIST%%APP_NAME%%APP_NAME%.exe" (
echo.
echo [ERROR] EXE was not created.
echo.
pause
exit /b 1
)

REM ---------------------------------------------------

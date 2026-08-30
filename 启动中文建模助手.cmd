@echo off
setlocal
set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"

if not exist "%PYTHON_EXE%" (
    echo Project Python was not found:
    echo %PYTHON_EXE%
    echo Please complete the installation steps in README.md.
    pause
    exit /b 1
)

pushd "%PROJECT_DIR%"
"%PYTHON_EXE%" -m abaqus_codex assistant
set "ASSISTANT_EXIT_CODE=%ERRORLEVEL%"
popd

if not "%ASSISTANT_EXIT_CODE%"=="0" (
    echo.
    echo Assistant exited with code %ASSISTANT_EXIT_CODE%.
    pause
)

endlocal & exit /b %ASSISTANT_EXIT_CODE%

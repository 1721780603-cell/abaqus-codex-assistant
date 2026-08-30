@echo off
chcp 65001 >nul
setlocal

rem 使用启动文件所在目录定位项目，移动整个项目后仍可正常使用。
set "PROJECT_DIR=%~dp0"
set "PYTHON_EXE=%PROJECT_DIR%.venv\Scripts\python.exe"

rem 虚拟环境不存在时给初学者显示清晰提示，不尝试使用未知 Python。
if not exist "%PYTHON_EXE%" (
    echo 未找到项目 Python：%PYTHON_EXE%
    echo 请先按照 README 完成项目安装。
    pause
    exit /b 1
)

rem 从项目根目录启动中文助手，确保配置和资源路径保持一致。
pushd "%PROJECT_DIR%"
"%PYTHON_EXE%" -m abaqus_codex assistant
set "ASSISTANT_EXIT_CODE=%ERRORLEVEL%"
popd

rem 正常关闭时不打扰用户；异常退出时保留窗口以便查看错误。
if not "%ASSISTANT_EXIT_CODE%"=="0" (
    echo.
    echo 中文建模助手异常退出，错误码：%ASSISTANT_EXIT_CODE%
    pause
)

endlocal & exit /b %ASSISTANT_EXIT_CODE%

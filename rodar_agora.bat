@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "SCRIPT_PATH=%SCRIPT_DIR%\buscar_nome_dou.py"

echo ============================================================
echo   Agente INLABS - Rodar agora
echo ============================================================
echo.

if not exist "%SCRIPT_PATH%" (
    echo [ERRO] Nao encontrei buscar_nome_dou.py em:
    echo   %SCRIPT_PATH%
    echo Este .bat precisa ficar na mesma pasta do script.
    pause
    exit /b 1
)

rem localiza o Python pela instalacao do "pythonw" (o Microsoft Store nao
rem registra um alias falso pra ele, entao esse caminho e sempre confiavel)
set "PYWEXE="
for /f "delims=" %%P in ('where pythonw 2^>nul') do (
    if not defined PYWEXE set "PYWEXE=%%P"
)

set "PYEXE="
if defined PYWEXE (
    set "PYEXE=!PYWEXE:pythonw.exe=python.exe!"
)

if not defined PYEXE (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        echo %%P | findstr /i "WindowsApps" >nul
        if errorlevel 1 (
            if not defined PYEXE set "PYEXE=%%P"
        )
    )
)

if not defined PYEXE (
    echo [ERRO] Python nao encontrado no PATH. Instale o Python e tente novamente.
    pause
    exit /b 1
)

pushd "%SCRIPT_DIR%"
"%PYEXE%" buscar_nome_dou.py %*
popd

echo.
echo ============================================================
echo   Concluido.
echo ============================================================
pause

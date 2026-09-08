@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "SCRIPT_PATH=%SCRIPT_DIR%\buscar_nome_dou.py"
set "LNK_NAME=AgenteINLABS_BuscaNome.lnk"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo ============================================================
echo   Agente INLABS - Ativar execucao ao ligar o computador
echo ============================================================
echo.

if not exist "%SCRIPT_PATH%" (
    echo [ERRO] Nao encontrei buscar_nome_dou.py em:
    echo   %SCRIPT_PATH%
    echo Este .bat precisa ficar na mesma pasta do script.
    pause
    exit /b 1
)

set "PYEXE="
for /f "delims=" %%P in ('where pythonw 2^>nul') do (
    if not defined PYEXE set "PYEXE=%%P"
)
if not defined PYEXE (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PYEXE set "PYEXE=%%P"
    )
)
if not defined PYEXE (
    echo [ERRO] Python nao encontrado no PATH. Instale o Python e tente novamente.
    pause
    exit /b 1
)

powershell -NoProfile -Command ^
    "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%STARTUP_DIR%\%LNK_NAME%');" ^
    "$s.TargetPath = '%PYEXE%';" ^
    "$s.Arguments = '\"%SCRIPT_PATH%\"';" ^
    "$s.WorkingDirectory = '%SCRIPT_DIR%';" ^
    "$s.Description = 'Agente INLABS - busca nome no Diario Oficial';" ^
    "$s.Save()"

if errorlevel 1 (
    echo.
    echo [ERRO] Nao foi possivel criar o atalho de inicializacao.
) else (
    echo.
    echo Pronto. A busca vai rodar automaticamente sempre que voce
    echo ligar/entrar no Windows com este usuario.
    echo Atalho criado em: %STARTUP_DIR%\%LNK_NAME%
)
echo.
pause

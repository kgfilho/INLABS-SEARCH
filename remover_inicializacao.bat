@echo off

set "LNK_NAME=AgenteINLABS_BuscaNome.lnk"
set "STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup"

echo ============================================================
echo   Agente INLABS - Remover execucao ao ligar o computador
echo ============================================================
echo.

if not exist "%STARTUP_DIR%\%LNK_NAME%" (
    echo Nenhum atalho de inicializacao encontrado ^(ja estava removido^).
    echo.
    pause
    exit /b 0
)

del /f /q "%STARTUP_DIR%\%LNK_NAME%"

if exist "%STARTUP_DIR%\%LNK_NAME%" (
    echo.
    echo [ERRO] Nao foi possivel remover o atalho.
) else (
    echo.
    echo Pronto. A busca nao vai mais rodar automaticamente ao ligar o PC
    echo ^(o agendamento diario, se ativado, continua valendo^).
)
echo.
pause

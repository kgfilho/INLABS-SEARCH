@echo off
setlocal enabledelayedexpansion

set "SCRIPT_DIR=%~dp0"
set "SCRIPT_DIR=%SCRIPT_DIR:~0,-1%"
set "TASK_NAME=AgenteINLABS_BuscaNome"
set "SCRIPT_PATH=%SCRIPT_DIR%\buscar_nome_dou.py"

echo ============================================================
echo   Agente INLABS - Horario da busca automatica (diaria)
echo ============================================================
echo.
echo   [1] Configurar / alterar horario
echo   [2] Remover o agendamento diario
echo   [3] Sair
echo.
set /p "OPCAO=Escolha uma opcao (1, 2 ou 3): "

if "%OPCAO%"=="1" goto configurar
if "%OPCAO%"=="2" goto remover
if "%OPCAO%"=="3" exit /b 0
echo Opcao invalida.
pause
exit /b 1

:configurar
if not exist "%SCRIPT_PATH%" (
    echo [ERRO] Nao encontrei buscar_nome_dou.py em:
    echo   %SCRIPT_PATH%
    echo Este .bat precisa ficar na mesma pasta do script.
    pause
    exit /b 1
)

rem localizar pythonw.exe (sem console) e cair para python.exe se preciso
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

:pedir_horario
set "HORARIO="
set /p "HORARIO=Digite o horario diario desejado (formato HH:MM, ex.: 05:00): "

if "%HORARIO%"=="" goto pedir_horario

echo(%HORARIO%| findstr /r "^[0-2][0-9]:[0-5][0-9]$" >nul
if errorlevel 1 (
    echo Horario invalido. Use o formato HH:MM, por exemplo 07:30.
    echo.
    goto pedir_horario
)

for /f "tokens=1 delims=:" %%H in ("%HORARIO%") do set "HH=%%H"
if %HH% GTR 23 (
    echo Horario invalido: hora deve ser entre 00 e 23.
    echo.
    goto pedir_horario
)

echo.
echo Configurando tarefa "%TASK_NAME%" para rodar todo dia as %HORARIO%...
echo   Python: %PYEXE%
echo   Script: %SCRIPT_PATH%
echo.

schtasks /Create /TN "%TASK_NAME%" /TR "\"%PYEXE%\" \"%SCRIPT_PATH%\"" /SC DAILY /ST %HORARIO% /F

if errorlevel 1 (
    echo.
    echo [ERRO] Nao foi possivel criar/atualizar a tarefa agendada.
    echo Tente executar este .bat novamente, ou abra um Prompt como
    echo Administrador se o erro persistir.
) else (
    echo.
    echo Pronto. A busca vai rodar automaticamente todo dia as %HORARIO%.
    echo Voce pode conferir em: Agendador de Tarefas ^> "%TASK_NAME%"
)
echo.
pause
exit /b 0

:remover
schtasks /Query /TN "%TASK_NAME%" >nul 2>&1
if errorlevel 1 (
    echo.
    echo Nenhum agendamento diario encontrado ^(tarefa "%TASK_NAME%" nao existe^).
    echo.
    pause
    exit /b 0
)

schtasks /Delete /TN "%TASK_NAME%" /F
if errorlevel 1 (
    echo.
    echo [ERRO] Nao foi possivel remover a tarefa agendada.
) else (
    echo.
    echo Agendamento diario removido. A busca nao vai mais rodar sozinha
    echo no horario fixo ^(a execucao ao ligar o PC, se ativada, continua valendo^).
)
echo.
pause
exit /b 0

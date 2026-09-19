@echo off
REM Primera linea util: cambiar al directorio del script
cd /d "%~dp0"
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo  =============================================
echo    AURA - Ejecucion de Pruebas Unitarias
echo  =============================================
echo.

if exist "%~dp0env\Scripts\python.exe" (
    set "PY_CMD=%~dp0env\Scripts\python.exe"
) else (
    set "PY_CMD=python"
)

if "%~1"=="" (
    echo  [INFO] Ejecutando suite de pruebas completa...
    "%PY_CMD%" -m pytest "%~dp0tests" -q
) else (
    echo  [INFO] Ejecutando: pytest %*
    "%PY_CMD%" -m pytest %*
)

if errorlevel 1 (
    echo.
    echo  [FALLO] Algunas pruebas fallaron.
    pause
    exit /b 1
)

echo.
echo  [EXITO] Todas las pruebas se ejecutaron correctamente.
pause

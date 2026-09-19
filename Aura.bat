@echo off
REM Primera linea util: cambiar al directorio del script
cd /d "%~dp0"
chcp 65001 >nul
setlocal EnableDelayedExpansion

REM Verificar que el entorno portable exista en %~dp0env
if not exist "%~dp0env\Scripts\python.exe" (
    echo.
    echo  [ERROR] El entorno portable no existe en:
    echo         "%~dp0env"
    echo  Por favor ejecuta primero: setup_env.bat
    echo.
    pause
    exit /b 1
)

echo.
echo  =============================================
echo    AURA - Iniciando aplicacion...
echo  =============================================
echo.

REM Ejecutar la aplicacion con el Python del entorno portable
"%~dp0env\Scripts\python.exe" "%~dp0run.py" %*

if errorlevel 1 (
    echo.
    echo  [ERROR] La aplicacion cerro con un codigo de error (!ERRORLEVEL!).
    pause
)

@echo off
REM Primera linea util: cambiar al directorio del script
cd /d "%~dp0"
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo  =============================================
echo    AURA - Gestor de Respaldo Portable
echo  =============================================
echo.

if exist "%~dp0env\Scripts\python.exe" (
    "%~dp0env\Scripts\python.exe" "%~dp0scripts\backup_manager.py" create %*
) else (
    python "%~dp0scripts\backup_manager.py" create %*
)

if errorlevel 1 (
    echo.
    echo  [ERROR] Fallo al generar el respaldo.
    pause
    exit /b 1
)

echo.
echo  [OK] Proceso finalizado.
pause

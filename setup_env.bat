@echo off
REM Primera linea util: cambiar al directorio del script
cd /d "%~dp0"
chcp 65001 >nul
setlocal EnableDelayedExpansion

echo.
echo  =============================================
echo    AURA - Configuracion del entorno portable
echo  =============================================
echo.

REM 1. Verificacion previa de requirements.txt en la raiz del proyecto
if not exist "%~dp0requirements.txt" (
    echo  [ERROR] No se encontro el archivo de requerimientos en:
    echo         "%~dp0requirements.txt"
    echo  Asegurate de que setup_env.bat este ubicado en la raiz de AURA.
    echo.
    pause
    exit /b 1
)

REM 2. Deteccion de Conda o Python 3.11
set "USE_CONDA=0"
set "PY_LAUNCHER="

REM Probar si conda esta disponible en el sistema
call conda --version >nul 2>&1
if not errorlevel 1 (
    echo  [INFO] Conda detectado en el sistema.
    set "USE_CONDA=1"
    goto :create_env
)

REM Si no hay Conda, detectar Python 3.11 via 'py -3.11'
call py -3.11 -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%v in ('py -3.11 --version 2^>^&1') do echo  [INFO] Python 3.11 detectado via py launcher: %%v
    set "PY_LAUNCHER=py -3.11"
    goto :create_env
)

REM Probar si el 'python' activo en el PATH es version 3.11
call python -c "import sys; sys.exit(0 if sys.version_info[:2] == (3, 11) else 1)" >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  [INFO] Python 3.11 detectado en PATH: %%v
    set "PY_LAUNCHER=python"
    goto :create_env
)

REM Si ninguna opcion encontro Python 3.11, mostrar error claro y salir sin crear nada
echo  [ERROR] No se encontro Python 3.11 en el sistema.
echo.
echo  AURA requiere estrictamente Python 3.11 para su entorno portable.
call python --version >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=*" %%v in ('python --version 2^>^&1') do echo  Version actual en PATH: %%v ^(No compatible^)
) else (
    echo  No se encontro ningun interprete de Python en el PATH.
)
echo.
echo  Para instalar Python 3.11 podes:
echo    1. Ejecutar en una consola: py install 3.11
echo    2. Descargar el instalador desde: https://www.python.org/downloads/release/python-3119/
echo.
echo  No se creo ningun entorno virtual.
echo.
pause
exit /b 1

:create_env
if "!USE_CONDA!"=="1" (
    echo.
    echo  [INFO] Creando entorno Conda en "%~dp0env" ^(Python 3.11^)...
    call conda create --prefix "%~dp0env" python=3.11 -y
    if errorlevel 1 (
        echo  [ERROR] Fallo la creacion del entorno Conda en "%~dp0env".
        pause
        exit /b 1
    )
    echo  [OK] Entorno Conda creado exitosamente en "%~dp0env".
) else (
    echo.
    echo  [INFO] Creando entorno virtual venv en "%~dp0env"...
    call !PY_LAUNCHER! -m venv "%~dp0env"
    if errorlevel 1 (
        echo  [ERROR] Fallo la creacion del entorno virtual en "%~dp0env".
        pause
        exit /b 1
    )
    echo  [OK] Entorno virtual venv creado exitosamente en "%~dp0env".
)

:install_deps
if not exist "%~dp0env\Scripts\python.exe" (
    echo.
    echo  [ERROR] No se encontro el ejecutable de Python en "%~dp0env\Scripts\python.exe".
    pause
    exit /b 1
)

echo.
echo  [INFO] Actualizando pip en el entorno portable...
"%~dp0env\Scripts\python.exe" -m pip install --upgrade pip --quiet

echo.
echo  [INFO] Instalando dependencias desde "%~dp0requirements.txt"...
"%~dp0env\Scripts\pip.exe" install -r "%~dp0requirements.txt"
if errorlevel 1 (
    echo.
    echo  [ERROR] Fallo al instalar las dependencias con pip.
    pause
    exit /b 1
)

REM 4. Inicializacion de .env desde .env.example si no existe
if not exist "%~dp0.env" (
    if exist "%~dp0.env.example" (
        echo.
        echo  [INFO] Creando configuracion inicial .env desde .env.example...
        copy "%~dp0.env.example" "%~dp0.env" >nul
        echo  [OK] Archivo .env creado. Recorda configurar tus API keys si usas proveedores cloud.
    )
)

echo.
echo  =============================================
echo    [OK] Entorno configurado correctamente.
echo    Ruta del entorno: "%~dp0env"
echo    Para iniciar AURA ejecuta: Aura.bat (o Aura.lnk)
echo  =============================================
echo.
pause

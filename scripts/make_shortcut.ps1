param(
    [switch]$Desktop,
    [switch]$RootOnly
)

$ErrorActionPreference = "Stop"

# Determinar directorio raiz del proyecto
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$RootDir = (Resolve-Path "$ScriptDir\..").Path

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  AURA - Generador de Accesos Directos (.lnk)" -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

# Verificar Aura.bat
$TargetBat = Join-Path $RootDir "Aura.bat"
if (-not (Test-Path $TargetBat)) {
    Write-Error "[ERROR] No se encontro '$TargetBat' en la raiz del proyecto."
    exit 1
}

# Resolver icono de waifu
$IcoWaifu = Join-Path $RootDir "assets\logo_waifu.ico"
$IcoLogo = Join-Path $RootDir "assets\logo.ico"
$IconPath = ""

if (Test-Path $IcoLogo) {
    try {
        $bytes = [System.IO.File]::ReadAllBytes($IcoLogo)
        if ($bytes.Length -ge 6 -and $bytes[0] -eq 0 -and $bytes[1] -eq 0 -and $bytes[2] -eq 1 -and $bytes[3] -eq 0) {
            $IconPath = $IcoLogo
        }
    } catch {}
}

if (-not $IconPath -and (Test-Path $IcoWaifu)) {
    try {
        $bytes = [System.IO.File]::ReadAllBytes($IcoWaifu)
        if ($bytes.Length -ge 6 -and $bytes[0] -eq 0 -and $bytes[1] -eq 0 -and $bytes[2] -eq 1 -and $bytes[3] -eq 0) {
            $IconPath = $IcoWaifu
        }
    } catch {}
}

if (-not $IconPath) {
    Write-Host "[INFO] Generando assets\logo_waifu.ico con Pillow..." -ForegroundColor Yellow
    $PyExe = Join-Path $RootDir "env\Scripts\python.exe"
    if (Test-Path $PyExe) {
        & $PyExe -c "from ui.branding import ensure_logo_waifu_ico; ensure_logo_waifu_ico()"
    } else {
        python -c "from ui.branding import ensure_logo_waifu_ico; ensure_logo_waifu_ico()"
    }
    if (Test-Path $IcoWaifu) {
        $IconPath = $IcoWaifu
    }
}

if (-not $IconPath -or -not (Test-Path $IconPath)) {
    Write-Error "[ERROR] No se pudo encontrar ni generar el icono de waifu en assets/."
    exit 1
}

Write-Host "[OK] Icono seleccionado: $IconPath" -ForegroundColor Green

# Crear objeto WScript.Shell
$WshShell = New-Object -ComObject WScript.Shell

function Create-AuraShortcut($DestLnkPath) {
    $Shortcut = $WshShell.CreateShortcut($DestLnkPath)
    $Shortcut.TargetPath = $TargetBat
    $Shortcut.WorkingDirectory = $RootDir
    $Shortcut.IconLocation = "$IconPath,0"
    $Shortcut.Description = "AURA - Asistente Universal con Respuesta Automatizada"
    $Shortcut.Save()
    Write-Host "[OK] Acceso directo creado: $DestLnkPath" -ForegroundColor Green
}

# 1. Crear en la raiz del proyecto
$RootLnk = Join-Path $RootDir "Aura.lnk"
Create-AuraShortcut $RootLnk

# 2. Si se solicito en el Escritorio
if ($Desktop) {
    $DesktopDir = [Environment]::GetFolderPath([Environment+SpecialFolder]::Desktop)
    $DesktopLnk = Join-Path $DesktopDir "Aura.lnk"
    Create-AuraShortcut $DesktopLnk
}

# Refrescar cache de iconos
Write-Host ""
Write-Host "[INFO] Refrescando cache de iconos de Windows (ie4uinit.exe -show)..." -ForegroundColor Cyan
try {
    Start-Process "ie4uinit.exe" -ArgumentList "-show" -NoNewWindow -Wait
} catch {
    # No critico
}

Write-Host ""
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host "  Acceso directo configurado exitosamente.   " -ForegroundColor Cyan
Write-Host "=============================================" -ForegroundColor Cyan
Write-Host ""

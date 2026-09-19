Add-Type -AssemblyName System.Drawing
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectDir = Split-Path -Parent $scriptDir
$srcPath = Join-Path $projectDir "assets\logo.png"
$destPath = Join-Path $projectDir "assets\logo_header.png"

if (Test-Path $srcPath) {
    $src = [System.Drawing.Image]::FromFile($srcPath)
    $dest = New-Object System.Drawing.Bitmap 128, 128
    $graphics = [System.Drawing.Graphics]::FromImage($dest)
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    $graphics.CompositingQuality = [System.Drawing.Drawing2D.CompositingQuality]::HighQuality
    $graphics.DrawImage($src, 0, 0, 128, 128)
    $dest.Save($destPath, [System.Drawing.Imaging.ImageFormat]::Png)
    $graphics.Dispose()
    $dest.Dispose()
    $src.Dispose()
    Write-Output "Successfully generated assets/logo_header.png (128x128)"
} else {
    Write-Error "Source file assets/logo.png not found"
}

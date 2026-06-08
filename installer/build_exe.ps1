# build_exe.ps1 — Construye ADOS_Installer.exe con PyInstaller
# Ejecutar desde la carpeta ADOS_Installer:
#   cd "c:\Users\fredy\OneDrive\TRABAJOS\Agentes IA\ADOS_Installer"
#   .\build_exe.ps1

$ErrorActionPreference = "Stop"

Write-Host "=== ADOS Installer — Build Script ===" -ForegroundColor Cyan

# 1. Instalar dependencias
Write-Host "`n[1/3] Instalando dependencias..." -ForegroundColor Yellow
python -m pip install -r requirements.txt

# 2. Construir el ejecutable
Write-Host "`n[2/3] Construyendo el ejecutable..." -ForegroundColor Yellow
pyinstaller `
    --name "ADOS_Installer" `
    --onefile `
    --windowed `
    --icon "assets\icon.ico" `
    --add-data "assets;assets" `
    --hidden-import customtkinter `
    --hidden-import PIL._tkinter_finder `
    --paths "src" `
    "src\main.py"

# 3. Resultado
Write-Host "`n[3/3] Build completado." -ForegroundColor Green
$exe = "dist\ADOS_Installer.exe"
if (Test-Path $exe) {
    $size = [math]::Round((Get-Item $exe).Length / 1MB, 1)
    Write-Host "Ejecutable generado: $exe ($size MB)" -ForegroundColor Green
} else {
    Write-Host "ERROR: No se genero el ejecutable." -ForegroundColor Red
}

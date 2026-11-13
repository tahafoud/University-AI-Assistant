# Windows PowerShell version.  Usage:  .\scripts\build_apk.ps1 -ApiBase https://your-host
param([string]$ApiBase = "")
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

if (-not (Get-Command flutter -ErrorAction SilentlyContinue)) { throw "flutter not found in PATH" }

foreach ($f in "intent_model.onnx","vocab.json","labels.json","config.json") {
  if (-not (Test-Path "assets/model/$f")) { throw "assets/model/$f is missing (copy from university_nlu/artifacts)" }
}

flutter pub get
flutter test

$defs = @()
if ($ApiBase) { $defs += "--dart-define=API_BASE=$ApiBase" }

flutter build apk --release --split-per-abi @defs

New-Item -ItemType Directory -Force -Path dist | Out-Null
Copy-Item build/app/outputs/flutter-apk/app-*-release.apk dist/
Get-ChildItem dist/*.apk | Format-Table Name, @{n="MB";e={[math]::Round($_.Length/1MB,1)}}
Get-FileHash dist/*.apk -Algorithm SHA256 | Format-Table Hash, Path
Write-Host "Most modern phones: app-arm64-v8a-release.apk"

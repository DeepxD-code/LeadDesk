param(
  [string]$OutDir = "backups",
  [string]$SevenZip = "7z"
)
$ErrorActionPreference = "Stop"
$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$root = Split-Path -Parent $PSScriptRoot
$stage = Join-Path $env:TEMP "leaddesk-backup-$ts"
$out = Join-Path $root $OutDir
New-Item -ItemType Directory -Force -Path $out | Out-Null
New-Item -ItemType Directory -Force -Path $stage | Out-Null
try {
  foreach ($p in @("data","secrets",".env")) {
    $src = Join-Path $root $p
    if (Test-Path $src) { Copy-Item $src -Destination (Join-Path $stage $p) -Recurse -Force }
  }
  $zip = Join-Path $out "leaddesk-backup-$ts.zip"
  if (Get-Command $SevenZip -ErrorAction SilentlyContinue) {
    $pw = Read-Host "Backup password (leave blank for unencrypted zip)" -AsSecureString
    $plain = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($pw))
    if ($plain) {
      & $SevenZip a -t7z -mhe=on ("$zip.7z") "$stage\*" "-p$plain" | Out-Null
      Remove-Item $zip -ErrorAction SilentlyContinue
      Write-Host "Encrypted backup: $zip.7z"
    } else {
      Compress-Archive -Path "$stage\*" -DestinationPath $zip -Force
      Write-Host "Backup created: $zip (unencrypted - install 7-Zip for encrypted backups)"
    }
  } else {
    Compress-Archive -Path "$stage\*" -DestinationPath $zip -Force
    Write-Host "Backup created: $zip (unencrypted - install 7-Zip for encrypted backups)"
  }
} finally {
  Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}

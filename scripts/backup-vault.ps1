param(
  [string]$OutDir = "",            # target folder; defaults to $env:LEADDESK_BACKUP_DIR or .\backups
  [string]$Password = "",          # optional for unattended runs; otherwise prompted
  [string]$SevenZip = ""           # optional explicit path to 7z.exe
)
$ErrorActionPreference = "Stop"

# Encrypted backup of the data directory, the master-key directory and .env.
# The password is never written to disk. Pass it with -Password for unattended
# runs, or let the script prompt. Beware: -Password is visible in the process
# command line, so prefer the prompt on a shared machine.

$ts = Get-Date -Format "yyyyMMdd-HHmmss"
$root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
  $OutDir = if ($env:LEADDESK_BACKUP_DIR) { $env:LEADDESK_BACKUP_DIR } else { "backups" }
}
$out = if ([System.IO.Path]::IsPathRooted($OutDir)) { $OutDir } else { Join-Path $root $OutDir }

# Resolve 7-Zip: parameter, PATH, then the standard install locations.
$exe = $SevenZip
if (-not $exe) {
  $cmd = Get-Command 7z -ErrorAction SilentlyContinue
  if ($cmd) { $exe = $cmd.Source }
  elseif (Test-Path "C:\Program Files\7-Zip\7z.exe") { $exe = "C:\Program Files\7-Zip\7z.exe" }
  elseif (Test-Path "C:\Program Files (x86)\7-Zip\7z.exe") { $exe = "C:\Program Files (x86)\7-Zip\7z.exe" }
}
if (-not $exe -or -not (Test-Path $exe)) {
  throw "7-Zip not found. Install it (winget install 7zip.7zip) and rerun."
}

if (-not $Password) {
  $secure = Read-Host "Backup password" -AsSecureString
  $Password = [Runtime.InteropServices.Marshal]::PtrToStringAuto(
    [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure))
}
if (-not $Password) { throw "A backup password is required; unencrypted vault backups are refused." }

$stage = Join-Path $env:TEMP "leaddesk-backup-$ts"
New-Item -ItemType Directory -Force -Path $out | Out-Null
New-Item -ItemType Directory -Force -Path $stage | Out-Null
try {
  foreach ($p in @("data", "secrets", ".env")) {
    $src = Join-Path $root $p
    if (Test-Path $src) { Copy-Item $src -Destination (Join-Path $stage $p) -Recurse -Force }
  }
  $archive = Join-Path $out "leaddesk-backup-$ts.7z"
  & $exe a -t7z -mhe=on -mx=9 "-p$Password" $archive "$stage\*" | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "7-Zip could not create the archive." }
  & $exe t "-p$Password" $archive | Out-Null
  if ($LASTEXITCODE -ne 0) { throw "Backup verification failed." }
  Write-Host "Encrypted backup written and verified: $archive"
  Write-Host "Keep the password in a password manager, separate from this machine."
} finally {
  Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
}

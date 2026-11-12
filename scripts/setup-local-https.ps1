$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$certDir = Join-Path $repoRoot 'certs'
$certPath = Join-Path $certDir 'localhost.pem'
$keyPath = Join-Path $certDir 'localhost-key.pem'

$mkcert = Get-Command mkcert -ErrorAction SilentlyContinue
if (-not $mkcert) {
    throw @'
mkcert is required to create a locally trusted HTTPS certificate.
Install it on Windows with:
  winget install FiloSottile.mkcert
Then reopen PowerShell and run this script again.
'@
}

New-Item -ItemType Directory -Path $certDir -Force | Out-Null
& $mkcert.Source -install
if ($LASTEXITCODE -ne 0) { throw 'mkcert could not install its local certificate authority.' }

& $mkcert.Source -cert-file $certPath -key-file $keyPath localhost 127.0.0.1 ::1
if ($LASTEXITCODE -ne 0) { throw 'mkcert could not generate the localhost certificate.' }

Write-Host "Local HTTPS certificate created at $certPath"
Write-Host 'The certificate and private key are ignored by git.'

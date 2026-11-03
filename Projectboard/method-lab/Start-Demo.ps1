# Baut das Method Lab und startet es lokal auf Port 8774.
$here = Split-Path -Parent $MyInvocation.MyCommand.Path
node "$here\build.mjs"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Start-Process "http://127.0.0.1:8774/"
node "$here\serve.mjs" 8774

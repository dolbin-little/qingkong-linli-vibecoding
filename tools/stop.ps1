$ErrorActionPreference='Stop'
$root=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Get-ChildItem -LiteralPath (Join-Path $root 'data') -Filter 'process-*.json' | ForEach-Object {
 $record=Get-Content -LiteralPath $_.FullName -Raw | ConvertFrom-Json
 $process=Get-CimInstance Win32_Process -Filter ("ProcessId="+[int]$record.pid) -ErrorAction SilentlyContinue
 if($process -and $process.ExecutablePath -and ([IO.Path]::GetFullPath($process.ExecutablePath)).StartsWith($root+'\',[StringComparison]::OrdinalIgnoreCase)){
  Stop-Process -Id ([int]$record.pid) -Force -ErrorAction SilentlyContinue
  Write-Output ('Stopped '+$record.role+' PID '+$record.pid)
 }
}

# Compatibility wrapper. The universal implementation lives in install-vector.py.
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)
$ErrorActionPreference = "Stop"
$script = Join-Path $PSScriptRoot "install-vector.py"
$python = Get-Command python -ErrorAction SilentlyContinue
if (-not $python) { $python = Get-Command py -ErrorAction SilentlyContinue }
if (-not $python) { throw "Python 3 is required. Install Python, then run this installer again." }
& $python.Source $script @Arguments
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

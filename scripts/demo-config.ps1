param(
    [Parameter(Mandatory)][ValidateSet('break', 'fix', 'status')][string]$Action,
    [Parameter(Mandatory)][string]$Environment,
    [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$arguments = @($Action, '--environment', $Environment)
if ($Apply) { $arguments += '--apply' }
uv run --frozen --project (Join-Path $root 'src/backend') python (Join-Path $PSScriptRoot 'demo_config.py') @arguments
if ($LASTEXITCODE -ne 0) { throw "Demo command exited with code $LASTEXITCODE. Review the output before retrying." }
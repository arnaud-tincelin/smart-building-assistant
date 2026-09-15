$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$env:SAMPLE_DOCS_DIR = Join-Path $root 'sample-docs'
$backend = Join-Path $root 'src\backend'

function Invoke-SetupScript {
    param([Parameter(Mandatory)][string]$ScriptName)

    uv run --project $backend python (Join-Path $PSScriptRoot $ScriptName)
    if ($LASTEXITCODE -ne 0) {
        throw "$ScriptName failed with exit code $LASTEXITCODE."
    }
}

Write-Output '==> Post-provision: AI Gateway telemetry setup'
Invoke-SetupScript 'setup_ai_gateway_telemetry.py'

Write-Output "`n==> Post-provision: Foundry IQ Knowledge Base setup"
Invoke-SetupScript 'setup_foundry_iq.py'

Write-Output "`n==> Post-provision: Foundry prompt agent setup"
Invoke-SetupScript 'setup_foundry_agent.py'

Write-Output "`n==> Post-provision: SRE Agent incident workflow setup"
Invoke-SetupScript 'setup_sre_agent.py'

Write-Output "`nFrontend: $($env:SERVICE_FRONTEND_URL ?? '<pending>')"
Write-Output "Backend : $($env:SERVICE_BACKEND_URL ?? '<pending>')"
Write-Output "Foundry : $($env:AZURE_AI_PROJECT_ENDPOINT ?? '<pending>')"
Write-Output "`nSRE Agent workflow details: docs/sre-agent.md"
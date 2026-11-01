#requires -Version 5.1
<#
  FinPilot AI - documentation consistency check (Layer 0 tooling).
  Non-application script: verifies required governance documents exist,
  that relative markdown links resolve, and that SEC-01..SEC-27 are all present
  in SECURITY_CHECKLIST.md. Exits non-zero on any failure.
#>
[CmdletBinding()]
param(
    [string]$Root
)

$ErrorActionPreference = 'Stop'

if ([string]::IsNullOrWhiteSpace($Root)) {
    $scriptDir = Split-Path -Parent $PSCommandPath
    $Root = Split-Path -Parent $scriptDir
}
$failures = New-Object System.Collections.Generic.List[string]

$required = @(
    'PROJECT_RULES.md',
    'PROJECT_SPEC.md',
    'ARCHITECTURE.md',
    'ACCEPTANCE_GATES.md',
    'DATA_AND_PERFORMANCE_POLICY.md',
    'SECURITY.md',
    'SECURITY_CHECKLIST.md',
    'README.md',
    'docs/threat-model.md',
    'docs/data-rights-matrix.md',
    'docs/experiment-register.md',
    'docs/security-decisions.md',
    'docs/exception-register.md',
    'docs/trade-policy-contract-v1.md',
    'docs/database-backup-restore.md',
    'docs/layers/README.md',
    'docs/layers/layer-00/README.md',
    'docs/layers/layer-01/README.md',
    'docs/layers/layer-02/README.md',
    'docs/layers/layer-03/README.md'
)

Write-Output "== Required documents =="
foreach ($rel in $required) {
    $full = Join-Path $Root $rel
    if (Test-Path -LiteralPath $full) {
        Write-Output ("  OK   {0}" -f $rel)
    } else {
        Write-Output ("  MISS {0}" -f $rel)
        $failures.Add("Missing required document: $rel")
    }
}

Write-Output ""
Write-Output "== Relative markdown link check =="
$mdFiles = Get-ChildItem -LiteralPath $Root -Recurse -Filter '*.md' -File |
    Where-Object {
        $_.FullName -notmatch '\\\.git\\' -and
        $_.FullName -notmatch '\\node_modules\\' -and
        $_.FullName -notmatch '\\\.venv\\' -and
        $_.FullName -notmatch '\\venv\\' -and
        $_.FullName -notmatch '\\dist\\' -and
        $_.FullName -notmatch '\\backend\\\.pytest_cache\\' -and
        $_.FullName -notmatch '\\ml\\\.pytest_cache\\'
    }

$linkCount = 0
$brokenCount = 0

foreach ($file in $mdFiles) {
    $content = Get-Content -LiteralPath $file.FullName -Raw
    # Matches markdown links [label](path) where path does not start with http/https/mailto/#
    $matches = [regex]::Matches($content, '\[([^\]]+)\]\(([^)]+)\)')
    foreach ($m in $matches) {
        $target = $m.Groups[2].Value.Trim()
        if ($target -match '^(https?://|mailto:|#)') {
            continue
        }
        # Strip query / fragment
        $pathOnly = ($target -split '[#?]')[0]
        if ([string]::IsNullOrWhiteSpace($pathOnly)) {
            continue
        }
        $linkCount++
        $resolved = Join-Path $file.DirectoryName $pathOnly
        if (-not (Test-Path -LiteralPath $resolved)) {
            Write-Output ("  BROKEN {0} -> {1} (in {2})" -f $m.Value, $pathOnly, (Split-Path -Leaf $file.FullName))
            $failures.Add("Broken relative link in $($file.FullName): $target")
            $brokenCount++
        }
    }
}
Write-Output ("  checked {0} relative link(s); {1} broken" -f $linkCount, $brokenCount)

Write-Output ""
Write-Output "== SEC-01..SEC-27 coverage in SECURITY_CHECKLIST.md =="
$secFile = Join-Path $Root 'SECURITY_CHECKLIST.md'
if (Test-Path -LiteralPath $secFile) {
    $secContent = Get-Content -LiteralPath $secFile -Raw
    $missingSec = @()
    1..27 | ForEach-Object {
        $id = "SEC-{0:d2}" -f $_
        if ($secContent -notmatch [regex]::Escape($id)) {
            $missingSec += $id
        }
    }
    if ($missingSec.Count -gt 0) {
        Write-Output ("  MISSING controls: {0}" -f ($missingSec -join ', '))
        $failures.Add("SECURITY_CHECKLIST.md missing controls: $($missingSec -join ', ')")
    } else {
        Write-Output "  OK   all 27 controls present"
    }
}

Write-Output ""
if ($failures.Count -eq 0) {
    Write-Output "RESULT: PASS"
    exit 0
} else {
    Write-Output ("RESULT: FAIL ({0} error(s))" -f $failures.Count)
    foreach ($f in $failures) {
        Write-Output ("  * {0}" -f $f)
    }
    exit 1
}

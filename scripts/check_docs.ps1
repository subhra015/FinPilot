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
    'docs/layers/README.md',
    'docs/layers/layer-00/README.md',
    'docs/layers/layer-01/README.md'
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
        $_.FullName -notmatch '\\coverage\\' -and
        $_.FullName -notmatch '\\__pycache__\\' -and
        $_.FullName -notmatch '\\\.mypy_cache\\' -and
        $_.FullName -notmatch '\\\.ruff_cache\\' -and
        $_.FullName -notmatch '\\\.pytest_cache\\'
    }
$linkCount = 0
$brokenCount = 0
foreach ($f in $mdFiles) {
    $text = Get-Content -LiteralPath $f.FullName -Raw
    if ($null -eq $text) { continue }
    $linkMatches = [regex]::Matches($text, '\]\(([^)]+)\)')
    foreach ($m in $linkMatches) {
        $target = $m.Groups[1].Value.Trim()
        if ($target -match '^(https?:|mailto:|#)') { continue }
        $target = ($target -split '#')[0].Trim()
        if ([string]::IsNullOrWhiteSpace($target)) { continue }
        if ($target -match '[<>|*?"]') { continue }
        $linkCount++
        $resolved = Join-Path (Split-Path -Parent $f.FullName) $target
        $exists = $false
        try { $exists = Test-Path -LiteralPath $resolved } catch { $exists = $false }
        if (-not $exists) {
            $brokenCount++
            Write-Output ("  BROKEN {0} -> {1}" -f $f.FullName.Replace($Root,''), $target)
            $failures.Add("Broken link in $($f.Name): $target")
        }
    }
}
Write-Output ("  checked {0} relative link(s); {1} broken" -f $linkCount, $brokenCount)

Write-Output ""
Write-Output "== SEC-01..SEC-27 coverage in SECURITY_CHECKLIST.md =="
$checklist = Join-Path $Root 'SECURITY_CHECKLIST.md'
$missingSec = @()
if (Test-Path -LiteralPath $checklist) {
    $cl = Get-Content -LiteralPath $checklist -Raw
    for ($i = 1; $i -le 27; $i++) {
        $id = "SEC-{0:D2}" -f $i
        if ($cl -notmatch [regex]::Escape($id)) {
            $missingSec += $id
        }
    }
    if ($missingSec.Count -eq 0) {
        Write-Output "  OK   all 27 controls present"
    } else {
        Write-Output ("  MISS {0}" -f ($missingSec -join ', '))
        foreach ($id in $missingSec) { $failures.Add("Missing control in checklist: $id") }
    }
} else {
    Write-Output "  MISS SECURITY_CHECKLIST.md"
}

Write-Output ""
if ($failures.Count -gt 0) {
    Write-Output ("RESULT: FAIL ({0} issue(s))" -f $failures.Count)
    exit 1
}
Write-Output "RESULT: PASS"
exit 0

<# Preview by default. Deletes only generated project artifacts; never customer data. #>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [switch]$Apply,
    [switch]$OldReleases
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot)).TrimEnd('\')
if (-not (Test-Path -LiteralPath (Join-Path $projectRoot 'desktop_launcher.py'))) {
    throw 'Project root validation failed.'
}
$rootPrefix = $projectRoot + [IO.Path]::DirectorySeparatorChar
$targets = [Collections.Generic.List[string]]::new()

function Add-GeneratedTarget([string]$Path) {
    if (-not (Test-Path -LiteralPath $Path)) { return }
    $resolved = (Resolve-Path -LiteralPath $Path).ProviderPath
    if (-not $resolved.StartsWith($rootPrefix, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Target outside project: $resolved"
    }
    $ancestor = $resolved
    while ($ancestor.Length -ge $projectRoot.Length) {
        if ((Get-Item -LiteralPath $ancestor -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Refusing reparse point in target path: $ancestor"
        }
        if ($ancestor -eq $projectRoot) { break }
        $ancestor = Split-Path -Parent $ancestor
    }
    $item = Get-Item -LiteralPath $resolved -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Refusing reparse point: $resolved"
    }
    # Inspect before recursing: never follow junctions or symbolic links.
    $pending = [Collections.Generic.Stack[string]]::new()
    if ($item.PSIsContainer) { $pending.Push($resolved) }
    while ($pending.Count -gt 0) {
        foreach ($child in Get-ChildItem -LiteralPath $pending.Pop() -Force) {
            if ($child.Attributes -band [IO.FileAttributes]::ReparsePoint) {
                throw "Refusing target with reparse point: $($child.FullName)"
            }
            if ($child.PSIsContainer) { $pending.Push($child.FullName) }
        }
    }
    $targets.Add($resolved)
}

foreach ($item in Get-ChildItem -LiteralPath $projectRoot -Directory -Force) {
    if ($item.Name -like '.pytest-*' -or $item.Name -in @('.pytest_cache', '.test-runs', 'build', '__pycache__')) {
        Add-GeneratedTarget $item.FullName
    }
}
foreach ($relative in @('.cache')) {
    Add-GeneratedTarget (Join-Path $projectRoot $relative)
}
foreach ($source in @('api', 'config', 'core', 'models', 'services', 'tests', 'legacy', 'packaging', 'scripts', 'Data_tool')) {
    $sourceRoot = Join-Path $projectRoot $source
    if (-not (Test-Path -LiteralPath $sourceRoot)) { continue }
    # Traverse only explicitly named source directories, excluding all runtime/profile roots.
    $pending = [Collections.Generic.Stack[string]]::new()
    $pending.Push($sourceRoot)
    while ($pending.Count -gt 0) {
        $directory = $pending.Pop()
        if ((Get-Item -LiteralPath $directory -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "Refusing source reparse point: $directory"
        }
        foreach ($child in Get-ChildItem -LiteralPath $directory -Directory -Force) {
            if ($child.Name -eq '__pycache__') { Add-GeneratedTarget $child.FullName }
            else { $pending.Push($child.FullName) }
        }
    }
}
if ($OldReleases) {
    # Only known intermediate releases; keep revoland-link-v18.
    $releases = @('context-strength', 'customer-hub', 'folder-posting', 'manual-comments',
        'negation-timeout', 'nested-folder-fix', 'property-inquiries', 'registry-130',
        'repost-link-check', 'saved-post-filter', 'share-links',
        'error-focus-v10', 'customer-comments-v11', 'posting-queue-v12',
        'customer-hub-v13', 'customer-groups-v14', 'customer-preview-v15', 'customer-group-column-v16', 'company-handover-v17')
    foreach ($release in $releases) {
        $releasePath = Join-Path $projectRoot "dist\$release"
        if (Test-Path -LiteralPath $releasePath) {
            # Reject unrecognized files so this option cannot erase future additions.
            foreach ($entry in Get-ChildItem -LiteralPath $releasePath -Force) {
                if ($entry.PSIsContainer -or $entry.Name -notin @(
                    'FacebookLeadFilter.exe', 'FacebookLeadFilter.sha256', 'CongCuBDS_JSON.exe',
                    'HUONG_DAN_CHAY_EXE.txt', 'EXE_VERIFICATION.json', 'RELEASE.json',
                    'CAP_NHAT.txt', 'AUTO_FOCUS_VERIFICATION.json', 'bai_dang_mau.json',
                    'CLEANUP_SUMMARY.json', 'HANDOVER_TEST_RESULTS.xml', 'HUONG_DAN_NHANH.txt',
                    'HUONG_DAN_SU_DUNG.pdf', 'KIEM_THU_TU_DONG.json', 'NGHIEM_THU_THUC_TE.md',
                    'RA_SOAT_BAN_GIAO.md', 'SHA256SUMS.txt')) {
                    throw "Unrecognized release content: $($entry.FullName)"
                }
            }
            Add-GeneratedTarget $releasePath
        }
    }
    Add-GeneratedTarget (Join-Path $projectRoot 'dist\RevolandFBPoster.exe')
    Add-GeneratedTarget (Join-Path $projectRoot 'dist\SHA256.txt')
}

$fileCount = 0
$byteCount = 0L
foreach ($target in $targets) {
    $item = Get-Item -LiteralPath $target -Force
    $files = if ($item.PSIsContainer) { @(Get-ChildItem -LiteralPath $target -Recurse -File -Force) } else { @($item) }
    $fileCount += $files.Count
    foreach ($file in $files) { $byteCount += $file.Length }
    Write-Output ($target.Substring($rootPrefix.Length))
}
Write-Output ("Targets: {0}; files: {1}; size: {2:N2} MB" -f $targets.Count, $fileCount, ($byteCount / 1MB))
if (-not $Apply) {
    Write-Output 'Preview only. Run again with -Apply to delete these generated artifacts. Stop tests/builds first.'
    return
}
foreach ($target in $targets) {
    if ($PSCmdlet.ShouldProcess($target, 'Delete generated artifact')) {
        Remove-Item -LiteralPath $target -Recurse -Force
    }
}
Write-Output 'Cleanup complete. Customer data, profiles, .venv and the main EXE were preserved.'



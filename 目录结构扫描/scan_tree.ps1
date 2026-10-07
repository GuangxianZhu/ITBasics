# scan_tree.ps1 - list every file under the current directory, one relative path per line,
# and write the result to file_structure.txt (easy for an AI to read: no tree indentation to decode).
# Usage: double-click run_scan_tree.bat (or: powershell -File scan_tree.ps1 [-Root path])
# NOTE: keep this file ASCII-only so Windows PowerShell 5.1 reads it correctly.

param([string]$Root = (Get-Location).Path)

$ErrorActionPreference = 'SilentlyContinue'
$Root = (Resolve-Path -LiteralPath $Root).Path
$OutName = 'file_structure.txt'
$OutPath = Join-Path $Root $OutName

# Folder names to skip (edit freely)
$Exclude = @('.git', 'node_modules', '__pycache__', '.vs', '.idea', '.venv', 'venv')

$paths = New-Object 'System.Collections.Generic.List[string]'
$script:dirCount = 0
$script:fileCount = 0

function Get-Rel([string]$full) {
    return ($full.Substring($Root.Length).TrimStart('\', '/') -replace '\\', '/')
}

function Walk([string]$dir) {
    $items = @(Get-ChildItem -LiteralPath $dir -Force |
        Where-Object { ($Exclude -notcontains $_.Name) -and ($_.FullName -ne $OutPath) })
    if ($items.Count -eq 0 -and $dir -ne $Root) {
        # empty folder: keep it, marked with a trailing slash
        $paths.Add((Get-Rel $dir) + '/')
        return
    }
    foreach ($it in $items) {
        if ($it.PSIsContainer) {
            $script:dirCount++
            # do not follow junctions / symlinks (avoids infinite loops)
            if (-not ($it.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                Walk $it.FullName
            }
        } else {
            $script:fileCount++
            $paths.Add((Get-Rel $it.FullName))
        }
    }
}

Walk $Root

$sorted = $paths.ToArray()
[Array]::Sort($sorted, [StringComparer]::OrdinalIgnoreCase)

$all = New-Object 'System.Collections.Generic.List[string]'
$all.Add('Root: ' + $Root)
$all.Add('Generated: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$all.Add('Excluded: ' + ($Exclude -join ', '))
$all.Add(('Total: {0} folders, {1} files. One relative path per line; a trailing / marks an empty folder.' -f $script:dirCount, $script:fileCount))
$all.Add('')
$all.AddRange([string[]]$sorted)

# UTF-8 with BOM so Notepad shows CJK file names correctly
[IO.File]::WriteAllLines($OutPath, $all, (New-Object System.Text.UTF8Encoding $true))

Write-Host "Done: $OutPath"
Write-Host ('{0} folders, {1} files' -f $script:dirCount, $script:fileCount)

# scan_tree.ps1 - scan the current directory and write the structure to file_structure.txt
# Usage: double-click run_scan_tree.bat (or: powershell -File scan_tree.ps1 [-Root path])
# NOTE: keep this file ASCII-only so Windows PowerShell 5.1 reads it correctly.

param([string]$Root = (Get-Location).Path)

$ErrorActionPreference = 'SilentlyContinue'
$Root = (Resolve-Path -LiteralPath $Root).Path
$OutName = 'file_structure.txt'
$OutPath = Join-Path $Root $OutName

# Folder names to skip (edit freely)
$Exclude = @('.git', 'node_modules', '__pycache__', '.vs', '.idea', '.venv', 'venv')

# Box-drawing characters built from code points (keeps this file ASCII)
$H = [string][char]0x2500
$TEE = [string][char]0x251C + $H + $H + ' '
$ELBOW = [string][char]0x2514 + $H + $H + ' '
$PIPE = [string][char]0x2502 + '   '
$BLANK = '    '

$lines = New-Object 'System.Collections.Generic.List[string]'
$script:dirCount = 0
$script:fileCount = 0
$script:totalBytes = [int64]0

function Format-Size([int64]$b) {
    if ($b -ge 1GB) { return ('{0:N2} GB' -f ($b / 1GB)) }
    if ($b -ge 1MB) { return ('{0:N2} MB' -f ($b / 1MB)) }
    if ($b -ge 1KB) { return ('{0:N1} KB' -f ($b / 1KB)) }
    return "$b B"
}

function Walk([string]$dir, [string]$prefix) {
    $items = @(Get-ChildItem -LiteralPath $dir -Force |
        Where-Object { ($Exclude -notcontains $_.Name) -and ($_.FullName -ne $OutPath) } |
        Sort-Object @{ Expression = { -not $_.PSIsContainer } }, Name)
    $n = $items.Count
    $i = 0
    foreach ($it in $items) {
        $i++
        $last = ($i -eq $n)
        $conn = if ($last) { $ELBOW } else { $TEE }
        if ($it.PSIsContainer) {
            $script:dirCount++
            $lines.Add($prefix + $conn + $it.Name + '/')
            # do not follow junctions / symlinks (avoids infinite loops)
            if (-not ($it.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
                $childPrefix = $prefix + $(if ($last) { $BLANK } else { $PIPE })
                Walk $it.FullName $childPrefix
            }
        } else {
            $script:fileCount++
            $script:totalBytes += $it.Length
            $lines.Add($prefix + $conn + $it.Name + '  (' + (Format-Size $it.Length) + ')')
        }
    }
}

$header = New-Object 'System.Collections.Generic.List[string]'
$header.Add('Directory: ' + $Root)
$header.Add('Generated: ' + (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'))
$header.Add('Excluded : ' + ($Exclude -join ', '))
$header.Add('')
$header.Add((Split-Path $Root -Leaf) + '/')

Walk $Root ''

$footer = @('', ('{0} folders, {1} files, total {2}' -f $script:dirCount, $script:fileCount, (Format-Size $script:totalBytes)))

$all = New-Object 'System.Collections.Generic.List[string]'
$all.AddRange($header)
$all.AddRange($lines)
$all.AddRange([string[]]$footer)

# UTF-8 with BOM so Notepad shows CJK file names correctly
[IO.File]::WriteAllLines($OutPath, $all, (New-Object System.Text.UTF8Encoding $true))

Write-Host "Done: $OutPath"
Write-Host ('{0} folders, {1} files' -f $script:dirCount, $script:fileCount)

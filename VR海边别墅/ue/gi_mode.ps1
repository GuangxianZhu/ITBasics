# Switch VillaVR rendering mode by editing Config\DefaultEngine.ini
#   forward : VR template default. Forward shading + MSAA, no Lumen (cheap, sharp, no dynamic GI)
#   lumen   : Deferred shading + TSR, Lumen GI/reflections (already configured: DynamicGlobalIlluminationMethod=1)
#   status  : print current mode
# The editor reads these at startup: close UE first, reopen after switching (first start compiles shaders).
param(
    [ValidateSet('forward', 'lumen', 'status')][string]$Mode = 'status',
    [string]$Project = (Join-Path $env:USERPROFILE 'Documents\Unreal Projects\VillaVR')
)
$ErrorActionPreference = 'Stop'
$ini = Join-Path $Project 'Config\DefaultEngine.ini'
if (-not (Test-Path $ini)) { Write-Host "[ERROR] not found: $ini"; exit 1 }

$text = [IO.File]::ReadAllText($ini)
function Get-Key([string]$k) {
    $m = [regex]::Match($text, '(?m)^' + [regex]::Escape($k) + '=([^\r\n]*)')
    if ($m.Success) { return $m.Groups[1].Value } else { return '(missing)' }
}
$fwd = Get-Key 'r.ForwardShading'
$aa = Get-Key 'r.AntiAliasingMethod'
$cur = if ($fwd -eq 'True' -or $fwd -eq '1') { 'forward' } else { 'lumen' }
Write-Host ("Current: {0}  (r.ForwardShading={1}, r.AntiAliasingMethod={2}, GI={3})" -f $cur, $fwd, $aa, (Get-Key 'r.DynamicGlobalIlluminationMethod'))
if ($Mode -eq 'status') { exit 0 }
if ($Mode -eq $cur) { Write-Host "Already in $Mode mode."; exit 0 }

if (Get-Process UnrealEditor -ErrorAction SilentlyContinue) {
    Write-Host '[WARN] Unreal Editor is running. The change only applies after you close and reopen it.'
}
$bak = $ini + '.before_gi_switch'
if (-not (Test-Path $bak)) { Copy-Item $ini $bak }

$want = @{}
if ($Mode -eq 'forward') { $want['r.ForwardShading'] = 'True'; $want['r.AntiAliasingMethod'] = '3' }   # 3 = MSAA
else { $want['r.ForwardShading'] = 'False'; $want['r.AntiAliasingMethod'] = '4' }                        # 4 = TSR
foreach ($k in $want.Keys) {
    $pat = '(?m)^' + [regex]::Escape($k) + '=[^\r\n]*'
    if (-not [regex]::IsMatch($text, $pat)) { Write-Host "[ERROR] key not found in ini: $k"; exit 1 }
    $text = [regex]::Replace($text, $pat, $k + '=' + $want[$k])
}
[IO.File]::WriteAllText($ini, $text, (New-Object Text.UTF8Encoding($false)))
Write-Host "Switched to $Mode. Backup: $bak"

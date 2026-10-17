# UE 5.8 Unreal MCP 接口自检脚本
# 原理: MCP = JSON-RPC 2.0 over HTTP (Streamable HTTP)。
#   1) initialize 握手 -> 服务器返回 serverInfo 和 Mcp-Session-Id
#   2) notifications/initialized 告知握手完成
#   3) tools/list 列出工具 (Tool Search 模式下应只有 3 个元工具)
#   4) tools/call list_toolsets 列出真正的工具集
param([int]$Port = 8000, [string]$Path = "/mcp")
$ErrorActionPreference = "Stop"
$Url = "http://127.0.0.1:$Port$Path"
$Log = Join-Path $PSScriptRoot "mcp_test_log.txt"
"=== MCP test $(Get-Date -Format s)  $Url ===" | Out-File $Log -Encoding utf8

function Write-Log($s) { $s | Out-File $Log -Append -Encoding utf8; Write-Host $s }

# 把 SSE ("data: {...}") 或纯 JSON 的响应体统一解析成对象
function Parse-Body($raw) {
  $lines = $raw -split "`n" | Where-Object { $_ -like "data:*" }
  if ($lines) { $raw = ($lines | ForEach-Object { $_.Substring(5).Trim() }) -join "" }
  return $raw | ConvertFrom-Json
}

$script:Session = $null
$script:Id = 0
function Send-Rpc($method, $params, [switch]$Notify) {
  $body = @{ jsonrpc = "2.0"; method = $method }
  if ($params) { $body.params = $params }
  if (-not $Notify) { $script:Id++; $body.id = $script:Id }
  $json = $body | ConvertTo-Json -Depth 20 -Compress
  $h = @{ "Accept" = "application/json, text/event-stream" }
  if ($script:Session) { $h["Mcp-Session-Id"] = $script:Session }
  $r = Invoke-WebRequest -Uri $Url -Method Post -Body ([Text.Encoding]::UTF8.GetBytes($json)) `
        -ContentType "application/json" -Headers $h -UseBasicParsing -TimeoutSec 30
  if ($r.Headers["Mcp-Session-Id"]) { $script:Session = $r.Headers["Mcp-Session-Id"] }
  if ($Notify -or -not $r.Content) { return $null }
  $content = $r.Content
  if ($content -is [byte[]]) { $content = [Text.Encoding]::UTF8.GetString($content) }
  return Parse-Body $content
}

try {
  # 0) 端口是否在监听
  $tcp = Test-NetConnection 127.0.0.1 -Port $Port -WarningAction SilentlyContinue
  Write-Log "[0] Port $Port listening: $($tcp.TcpTestSucceeded)"
  if (-not $tcp.TcpTestSucceeded) { throw "MCP 服务器没在监听。请在 UE 控制台输入 ModelContextProtocol.StartServer" }

  $init = Send-Rpc "initialize" @{ protocolVersion = "2025-06-18"; capabilities = @{}; clientInfo = @{ name = "zhu-mcp-selftest"; version = "1.0" } }
  Write-Log "[1] initialize -> serverInfo: $($init.result.serverInfo | ConvertTo-Json -Compress)  protocol: $($init.result.protocolVersion)  session: $script:Session"

  Send-Rpc "notifications/initialized" $null -Notify | Out-Null
  Write-Log "[2] notifications/initialized sent"

  $tl = Send-Rpc "tools/list" @{}
  $names = $tl.result.tools | ForEach-Object { $_.name }
  Write-Log "[3] tools/list -> $($names.Count) tools: $($names -join ', ')"

  if ($names -contains "list_toolsets") {
    $ts = Send-Rpc "tools/call" @{ name = "list_toolsets"; arguments = @{} }
    $txt = ($ts.result.content | ForEach-Object { $_.text }) -join "`n"
    Write-Log "[4] list_toolsets ->"
    Write-Log $txt
  }
  Write-Log "RESULT: PASS"
} catch {
  Write-Log "RESULT: FAIL  $($_.Exception.Message)"
}

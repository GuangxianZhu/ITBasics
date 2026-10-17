@echo off
rem One-click MCP interface self-test (no AI involved): initialize -> tools/list -> list_toolsets
rem Result: mcp_test_log.txt next to this file. UE must be open with the MCP server running.
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0test_mcp.ps1" %*
echo.
echo Log: %~dp0mcp_test_log.txt
pause

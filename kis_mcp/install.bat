@echo off
chcp 65001 > nul
echo [KIS MCP] Installing packages...
python -m pip install mcp httpx python-dotenv
echo.
echo Done. Please set KIS_ACCOUNT_NO in .env file.
pause

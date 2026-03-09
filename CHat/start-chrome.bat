@echo off
REM Script to start Chrome with remote debugging enabled

set CHROME_PATH="C:\Program Files\Google\Chrome\Application\chrome.exe"
set DEBUG_PORT=9222
set USER_DATA_DIR="C:\Users\%USERNAME%\AppData\Local\Google\Chrome\User Data"

REM Close any running Chrome instances
taskkill /F /IM chrome.exe 2>nul

REM Start Chrome with remote debugging
start "" %CHROME_PATH% --remote-debugging-port=%DEBUG_PORT% --user-data-dir=%USER_DATA_DIR%

echo Chrome started with remote debugging on port %DEBUG_PORT%
echo Navigate to nekto.me and then run: python bot.py
pause

@echo off
cd /d "%~dp0"
if exist "SR Voiceover Roulette.exe" (
    start "" "SR Voiceover Roulette.exe"
    exit /b
)
echo 没找到 exe，改用源码模式启动（会留一个黑框，方便看日志）...
"C:\Users\Admin\.workbuddy\binaries\python\envs\default\Scripts\python.exe" sr_roulette.py
pause

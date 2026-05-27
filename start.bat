@echo off
REM 一键启动脚本（Windows）
REM 用法：双击此文件 或 start.bat
docker compose up --build -d
echo.
echo 启动成功，访问 http://localhost:8000
pause

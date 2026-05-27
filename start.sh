#!/bin/bash
# 一键启动脚本（Linux / macOS）
# 用法：bash start.sh
docker compose up --build -d
echo ""
echo "✅ 启动成功，访问 http://localhost:8000"

#!/bin/bash
echo "🛑 停止台中榮總自動掛號系統..."

# 停止 Python 程序
pkill -f "python web_interface.py"

# 停止 Xvfb
pkill -f "Xvfb :99"

echo "✅ 系統已停止"

#!/bin/bash
cd ~/vghtc-register
source venv/bin/activate

# 設定環境變數
export CLOUD_DEPLOYMENT=true
export PORT=8080
export DISPLAY=:99

# 啟動虛擬顯示
Xvfb :99 -screen 0 1920x1080x24 &
XVFB_PID=$!

# 等待 Xvfb 啟動
sleep 2

echo "🚀 啟動台中榮總自動掛號系統..."
echo "📍 存取網址: http://$(curl -s -H "Metadata-Flavor: Google" http://metadata.google.internal/computeMetadata/v1/instance/network-interfaces/0/access-configs/0/external-ip):8080"

# 啟動應用程式
python web_interface.py

# 清理
kill $XVFB_PID 2>/dev/null

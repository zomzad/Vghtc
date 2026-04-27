#!/bin/bash
# 手動設定指令 (在 VM 上執行)

echo "🔧 手動設定台中榮總自動掛號系統"

# 更新系統
sudo apt update && sudo apt upgrade -y

# 安裝依賴
sudo apt install -y python3 python3-pip python3-venv git wget gnupg ca-certificates xvfb

# 建立虛擬環境
cd ~/vghtc-register
python3 -m venv venv
source venv/bin/activate

# 安裝 Python 套件
pip install -r requirements.txt

# 安裝 Playwright 瀏覽器
playwright install chromium
sudo playwright install-deps chromium

# 設定環境變數
export CLOUD_DEPLOYMENT=true
export PORT=8080
export DISPLAY=:99

echo "✅ 設定完成！"
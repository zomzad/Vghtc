#!/bin/bash

# GCP VM 快速設定腳本
# 在 GCP VM 上執行此腳本來快速部署系統

echo "🚀 台中榮總自動掛號系統 - GCP 部署腳本"
echo "================================================"

# 檢查是否為 root 用戶
if [ "$EUID" -eq 0 ]; then
    echo "❌ 請不要使用 root 用戶執行此腳本"
    exit 1
fi

# 更新系統
echo "📦 更新系統套件..."
sudo apt update && sudo apt upgrade -y

# 安裝基本依賴
echo "🔧 安裝基本依賴..."
sudo apt install -y python3 python3-pip python3-venv git wget gnupg ca-certificates xvfb

# 建立專案目錄
echo "📁 建立專案目錄..."
mkdir -p ~/vghtc-register
cd ~/vghtc-register

# 建立虛擬環境
echo "🐍 設定 Python 虛擬環境..."
python3 -m venv venv
source venv/bin/activate

# 安裝 Python 依賴 (假設 requirements.txt 已存在)
if [ -f "requirements.txt" ]; then
    echo "📋 安裝 Python 依賴..."
    pip install -r requirements.txt
else
    echo "📋 安裝基本 Python 依賴..."
    pip install flask==2.3.3 playwright==1.40.0 schedule==1.2.0 requests==2.31.0
fi

# 安裝 Playwright 瀏覽器
echo "🌐 安裝 Playwright 瀏覽器..."
playwright install chromium
sudo playwright install-deps chromium

# 設定環境變數
echo "⚙️ 設定環境變數..."
echo 'export CLOUD_DEPLOYMENT=true' >> ~/.bashrc
echo 'export PORT=8080' >> ~/.bashrc
echo 'export DISPLAY=:99' >> ~/.bashrc

# 建立啟動腳本
echo "📝 建立啟動腳本..."
cat > start_server.sh << 'EOF'
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
EOF

chmod +x start_server.sh

# 建立停止腳本
echo "🛑 建立停止腳本..."
cat > stop_server.sh << 'EOF'
#!/bin/bash
echo "🛑 停止台中榮總自動掛號系統..."

# 停止 Python 程序
pkill -f "python web_interface.py"

# 停止 Xvfb
pkill -f "Xvfb :99"

echo "✅ 系統已停止"
EOF

chmod +x stop_server.sh

# 建立系統服務 (可選)
echo "🔧 建立系統服務..."
sudo tee /etc/systemd/system/vghtc-register.service > /dev/null << EOF
[Unit]
Description=VGHTC Auto Register Service
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/vghtc-register
Environment=CLOUD_DEPLOYMENT=true
Environment=PORT=8080
Environment=DISPLAY=:99
ExecStartPre=/usr/bin/Xvfb :99 -screen 0 1920x1080x24 -ac
ExecStart=$HOME/vghtc-register/venv/bin/python web_interface.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# 重新載入 systemd
sudo systemctl daemon-reload

echo ""
echo "🎉 GCP VM 設定完成！"
echo "================================================"
echo ""
echo "📋 接下來的步驟："
echo "1. 上傳您的專案檔案到 ~/vghtc-register/"
echo "2. 確認以下檔案存在："
echo "   - web_interface.py"
echo "   - vghtc_auto_register.py" 
echo "   - vghtc_config.json"
echo "   - templates/ 資料夾"
echo ""
echo "🚀 啟動方式："
echo "   手動啟動: ./start_server.sh"
echo "   系統服務: sudo systemctl start vghtc-register"
echo ""
echo "🛑 停止方式："
echo "   手動停止: ./stop_server.sh"
echo "   系統服務: sudo systemctl stop vghtc-register"
echo ""
echo "🔍 查看狀態:"
echo "   sudo systemctl status vghtc-register"
echo ""
echo "🌐 設定防火牆規則允許 8080 端口後即可存取！"
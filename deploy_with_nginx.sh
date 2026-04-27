#!/bin/bash

# 腳本名稱: deploy_with_nginx.sh
# 功能: 在 Debian 11 上自動部署 VGHTC 自動掛號系統 (Nginx + Flask)

set -e  # 遇到錯誤立即停止

echo "🚀 開始部署 VGHTC 自動掛號系統 (Nginx 版)"
echo "============================================="

# 1. 檢查 root 權限
if [ "$EUID" -ne 0 ]; then
    echo "❌ 請使用 root 權限執行此腳本"
    echo "範例: sudo bash deploy_with_nginx.sh"
    exit 1
fi

# 獲取真實用戶
REAL_USER=${SUDO_USER:-$(whoami)}
USER_HOME="/home/$REAL_USER"
PROJECT_DIR="$USER_HOME/vghtc-register"

echo "👤 部署用戶: $REAL_USER"
echo "📂 專案目錄: $PROJECT_DIR"

# 2. 系統更新與安裝依賴
echo "📦 更新系統並安裝必要套件..."
apt-get update
apt-get install -y python3-venv python3-pip nginx xvfb libgbm1 libnss3 libasound2

# 3. 設定 Python 虛擬環境
echo "🐍 設定 Python 虛擬環境..."
cd "$PROJECT_DIR"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    echo "✅ 虛擬環境已建立"
fi

# 啟用虛擬環境並安裝套件
source venv/bin/activate
echo "📥 安裝 Python 依賴..."
pip install --upgrade pip
pip install flask selenium schedule beautifulsoup4 requests webdriver-manager ddddocr playwright

# 安裝 Playwright 瀏覽器
echo "🎭 安裝 Playwright 瀏覽器..."
playwright install chromium
playwright install-deps

# 4. 設定 Systemd 服務 (Flask App)
echo "⚙️ 設定 Systemd 服務..."
SERVICE_FILE="/etc/systemd/system/vghtc-register.service"

cat > $SERVICE_FILE << EOF
[Unit]
Description=VGHTC Auto Register Service (Flask)
After=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$REAL_USER
WorkingDirectory=$PROJECT_DIR
Environment=PATH=$PROJECT_DIR/venv/bin
Environment=DISPLAY=:99
Environment=PORT=5000
Environment=HOST=127.0.0.1
Environment=CLOUD_DEPLOYMENT=true
ExecStartPre=/bin/bash -c 'Xvfb :99 -screen 0 1024x768x24 -nolisten tcp > /dev/null 2>&1 &'
ExecStart=$PROJECT_DIR/venv/bin/python $PROJECT_DIR/web_interface.py
ExecStop=/bin/kill -TERM \$MAINPID
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

# 5. 設定 Nginx 反向代理
echo "🌐 設定 Nginx 反向代理..."
NGINX_CONF="/etc/nginx/sites-available/vghtc-register"

cat > $NGINX_CONF << EOF
server {
    listen 80;
    server_name _;  # 接受所有域名/IP

    # 增加上傳限制與超時設定
    client_max_body_size 10M;
    proxy_read_timeout 300;
    proxy_connect_timeout 300;
    proxy_send_timeout 300;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
    }
}
EOF

# 啟用 Nginx 設定
ln -sf $NGINX_CONF /etc/nginx/sites-enabled/
rm -f /etc/nginx/sites-enabled/default  # 移除預設設定

# 測試 Nginx 設定
nginx -t

# 6. 設定防火牆 (UFW)
if command -v ufw > /dev/null; then
    echo "🛡️ 設定 UFW 防火牆..."
    ufw allow 'Nginx Full'
    ufw allow 80/tcp
    ufw allow 22/tcp  # 確保 SSH 不被斷開
    # ufw enable  # 不自動啟用，避免意外斷線，讓使用者自己決定
fi

# 7. 啟動服務
echo "🚀 啟動服務..."
systemctl daemon-reload
systemctl enable vghtc-register
systemctl restart vghtc-register
systemctl restart nginx

# 8. 檢查狀態
echo "🔍 檢查服務狀態..."
if systemctl is-active --quiet vghtc-register; then
    echo "✅ Flask 服務: 運行中"
else
    echo "❌ Flask 服務: 啟動失敗 (請檢查 sudo journalctl -u vghtc-register)"
fi

if systemctl is-active --quiet nginx; then
    echo "✅ Nginx 服務: 運行中"
else
    echo "❌ Nginx 服務: 啟動失敗"
fi

# 獲取公網 IP
PUBLIC_IP=$(curl -s ifconfig.me || echo "無法獲取 IP")

echo ""
echo "🎉 部署完成！"
echo "============================================="
echo "🌍 請訪問: http://$PUBLIC_IP"
echo "============================================="

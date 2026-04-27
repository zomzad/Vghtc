#!/bin/bash

echo "🚀 設定 VGHTC 自動掛號系統為 systemd 服務"
echo "============================================="

# 檢查是否為 root 用戶
if [ "$EUID" -ne 0 ]; then
    echo "❌ 此腳本需要 root 權限執行"
    echo "請使用: sudo ./setup_systemd_service.sh"
    exit 1
fi

# 獲取當前用戶名稱 (執行 sudo 的原始用戶)
REAL_USER=${SUDO_USER:-$(whoami)}
USER_HOME="/home/$REAL_USER"

echo "👤 設定用戶: $REAL_USER"
echo "🏠 用戶目錄: $USER_HOME"

# 檢查專案目錄是否存在
if [ ! -d "$USER_HOME/vghtc-register" ]; then
    echo "❌ 找不到專案目錄: $USER_HOME/vghtc-register"
    exit 1
fi

# 建立 systemd 服務檔案
echo "📝 建立 systemd 服務檔案..."
cat > /etc/systemd/system/vghtc-register.service << EOF
[Unit]
Description=VGHTC Auto Register Service
After=network.target
Wants=network.target

[Service]
Type=simple
User=$REAL_USER
Group=$REAL_USER
WorkingDirectory=$USER_HOME/vghtc-register
Environment=PATH=$USER_HOME/vghtc-register/venv/bin
Environment=DISPLAY=:99
ExecStartPre=/bin/bash -c 'Xvfb :99 -screen 0 1024x768x24 -nolisten tcp > /dev/null 2>&1 &'
ExecStart=$USER_HOME/vghtc-register/venv/bin/python $USER_HOME/vghtc-register/web_interface.py
ExecStop=/bin/kill -TERM \$MAINPID
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 重新載入 systemd
echo "🔄 重新載入 systemd..."
systemctl daemon-reload

# 啟用服務 (開機自動啟動)
echo "✅ 啟用服務..."
systemctl enable vghtc-register.service

# 啟動服務
echo "🚀 啟動服務..."
systemctl start vghtc-register.service

# 檢查服務狀態
echo "🔍 檢查服務狀態..."
systemctl status vghtc-register.service

echo ""
echo "🎉 systemd 服務設定完成！"
echo "============================================="
echo ""
echo "📋 服務管理指令："
echo "🚀 啟動服務: sudo systemctl start vghtc-register"
echo "🛑 停止服務: sudo systemctl stop vghtc-register"
echo "🔄 重啟服務: sudo systemctl restart vghtc-register"
echo "📊 查看狀態: sudo systemctl status vghtc-register"
echo "📝 查看日誌: sudo journalctl -u vghtc-register -f"
echo ""
echo "🌐 網頁地址: http://$(curl -s ifconfig.me):8080"
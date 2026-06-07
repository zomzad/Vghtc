#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台中榮總自動掛號系統 - 網頁介面
使用 Flask 提供前端設定介面
"""

from flask import Flask, render_template, request, jsonify, redirect, url_for, flash
import json
import asyncio
import threading
import os
from datetime import datetime, timedelta
from vghtc_auto_register import VGHTCAutoRegister, ScheduleManager
import logging
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = 'vghtc_auto_register_secret_key'

# 初始化 LoginManager
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# 使用者資料檔案
USERS_FILE = 'users.json'

class User(UserMixin):
    def __init__(self, id, username, password_hash):
        self.id = id
        self.username = username
        self.password_hash = password_hash

def load_users():
    if not os.path.exists(USERS_FILE):
        # 預設使用者 admin / admin
        default_user = {
            '1': {
                'username': 'admin',
                'password_hash': generate_password_hash('admin')
            }
        }
        with open(USERS_FILE, 'w') as f:
            json.dump(default_user, f)
        return default_user
    try:
        with open(USERS_FILE, 'r') as f:
            return json.load(f)
    except:
        return {}

@login_manager.user_loader
def load_user(user_id):
    users = load_users()
    if user_id in users:
        user_data = users[user_id]
        return User(user_id, user_data['username'], user_data['password_hash'])
    return None

# 進度追蹤
progress_status = {
    'is_running': False,
    'current_step': '',
    'progress': 0,
    'message': '',
    'logs': []
}

def update_progress(step: str, progress: int, message: str):
    """更新進度狀態"""
    progress_status.update({
        'current_step': step,
        'progress': progress,
        'message': message
    })
    # 保留最近10條日誌
    progress_status['logs'].append(f"[{progress}%] {step}: {message}")
    if len(progress_status['logs']) > 10:
        progress_status['logs'] = progress_status['logs'][-10:]

# 全域變數
auto_register = VGHTCAutoRegister()
auto_register.set_progress_callback(update_progress)
schedule_manager = ScheduleManager(auto_register)

# 設定日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
        
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        users = load_users()
        user_id = None
        for uid, udata in users.items():
            if udata['username'] == username:
                if check_password_hash(udata['password_hash'], password):
                    user_id = uid
                break
        
        if user_id:
            user = load_user(user_id)
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('帳號或密碼錯誤')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('login'))

@app.route('/')
@login_required
def index():
    """首頁"""
    config = auto_register.config
    return render_template('index.html', config=config)


@app.route('/api/config', methods=['GET'])
@login_required
def get_config():
    """取得設定"""
    return jsonify(auto_register.config)


@app.route('/api/config', methods=['POST'])
@login_required
def save_config():
    """儲存病患資料"""
    try:
        data = request.json

        # 驗證必要欄位
        required_fields = ['id_number',
                           'birth_year', 'birth_month', 'birth_day']
        for field in required_fields:
            if not data.get('patient_info', {}).get(field):
                return jsonify({'success': False, 'message': f'請填寫{field}'})

        # 只更新病患資料
        auto_register.config['patient_info'].update(data['patient_info'])
        auto_register.save_config(auto_register.config)

        return jsonify({'success': True, 'message': '病患資料已儲存'})

    except Exception as e:
        logger.error(f"儲存病患資料失敗: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/config/schedule', methods=['POST'])
@login_required
def save_schedule_config():
    """儲存排程設定"""
    try:
        data = request.json

        # 驗證排程設定
        schedule_data = data.get('schedule', {})
        if not schedule_data.get('target_weekdays'):
            return jsonify({'success': False, 'message': '請選擇至少一個星期'})

        if not schedule_data.get('start_date') or not schedule_data.get('end_date'):
            return jsonify({'success': False, 'message': '請設定開始和結束日期'})

        # 更新排程設定
        auto_register.config['schedule'].update(schedule_data)
        auto_register.save_config(auto_register.config)

        return jsonify({'success': True, 'message': '排程設定已儲存'})

    except Exception as e:
        logger.error(f"儲存排程設定失敗: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/config/schedule/toggle', methods=['POST'])
def toggle_schedule_enabled():
    """切換排程功能開關"""
    try:
        data = request.json
        enabled = data.get('enabled', False)
        
        # 只更新 enabled 狀態，保持其他設定不變
        auto_register.config['schedule']['enabled'] = enabled
        auto_register.save_config(auto_register.config)
        
        message = '排程功能已啟用' if enabled else '排程功能已停用'
        return jsonify({'success': True, 'message': message})
        
    except Exception as e:
        logger.error(f"切換排程功能失敗: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/register/immediate', methods=['POST'])
def immediate_register():
    """立即掛號"""
    try:
        data = request.json
        target_date = data.get('target_date')

        if not target_date:
            return jsonify({'success': False, 'message': '請選擇掛號日期'})

        # 檢查是否已在執行中
        if progress_status['is_running']:
            return jsonify({'success': False, 'message': '系統正在執行掛號，請稍後再試'})

        # 重置進度狀態
        progress_status.update({
            'is_running': True,
            'current_step': '準備開始',
            'progress': 0,
            'message': f'準備掛號 {target_date}',
            'logs': []
        })

        # 在背景執行掛號
        def run_register():
            try:
                result = asyncio.run(
                    auto_register.register_specific_date(target_date))
                
                # 更新最終狀態
                progress_status.update({
                    'is_running': False,
                    'current_step': '完成',
                    'progress': 100,
                    'message': '掛號成功！' if result else '掛號失敗',
                })
                
                logger.info(f"立即掛號結果: {result}")
            except Exception as e:
                progress_status.update({
                    'is_running': False,
                    'current_step': '錯誤',
                    'progress': 0,
                    'message': f'掛號過程發生錯誤: {str(e)}',
                })
                logger.error(f"立即掛號失敗: {e}")

        thread = threading.Thread(target=run_register, daemon=True)
        thread.start()

        return jsonify({'success': True, 'message': f'已開始掛號 {target_date}，請查看下方進度'})

    except Exception as e:
        logger.error(f"立即掛號失敗: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/doctor/schedule', methods=['GET'])
@login_required
def get_doctor_schedule():
    """查詢醫師所有可掛號日期及額滿狀態"""
    try:
        if progress_status['is_running']:
            return jsonify({'success': False, 'message': '系統正在執行掛號，請稍後再試'})

        def run_fetch():
            try:
                result = asyncio.run(auto_register.fetch_doctor_schedule())
                progress_status['schedule_result'] = result
                progress_status['schedule_fetching'] = False
            except Exception as e:
                logger.error(f"查詢門診時間表失敗: {e}")
                progress_status['schedule_result'] = []
                progress_status['schedule_fetching'] = False

        progress_status['schedule_fetching'] = True
        progress_status['schedule_result'] = None
        thread = threading.Thread(target=run_fetch, daemon=True)
        thread.start()
        thread.join(timeout=60)

        result = progress_status.get('schedule_result', [])
        return jsonify({'success': True, 'data': result})
    except Exception as e:
        logger.error(f"查詢門診時間表失敗: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/progress', methods=['GET'])
def get_progress():
    """取得掛號進度"""
    return jsonify(progress_status)


@app.route('/api/register/auto', methods=['POST'])
def auto_register_range():
    """自動掛號（日期範圍）"""
    try:
        data = request.json
        weekdays = data.get('weekdays', [])
        start_date = data.get('start_date')
        end_date = data.get('end_date')

        if not weekdays:
            return jsonify({'success': False, 'message': '請選擇至少一個星期'})
        
        if not start_date or not end_date:
            return jsonify({'success': False, 'message': '請選擇開始和結束日期'})

        # 在背景執行掛號
        def run_auto_register():
            try:
                result = asyncio.run(
                    auto_register.auto_register_by_date_range(weekdays, start_date, end_date))
                logger.info(f"自動掛號結果: {result}")
            except Exception as e:
                logger.error(f"自動掛號失敗: {e}")

        thread = threading.Thread(target=run_auto_register, daemon=True)
        thread.start()

        weekday_names = {1: '一', 2: '二', 3: '三',
                         4: '四', 5: '五', 6: '六', 7: '日'}
        selected_days = [weekday_names[w] for w in weekdays]

        return jsonify({
            'success': True,
            'message': f'已開始自動掛號，目標星期: {", ".join(selected_days)}，日期範圍: {start_date} 到 {end_date}，請查看瀏覽器視窗'
        })

    except Exception as e:
        logger.error(f"自動掛號失敗: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/schedule/start', methods=['POST'])
def start_schedule():
    """啟動排程"""
    try:
        schedule_manager.start_schedule()
        return jsonify({'success': True, 'message': '排程已啟動'})
    except Exception as e:
        logger.error(f"啟動排程失敗: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/schedule/stop', methods=['POST'])
def stop_schedule():
    """停止排程"""
    try:
        schedule_manager.stop_schedule()
        return jsonify({'success': True, 'message': '排程已停止'})
    except Exception as e:
        logger.error(f"停止排程失敗: {e}")
        return jsonify({'success': False, 'message': str(e)})


@app.route('/api/schedule/status', methods=['GET'])
def schedule_status():
    """取得排程狀態"""
    schedule_config = auto_register.config['schedule']
    return jsonify({
        'running': schedule_manager.running,
        'enabled': schedule_config['enabled'],
        'config': {
            'target_weekdays': schedule_config['target_weekdays'],
            'check_time': schedule_config['check_time'],
            'start_date': schedule_config['start_date'],
            'end_date': schedule_config['end_date']
        }
    })


@app.route('/logs')
def view_logs():
    """查看日誌"""
    try:
        with open('vghtc_register.log', 'r', encoding='utf-8') as f:
            logs = f.readlines()

        # 只顯示最近100行
        recent_logs = logs[-100:] if len(logs) > 100 else logs

        return render_template('logs.html', logs=recent_logs)
    except FileNotFoundError:
        return render_template('logs.html', logs=['日誌檔案不存在'])


if __name__ == '__main__':
    # 檢查是否為雲端部署
    is_cloud = os.getenv('CLOUD_DEPLOYMENT', 'false').lower() == 'true'
    port = int(os.environ.get('PORT', 5000))
    
    # 確保使用者檔案存在
    print("檢查使用者資料庫...")
    load_users()
    if os.path.exists(USERS_FILE):
        print(f"使用者檔案位於: {os.path.abspath(USERS_FILE)}")
        print("預設管理員帳號: admin / 密碼: admin")
    
    if is_cloud:
        print("台中榮總自動掛號系統 - 雲端部署模式")
        app.run(host='0.0.0.0', port=port, debug=False)
    else:
        print("台中榮總自動掛號系統 - 本地開發模式")
        print(f"請開啟瀏覽器訪問: http://localhost:{port}")
        app.run(debug=True, host='0.0.0.0', port=port)

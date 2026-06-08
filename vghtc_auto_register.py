#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
台中榮總自動掛號系統
支援黃文男醫師免疫風濕科掛號
"""

import asyncio
import json
import logging
import os
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional
from playwright.async_api import async_playwright, Page, Browser
from playwright_stealth import Stealth
import capsolver
import schedule
import time
import threading

# 設定日誌 - 雲端環境適配
import os

def setup_logging():
    handlers = [logging.StreamHandler()]  # 總是使用 StreamHandler
    
    # 只在本地環境嘗試建立檔案日誌
    if not os.getenv('CLOUD_DEPLOYMENT', 'false').lower() == 'true':
        try:
            handlers.append(logging.FileHandler('vghtc_register.log', encoding='utf-8'))
        except (OSError, PermissionError):
            pass  # 忽略檔案建立錯誤
    
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers
    )

setup_logging()
logger = logging.getLogger(__name__)


class VGHTCAutoRegister:
    def __init__(self, config_file: str = 'vghtc_config.json'):
        self.config_file = config_file
        self.config = self.load_config()
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None
        self.progress_callback = None
    
    def set_progress_callback(self, callback):
        """設定進度回調函數"""
        self.progress_callback = callback
    
    def update_progress(self, step: str, progress: int, message: str):
        """更新進度"""
        if self.progress_callback:
            self.progress_callback(step, progress, message)
        logger.info(f"[{progress}%] {step}: {message}")

    def load_config(self) -> Dict:
        """載入設定檔"""
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except FileNotFoundError:
            # 預設設定
            default_config = {
                "patient_info": {
                    "id_number": "",
                    "birth_year": "",
                    "birth_month": "",
                    "birth_day": ""
                },
                "schedule": {
                    "enabled": False,
                    "target_weekdays": [2, 3, 5],  # 星期二、三、五
                    "check_time": "08:00",
                    "start_date": "",
                    "end_date": ""
                },
                "doctor_info": {
                    "section": "IMRH",
                    "section_name": "免疫風濕",
                    "doctor_no": "0961F",
                    "doctor_name": "黃文男"
                },
                "captcha_api_key": "b8dfe5b269d619f22045cef4ad78663a",  # 2captcha API key
                "cloud_deployment": False  # 是否為雲端部署
            }
            self.save_config(default_config)
            return default_config

    def save_config(self, config: Dict):
        """儲存設定檔"""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)

    async def init_browser(self, headless: bool = True, use_display: bool = False):
        """初始化瀏覽器"""
        playwright = await async_playwright().start()

        # 雲端部署時的瀏覽器設定
        launch_options = {
            'headless': headless,
            'args': [
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-gpu',
                '--no-first-run',
                '--no-default-browser-check',
                '--disable-background-timer-throttling',
                '--disable-backgrounding-occluded-windows',
                '--disable-renderer-backgrounding'
            ]
        }

        # 如果是雲端環境且需要顯示，使用虛擬顯示
        if use_display and headless:
            launch_options['args'].extend([
                '--virtual-time-budget=5000',
                '--run-all-compositor-stages-before-draw'
            ])

        self.browser = await playwright.chromium.launch(**launch_options)
        self.page = await self.browser.new_page()

        # 套用 stealth 偽裝，讓 reCAPTCHA 認為是正常瀏覽器
        await Stealth().apply_stealth_async(self.page)

        # 設定 User-Agent 和其他選項
        await self.page.set_extra_http_headers({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        })

        # 設定視窗大小
        await self.page.set_viewport_size({'width': 1920, 'height': 1080})

    async def close_browser(self):
        """關閉瀏覽器"""
        if self.browser:
            await self.browser.close()

    async def navigate_to_doctor_schedule(self) -> bool:
        """導航到醫師門診時間表"""
        try:
            # 前往掛號首頁
            logger.info("🌐 正在前往台中榮總掛號首頁...")
            await self.page.goto('https://register.vghtc.gov.tw/register/')
            await self.page.wait_for_load_state('networkidle')
            logger.info("✅ 成功載入掛號首頁")

            # 點擊複診預約掛號
            logger.info("🔗 正在進入科別選擇頁面...")
            await self.page.goto('https://register.vghtc.gov.tw/register/listSection.jsp')
            await self.page.wait_for_load_state('networkidle')
            logger.info("✅ 成功載入科別選擇頁面")

            # 點擊免疫風濕科
            logger.info(f"🏥 正在點擊 {self.config['doctor_info']['section_name']} 科...")
            await self.page.click(f'a[href*="section={self.config["doctor_info"]["section"]}"]')
            await self.page.wait_for_load_state('networkidle')
            logger.info(f"✅ 成功進入 {self.config['doctor_info']['section_name']} 科")

            # 點擊黃文男醫師
            logger.info(f"👨‍⚕️ 正在點擊 {self.config['doctor_info']['doctor_name']} 醫師...")
            doctor_selector = f'[id="{self.config["doctor_info"]["doctor_no"]}"]'
            await self.page.click(doctor_selector)
            await self.page.wait_for_load_state('networkidle')
            logger.info(f"✅ 成功進入 {self.config['doctor_info']['doctor_name']} 醫師門診時間表")

            logger.info(
                f"成功導航到{self.config['doctor_info']['doctor_name']}醫師門診時間表")
            
            # 除錯：截圖保存當前頁面
            try:
                await self.page.screenshot(path='debug_doctor_schedule.png')
                logger.debug("已保存醫師門診時間表截圖: debug_doctor_schedule.png")
            except Exception as e:
                logger.debug(f"截圖失敗: {e}")
            
            return True

        except Exception as e:
            logger.error(f"導航到醫師門診時間表失敗: {e}")
            return False

    async def get_available_appointments(self, target_weekdays: List[int], start_date_str: str = None, end_date_str: str = None) -> List[Dict]:
        """取得可預約的門診時間"""
        appointments = []

        # 計算日期範圍
        if start_date_str and end_date_str:
            start_date = datetime.strptime(start_date_str, '%Y-%m-%d').date()
            end_date = datetime.strptime(end_date_str, '%Y-%m-%d').date()
        else:
            # 預設範圍：今天到30天後
            start_date = datetime.now().date()
            end_date = start_date + timedelta(days=30)

        try:
            # 尋找所有【預約】連結 - 嘗試多種選擇器
            reservation_links = await self.page.query_selector_all('a:has-text("【預約】")')
            if not reservation_links:
                # 備用選擇器
                reservation_links = await self.page.query_selector_all('a[href*="javascript:document.T"]')
            if not reservation_links:
                # 再備用選擇器
                reservation_links = await self.page.query_selector_all('a[href*="javascript:"]')
            
            logger.info(f"找到 {len(reservation_links)} 個預約連結")
            
            # 除錯：也嘗試直接搜尋包含日期的元素
            date_elements = await self.page.query_selector_all('*:has-text("114.")')
            logger.debug(f"找到 {len(date_elements)} 個包含日期的元素")

            import re
            for i, link in enumerate(reservation_links):
                # 嘗試多層父元素來獲取日期資訊
                text_content = ""
                current_element = link
                
                # 向上查找包含日期的元素 (最多查找5層)
                for level in range(5):
                    parent = await current_element.query_selector('xpath=..')
                    if parent:
                        parent_text = await parent.text_content()
                        # 動態匹配任何民國年份（三位數）
                        if re.search(r'\d{3}\.', parent_text):
                            text_content = parent_text
                            # 只記錄簡短的日期資訊
                            date_match = re.search(r'(\d{3})\.(\d{1,2})\.(\d{1,2})', parent_text)
                            if date_match:
                                logger.debug(f"預約連結 {i+1}: 找到日期 {date_match.group()}")
                            break
                        current_element = parent
                    else:
                        break
                
                # 如果還是沒找到，直接用連結本身的文字
                if not text_content:
                    text_content = await link.text_content()

                # 解析日期 (格式: XXX.MM.DD，XXX為民國年份)
                date_match = re.search(r'(\d{3})\.(\d{1,2})\.(\d{1,2})', text_content)
                if date_match:
                    roc_year = int(date_match.group(1))  # 民國年（三位數）
                    month = int(date_match.group(2))
                    day = int(date_match.group(3))
                    
                    # 動態轉換民國年為西元年
                    ad_year = roc_year + 1911  # 例如：114 -> 2025, 115 -> 2026, 116 -> 2027
                    
                    # 計算完整日期
                    try:
                        full_date = datetime(ad_year, month, day)
                    except ValueError:
                        # 日期無效，跳過
                        logger.debug(f"無效日期: {ad_year}-{month}-{day}")
                        continue
                    
                    appointment_date = full_date.date()
                    weekday = full_date.weekday() + 1  # 轉換為1-7 (週一到週日)

                    # 檢查日期是否在範圍內
                    if start_date <= appointment_date <= end_date:
                        # 檢查是否為目標星期
                        if weekday in target_weekdays:
                            href = await link.get_attribute('href')
                            appointments.append({
                                'date': full_date.strftime('%Y-%m-%d'),
                                'weekday': weekday,
                                'link': link,
                                'href': href,
                                'text': text_content.strip(),
                                'days_from_today': (appointment_date - datetime.now().date()).days
                            })

            logger.info(f"在指定日期範圍內找到 {len(appointments)} 個可預約的門診時間")
            logger.info(f"搜尋日期範圍: {start_date} 到 {end_date}")
            
            # 詳細列出找到的門診時間
            for apt in appointments:
                logger.info(f"  - {apt['date']} (星期{apt['weekday']}) - {apt['text'][:50]}...")

            return appointments

        except Exception as e:
            logger.error(f"取得可預約門診時間失敗: {e}")
            return []

    async def make_appointment(self, appointment: Dict) -> bool:
        """進行掛號"""
        try:
            logger.info(
                f"開始掛號: {appointment['date']} (星期{appointment['weekday']})")

            # 點擊預約連結
            await appointment['link'].click()
            await self.page.wait_for_load_state('networkidle')

            # 填寫表單
            await self.fill_registration_form()

            # 處理 reCAPTCHA 驗證
            await self.handle_recaptcha()

            # 提交表單 - 嘗試多種選擇器
            submit_success = False
            submit_selectors = [
                'button:has-text("確認")',
                'input[type="submit"]',
                'button[type="submit"]',
                'input[name="Submit"]',
                'button:has-text("送出")',
                'button:has-text("提交")'
            ]
            
            for selector in submit_selectors:
                try:
                    submit_button = await self.page.query_selector(selector)
                    if submit_button:
                        logger.info(f"找到提交按鈕: {selector}")
                        await submit_button.click()
                        submit_success = True
                        break
                except Exception as e:
                    logger.debug(f"嘗試選擇器 {selector} 失敗: {e}")
                    continue
            
            if not submit_success:
                logger.warning("無法找到提交按鈕，嘗試按 Enter 鍵")
                await self.page.keyboard.press('Enter')
            
            await self.page.wait_for_load_state('networkidle')

            # 檢查結果
            page_content = await self.page.content()
            page_text = await self.page.text_content('body')
            current_url = self.page.url
            
            # 截圖保存結果頁面
            try:
                await self.page.screenshot(path=f'result_{appointment["date"]}.png')
                logger.info(f"已保存結果頁面截圖: result_{appointment['date']}.png")
            except Exception as e:
                logger.debug(f"截圖失敗: {e}")
            
            # 記錄頁面資訊用於除錯
            logger.info(f"結果頁面 URL: {current_url}")
            logger.debug(f"頁面內容關鍵字: {page_text[:200]}...")
            
            # 檢查多種成功訊息 (基於台中榮總實際使用的訊息)
            success_keywords = [
                '預約成功', '掛號成功', '完成預約', '預約完成',
                '成功', '已完成', '預約已建立', '掛號已完成',
                '謝謝您的預約', '預約資料已送出', '預約資料已儲存',
                '門診預約掛號完成', '您的預約', '掛號完成',
                '預約號碼', '看診序號', '請準時就診'
            ]
            
            failure_keywords = [
                '預約失敗', '掛號失敗', '錯誤', '失敗',
                '無法預約', '額滿', '已額滿', '系統錯誤',
                '驗證碼錯誤', '資料錯誤'
            ]
            
            # 若還停留在表單頁，代表驗證碼未通過或表單被退回
            if 'registerPrompt.jsp' in current_url:
                logger.warning(f"掛號失敗: 仍在表單頁 ({current_url})，可能是 reCAPTCHA 未通過")
                return False

            # 檢查失敗關鍵字
            for keyword in failure_keywords:
                if keyword in page_text:
                    logger.warning(f"掛號失敗 - 發現失敗關鍵字: {keyword}")
                    return False

            # 檢查成功關鍵字
            for keyword in success_keywords:
                if keyword in page_text:
                    logger.info(f"掛號成功: {appointment['date']} - 發現成功關鍵字: {keyword}")
                    return True

            # 頁面已跳轉且無明確失敗訊息，記錄頁面文字供人工確認
            logger.warning(f"掛號結果不明: 頁面已跳轉至 {current_url}，但未找到成功/失敗關鍵字")
            logger.warning(f"頁面文字前300字: {page_text[:300]}")
            return False

        except Exception as e:
            logger.error(f"掛號失敗: {e}")
            return False

    async def fill_registration_form(self):
        """填寫掛號表單"""
        try:
            patient_info = self.config['patient_info']

            # 填寫身分證字號
            await self.page.fill('input[name="patientID"]', patient_info['id_number'])

            # 填寫出生年份
            await self.page.fill('input[name="patientBirthYear"]', patient_info['birth_year'])

            # 選擇出生月份
            await self.page.select_option('select[name="patientBirthMonth"]', patient_info['birth_month'])

            # 選擇出生日期
            await self.page.select_option('select[name="patientBirthDate"]', patient_info['birth_day'])

            logger.info("表單填寫完成")

        except Exception as e:
            logger.error(f"填寫表單失敗: {e}")
            raise

    async def handle_recaptcha(self):
        """處理 reCAPTCHA 驗證"""
        try:
            # 等待頁面穩定後再偵測
            await self.page.wait_for_timeout(2000)

            # 診斷：列出所有 iframe
            all_frames = self.page.frames
            logger.info(f"頁面共有 {len(all_frames)} 個 frame")
            for f in all_frames:
                logger.info(f"  frame URL: {f.url[:100]}")

            # 診斷：找 data-sitekey
            sitekey_el = await self.page.query_selector('[data-sitekey]')
            logger.info(f"data-sitekey 元素: {sitekey_el}")

            recaptcha_frame = await self.page.query_selector('iframe[src*="recaptcha"]')

            if not recaptcha_frame:
                logger.info("未偵測到 reCAPTCHA，繼續執行")
                return

            logger.info("偵測到 reCAPTCHA，使用 CapSolver 解題...")
            if await self.solve_recaptcha_with_capsolver():
                logger.info("reCAPTCHA CapSolver 解決成功")
                return

            # fallback: 本地環境等待手動處理
            is_cloud = os.getenv('CLOUD_DEPLOYMENT', 'false').lower() == 'true'
            if not is_cloud:
                self.update_progress(
                    "等待手動驗證", 60,
                    "⚠️ CapSolver 失敗，請查看已開啟的瀏覽器視窗，手動勾選「我不是機器人」，完成後系統將自動繼續（最多等待 3 分鐘）"
                )
                logger.info("CapSolver 失敗，等待手動完成 reCAPTCHA 驗證（最多 180 秒）...")

                # 每 5 秒檢查一次，最多等 180 秒
                for _ in range(36):
                    await self.page.wait_for_timeout(5000)
                    token_value = await self.page.evaluate("""
                        (function() {
                            var el = document.getElementById('g-recaptcha-response');
                            return el ? el.value || el.innerHTML : '';
                        })()
                    """)
                    if token_value and len(token_value) > 20:
                        logger.info("偵測到手動完成 reCAPTCHA，繼續執行...")
                        self.update_progress("驗證完成", 70, "reCAPTCHA 手動完成，繼續掛號...")
                        return
                raise Exception("reCAPTCHA 未完成（等待 3 分鐘後仍未偵測到驗證結果）")
            else:
                raise Exception("reCAPTCHA CapSolver 解題失敗，無法繼續掛號")

        except Exception as e:
            logger.error(f"reCAPTCHA 處理失敗: {e}")
            raise

    async def solve_recaptcha_with_capsolver(self) -> bool:
        """使用 CapSolver REST API 解決 reCAPTCHA v2"""
        try:
            api_key = self.config.get('capsolver_api_key', '')
            if not api_key:
                logger.warning("未設定 capsolver_api_key")
                return False

            # 取得 site key
            site_key = await self.page.get_attribute('[data-sitekey]', 'data-sitekey')
            if not site_key:
                site_key = '6LedJkIeAAAAALoCNvLVaP1QM9SV2psBNZ9qBCPc'
            current_url = self.page.url

            logger.info(f"送出 CapSolver 任務 (site_key: {site_key[:20]}...)")

            # 透過瀏覽器的 fetch 呼叫 CapSolver API（繞過 Python requests 防火牆限制）
            logger.info("透過瀏覽器呼叫 CapSolver API...")
            create_result = await self.page.evaluate("""
                async ([apiKey, siteKey, pageUrl]) => {
                    const resp = await fetch('https://api.capsolver.com/createTask', {
                        method: 'POST',
                        headers: {'Content-Type': 'application/json'},
                        body: JSON.stringify({
                            clientKey: apiKey,
                            task: {
                                type: 'ReCaptchaV2TaskProxyLess',
                                websiteURL: pageUrl,
                                websiteKey: siteKey
                            }
                        })
                    });
                    return await resp.json();
                }
            """, [api_key, site_key, current_url])

            logger.info(f"CapSolver createTask 回應: {create_result}")
            if create_result.get('errorId', 1) != 0:
                raise Exception(f"CapSolver createTask 失敗: {create_result.get('errorDescription', '未知錯誤')}")

            task_id = create_result.get('taskId')
            if not task_id:
                raise Exception("CapSolver 未回傳 taskId")

            logger.info(f"CapSolver taskId: {task_id}，等待解題...")

            # 輪詢解題結果（最多 120 秒）
            token = None
            for attempt in range(24):
                await asyncio.sleep(5)
                result_data = await self.page.evaluate("""
                    async ([apiKey, taskId]) => {
                        const resp = await fetch('https://api.capsolver.com/getTaskResult', {
                            method: 'POST',
                            headers: {'Content-Type': 'application/json'},
                            body: JSON.stringify({clientKey: apiKey, taskId: taskId})
                        });
                        return await resp.json();
                    }
                """, [api_key, task_id])

                status = result_data.get('status')
                logger.info(f"CapSolver 狀態 ({attempt+1}/24): {status}")

                if status == 'ready':
                    token = result_data.get('solution', {}).get('gRecaptchaResponse')
                    break
                elif status == 'failed' or result_data.get('errorId', 0) != 0:
                    raise Exception(f"CapSolver 解題失敗: {result_data.get('errorDescription', '未知錯誤')}")

            if not token:
                raise Exception("CapSolver 解題超時（120秒）")

            if not token:
                logger.error("CapSolver 未回傳 token")
                return False

            # 注入 token 並觸發 reCAPTCHA callback
            await self.page.evaluate(f"""
                (function() {{
                    var token = "{token}";

                    // 1. 寫入隱藏欄位
                    var resp = document.getElementById("g-recaptcha-response");
                    if (resp) {{
                        resp.style.display = "block";
                        resp.innerHTML = token;
                    }}

                    // 2. 呼叫 data-callback 指定的函式
                    var el = document.querySelector("[data-callback]");
                    if (el) {{
                        var cbName = el.getAttribute("data-callback");
                        if (cbName && typeof window[cbName] === "function") {{
                            window[cbName](token);
                        }}
                    }}

                    // 3. 透過 grecaptcha 內部 clients 觸發 callback（最通用）
                    try {{
                        var clients = window.___grecaptcha_cfg.clients;
                        Object.keys(clients).forEach(function(key) {{
                            var client = clients[key];
                            Object.keys(client).forEach(function(k) {{
                                if (client[k] && typeof client[k].callback === "function") {{
                                    client[k].callback(token);
                                }}
                            }});
                        }});
                    }} catch(e) {{}}
                }})();
            """)
            await self.page.wait_for_timeout(2000)

            # 驗證 token 是否成功注入（g-recaptcha-response 有值）
            token_value = await self.page.evaluate("""
                (function() {
                    var el = document.getElementById('g-recaptcha-response');
                    return el ? el.value || el.innerHTML : '';
                })()
            """)
            if token_value and len(token_value) > 20:
                logger.info(f"CapSolver token 注入成功，token 長度: {len(token_value)}")
                return True
            else:
                logger.error(f"CapSolver token 注入後驗證失敗，token 為空或太短: '{str(token_value)[:50]}'")
                return False

        except Exception as e:
            logger.error(f"CapSolver 解題失敗: {e}")
            return False

    async def solve_recaptcha_with_service(self, api_key: str) -> bool:
        """使用第三方服務解決 reCAPTCHA"""
        try:
            # 取得 reCAPTCHA site key
            site_key = await self.page.get_attribute('[data-sitekey]', 'data-sitekey')
            if not site_key:
                site_key = '6LedJkIeAAAAALoCNvLVaP1QM9SV2psBNZ9qBCPc'  # 台中榮總的 site key

            current_url = self.page.url

            # 提交到 2captcha
            payload = {
                'key': api_key,
                'method': 'userrecaptcha',
                'googlekey': site_key,
                'pageurl': current_url
            }

            response = requests.post(
                'https://2captcha.com/in.php', data=payload, timeout=30)

            if response.ok and 'OK|' in response.text:
                captcha_id = response.text.split('|')[1]
                logger.info(f"reCAPTCHA 任務已提交，ID: {captcha_id}")

                # 等待解決結果
                for attempt in range(20):  # 最多等待2分鐘
                    await asyncio.sleep(6)

                    result_response = requests.get(
                        f'https://2captcha.com/res.php?key={api_key}&action=get&id={captcha_id}',
                        timeout=10
                    )

                    if 'CAPCHA_NOT_READY' in result_response.text:
                        continue
                    elif 'OK|' in result_response.text:
                        captcha_solution = result_response.text.split('|')[1]

                        # 注入解決方案
                        js_code = f'''
                        document.getElementById("g-recaptcha-response").style.display="block";
                        document.getElementById("g-recaptcha-response").innerHTML="{captcha_solution}";
                        '''
                        await self.page.evaluate(js_code)

                        logger.info("reCAPTCHA 解決方案已注入")
                        return True
                    else:
                        logger.error(f"reCAPTCHA 解決失敗: {result_response.text}")
                        break

            return False

        except Exception as e:
            logger.error(f"使用第三方服務解決 reCAPTCHA 失敗: {e}")
            return False

    async def auto_handle_recaptcha(self):
        """雲端環境下的自動 reCAPTCHA 處理"""
        try:
            # 嘗試點擊 reCAPTCHA 複選框
            checkbox = await self.page.query_selector('iframe[src*="recaptcha"] >> css=div.recaptcha-checkbox-border')
            if checkbox:
                await checkbox.click()
                logger.info("已點擊 reCAPTCHA 複選框")

                # 等待驗證完成或出現圖片驗證
                await self.page.wait_for_timeout(3000)

                # 檢查是否需要圖片驗證
                challenge_frame = await self.page.query_selector('iframe[src*="recaptcha/api2/bframe"]')
                if challenge_frame:
                    logger.warning("出現圖片驗證，雲端環境無法自動處理")
                    # 可以在這裡加入更進階的圖片識別邏輯
                else:
                    logger.info("reCAPTCHA 可能已自動通過")

        except Exception as e:
            logger.warning(f"自動處理 reCAPTCHA 失敗: {e}")

    async def get_all_doctor_schedule(self) -> List[Dict]:
        """取得醫師所有門診日期及額滿狀態"""
        results = []
        try:
            import re
            # 找所有包含日期資訊的列，包含可預約和額滿
            # 先抓可預約的連結
            reservation_links = await self.page.query_selector_all('a:has-text("【預約】")')
            available_dates = set()

            for link in reservation_links:
                text_content = ""
                current_element = link
                for _ in range(5):
                    parent = await current_element.query_selector('xpath=..')
                    if parent:
                        parent_text = await parent.text_content()
                        if re.search(r'\d{3}\.', parent_text):
                            text_content = parent_text
                            break
                        current_element = parent
                    else:
                        break
                if not text_content:
                    text_content = await link.text_content()

                date_match = re.search(r'(\d{3})\.(\d{1,2})\.(\d{1,2})', text_content)
                if date_match:
                    roc_year = int(date_match.group(1))
                    month = int(date_match.group(2))
                    day = int(date_match.group(3))
                    ad_year = roc_year + 1911
                    try:
                        full_date = datetime(ad_year, month, day)
                        date_str = full_date.strftime('%Y-%m-%d')
                        available_dates.add(date_str)
                        results.append({
                            'date': date_str,
                            'weekday': full_date.weekday() + 1,
                            'status': 'available',
                            'days_from_today': (full_date.date() - datetime.now().date()).days
                        })
                    except ValueError:
                        continue

            # 再抓額滿的項目
            full_elements = await self.page.query_selector_all('*:has-text("額滿")')
            for el in full_elements:
                text_content = await el.text_content()
                if '額滿' not in text_content:
                    continue
                date_match = re.search(r'(\d{3})\.(\d{1,2})\.(\d{1,2})', text_content)
                if date_match:
                    roc_year = int(date_match.group(1))
                    month = int(date_match.group(2))
                    day = int(date_match.group(3))
                    ad_year = roc_year + 1911
                    try:
                        full_date = datetime(ad_year, month, day)
                        date_str = full_date.strftime('%Y-%m-%d')
                        if date_str not in available_dates:
                            available_dates.add(date_str)
                            results.append({
                                'date': date_str,
                                'weekday': full_date.weekday() + 1,
                                'status': 'full',
                                'days_from_today': (full_date.date() - datetime.now().date()).days
                            })
                    except ValueError:
                        continue

            results.sort(key=lambda x: x['date'])
            logger.info(f"取得醫師門診時間表: {len(results)} 筆（可預約 {sum(1 for r in results if r['status']=='available')} 筆，額滿 {sum(1 for r in results if r['status']=='full')} 筆）")
            return results

        except Exception as e:
            logger.error(f"取得醫師門診時間表失敗: {e}")
            return []

    async def fetch_doctor_schedule(self) -> List[Dict]:
        """啟動瀏覽器、導航並回傳完整門診時間表"""
        try:
            is_cloud = os.getenv('CLOUD_DEPLOYMENT', 'false').lower() == 'true'
            await self.init_browser(headless=True)
            if not await self.navigate_to_doctor_schedule():
                return []
            return await self.get_all_doctor_schedule()
        finally:
            await self.close_browser()

    async def fetch_sections(self) -> List[Dict]:
        """抓取所有科別清單"""
        import re
        try:
            await self.init_browser(headless=True)
            await self.page.goto('https://register.vghtc.gov.tw/register/listSection.jsp')
            await self.page.wait_for_load_state('networkidle')

            links = await self.page.query_selector_all('a[href*="section="]')
            sections = []
            for link in links:
                href = await link.get_attribute('href')
                name = (await link.text_content() or '').strip()
                match = re.search(r'section=([A-Z0-9]+)', href or '')
                if match and name:
                    sections.append({'code': match.group(1), 'name': name})
            logger.info(f"取得科別清單: {len(sections)} 個")
            return sections
        finally:
            await self.close_browser()

    async def fetch_doctors_by_section(self, section_code: str) -> List[Dict]:
        """抓取指定科別的醫師清單"""
        import re
        try:
            await self.init_browser(headless=True)
            await self.page.goto('https://register.vghtc.gov.tw/register/listSection.jsp')
            await self.page.wait_for_load_state('networkidle')
            await self.page.click(f'a[href*="section={section_code}"]')
            await self.page.wait_for_load_state('networkidle')

            # 醫師元素以醫師代碼為 id，元素類型不固定，查所有帶 id 的元素
            all_with_id = await self.page.query_selector_all('[id]')
            doctors = []
            debug_ids = []
            for el in all_with_id:
                el_id = (await el.get_attribute('id') or '').strip()
                if not el_id:
                    continue
                debug_ids.append(el_id)
                # 醫師代碼格式：4~8 位，由數字和大寫英文組成，且包含至少一個數字
                if re.match(r'^[0-9A-Z]{4,8}$', el_id) and re.search(r'[0-9]', el_id) and re.search(r'[A-Z]', el_id):
                    name = (await el.text_content() or '').strip()
                    if not name:
                        # 嘗試從父元素取名稱
                        parent = await el.query_selector('xpath=..')
                        if parent:
                            name = (await parent.text_content() or '').strip()
                    name = name.split('\n')[0].strip()
                    if name:
                        doctors.append({'code': el_id, 'name': name})

            # 依 code 去重，保留第一筆
            seen = set()
            unique_doctors = []
            for d in doctors:
                if d['code'] not in seen:
                    seen.add(d['code'])
                    unique_doctors.append(d)

            logger.info(f"取得 {section_code} 科醫師清單: {len(unique_doctors)} 位（去重前 {len(doctors)} 筆）")
            return unique_doctors
        finally:
            await self.close_browser()

    async def auto_register_by_date_range(self, target_weekdays: List[int], start_date: str = None, end_date: str = None):
        """在指定日期範圍內自動掛號"""
        try:
            weekday_names = {1: '一', 2: '二', 3: '三', 4: '四', 5: '五', 6: '六', 7: '日'}
            target_days = [weekday_names[w] for w in target_weekdays]
            self.update_progress("開始", 5, f"開始自動掛號 - 目標星期: {', '.join(target_days)}")
            
            # 雲端環境使用 headless 模式
            is_cloud = os.getenv('CLOUD_DEPLOYMENT', 'false').lower() == 'true'
            self.update_progress("環境檢查", 10, f"執行環境: {'雲端模式 (headless)' if is_cloud else '本地模式'}")
            
            self.update_progress("啟動瀏覽器", 15, "正在啟動瀏覽器...")
            await self.init_browser(headless=True)
            self.update_progress("瀏覽器就緒", 25, "瀏覽器啟動成功")

            self.update_progress("導航", 30, "正在導航到醫師門診時間表...")
            if not await self.navigate_to_doctor_schedule():
                self.update_progress("錯誤", 0, "導航到醫師門診時間表失敗")
                return False
            self.update_progress("導航完成", 40, "成功到達醫師門診時間表")

            self.update_progress("搜尋時段", 50, f"正在搜尋 {start_date} 到 {end_date} 的可預約時間...")
            appointments = await self.get_available_appointments(target_weekdays, start_date, end_date)

            if not appointments:
                self.update_progress("未找到", 0, "沒有找到可預約的門診時間")
                return False

            # 按日期排序
            appointments.sort(key=lambda x: x['date'])
            self.update_progress("時段分析", 60, f"找到 {len(appointments)} 個可預約時段，開始批量掛號")

            success_count = 0
            total_appointments = len(appointments)
            
            for i, appointment in enumerate(appointments):
                try:
                    current_progress = 60 + (i * 30 // total_appointments)  # 60-90% 用於掛號過程
                    self.update_progress("掛號中", current_progress, f"正在掛號 {appointment['date']} ({i+1}/{total_appointments})")
                    
                    # 每次掛號前重新導航到醫師頁面 (除了第一次)
                    if i > 0:
                        self.update_progress("重新導航", current_progress, f"重新導航到醫師門診時間表...")
                        if not await self.navigate_to_doctor_schedule():
                            self.update_progress("錯誤", current_progress, "重新導航失敗，跳過後續掛號")
                            break
                        
                        # 重新取得預約連結
                        fresh_appointments = await self.get_available_appointments(target_weekdays, start_date, end_date)
                        
                        # 找到對應的預約 (根據日期匹配)
                        current_appointment = None
                        for fresh_apt in fresh_appointments:
                            if fresh_apt['date'] == appointment['date']:
                                current_appointment = fresh_apt
                                break
                        
                        if not current_appointment:
                            self.update_progress("跳過", current_progress, f"重新導航後找不到 {appointment['date']} 的預約，可能已被掛走")
                            continue
                        
                        appointment = current_appointment
                    
                    if await self.make_appointment(appointment):
                        success_count += 1
                        self.update_progress("成功", current_progress, f"成功掛號 {appointment['date']} ({success_count}/{total_appointments} 成功)")
                    else:
                        self.update_progress("失敗", current_progress, f"掛號 {appointment['date']} 失敗")

                    # 每次掛號後稍作休息
                    await asyncio.sleep(3)
                    
                except Exception as e:
                    self.update_progress("錯誤", current_progress, f"掛號 {appointment['date']} 時發生錯誤: {str(e)}")
                    continue

            final_message = f"掛號完成！成功 {success_count}/{total_appointments} 個門診"
            self.update_progress("完成", 100, final_message)
            return success_count > 0

        except Exception as e:
            self.update_progress("錯誤", 0, f"自動掛號過程發生錯誤: {str(e)}")
            return False
        finally:
            await self.close_browser()

    async def register_specific_date(self, target_date: str):
        """掛指定日期的號"""
        try:
            self.update_progress("開始", 5, f"開始立即掛號流程 - 目標日期: {target_date}")
            
            # 雲端環境使用 headless 模式
            is_cloud = os.getenv('CLOUD_DEPLOYMENT', 'false').lower() == 'true'
            self.update_progress("環境檢查", 10, f"執行環境: {'雲端模式 (headless)' if is_cloud else '本地模式'}")
            
            self.update_progress("啟動瀏覽器", 15, "正在啟動瀏覽器...")
            await self.init_browser(headless=True)
            self.update_progress("瀏覽器就緒", 25, "瀏覽器啟動成功")

            self.update_progress("導航", 30, "正在導航到醫師門診時間表...")
            if not await self.navigate_to_doctor_schedule():
                self.update_progress("錯誤", 0, "導航到醫師門診時間表失敗")
                return False
            self.update_progress("導航完成", 50, "成功到達醫師門診時間表")

            # 取得所有可預約時間 (搜尋指定日期前後30天)
            self.update_progress("搜尋時段", 60, "正在搜尋可預約時間...")
            from datetime import datetime, timedelta
            target_dt = datetime.strptime(target_date, '%Y-%m-%d')
            start_date = (target_dt - timedelta(days=1)).strftime('%Y-%m-%d')  # 前一天
            end_date = (target_dt + timedelta(days=30)).strftime('%Y-%m-%d')   # 後30天
            
            appointments = await self.get_available_appointments([1, 2, 3, 4, 5, 6, 7], start_date, end_date)  # 所有星期
            self.update_progress("時段分析", 70, f"找到 {len(appointments)} 個可預約時段")

            # 尋找指定日期
            self.update_progress("尋找目標", 75, f"搜尋目標日期 {target_date} 的可預約時段...")
            target_appointment = None
            for appointment in appointments:
                if appointment['date'] == target_date:
                    target_appointment = appointment
                    self.update_progress("找到目標", 80, f"找到目標日期的預約時段")
                    break

            if not target_appointment:
                self.update_progress("未找到", 0, f"找不到 {target_date} 的可預約門診。建議檢查該日期是否為門診日或已開放預約")
                return False

            self.update_progress("開始掛號", 85, "正在進行掛號...")
            result = await self.make_appointment(target_appointment)
            
            if result:
                self.update_progress("成功", 100, "掛號成功！")
            else:
                self.update_progress("失敗", 0, "掛號失敗")
                
            return result

        except Exception as e:
            self.update_progress("錯誤", 0, f"掛號過程發生錯誤: {str(e)}")
            import traceback
            logger.error(f"詳細錯誤: {traceback.format_exc()}")
            return False
        finally:
            self.update_progress("清理", 95, "正在關閉瀏覽器...")
            await self.close_browser()
            if not hasattr(self, '_final_status_set'):
                self.update_progress("完成", 100, "瀏覽器已關閉，掛號流程結束")

# 排程功能


class ScheduleManager:
    def __init__(self, auto_register: VGHTCAutoRegister):
        self.auto_register = auto_register
        self.running = False
        self.thread = None

    def start_schedule(self):
        """啟動排程"""
        if self.running:
            logger.warning("排程已在運行中")
            return

        config = self.auto_register.config['schedule']
        if not config['enabled']:
            logger.warning("排程功能未啟用")
            return

        # 設定每日檢查時間
        schedule.every().day.at(config['check_time']).do(
            self._run_scheduled_register)

        self.running = True
        self.thread = threading.Thread(target=self._schedule_loop, daemon=True)
        self.thread.start()

        logger.info(f"排程已啟動，每日 {config['check_time']} 執行自動掛號")

    def stop_schedule(self):
        """停止排程"""
        self.running = False
        schedule.clear()
        logger.info("排程已停止")

    def _schedule_loop(self):
        """排程循環"""
        while self.running:
            schedule.run_pending()
            time.sleep(60)  # 每分鐘檢查一次

    def _run_scheduled_register(self):
        """執行排程掛號"""
        config = self.auto_register.config['schedule']
        asyncio.run(self.auto_register.auto_register_by_date_range(
            config['target_weekdays'],
            config['start_date'],
            config['end_date']
        ))


if __name__ == "__main__":
    # 測試用
    auto_register = VGHTCAutoRegister()

    # 範例：掛指定日期
    # asyncio.run(auto_register.register_specific_date('2025-12-09'))

    # 範例：自動掛號（星期二、三、五）
    # asyncio.run(auto_register.auto_register_by_date_range([2, 3, 5]))

    print("台中榮總自動掛號系統已載入")
    print("請使用 web_interface.py 啟動網頁介面")

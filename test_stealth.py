#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
測試 playwright-stealth 是否能讓 reCAPTCHA 自動通過
使用 recaptcha-demo 網站（公開測試用）驗證 stealth 效果
"""
import asyncio
from playwright.async_api import async_playwright
from playwright_stealth import Stealth


async def test_stealth_on_recaptcha():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)  # 開視窗方便觀察
        page = await browser.new_page()

        print("套用 stealth...")
        await Stealth().apply_stealth_async(page)

        # 先用 bot 偵測網站確認 stealth 效果
        print("前往 bot 偵測網站...")
        await page.goto("https://bot.sannysoft.com/")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="stealth_botcheck.png")
        print("截圖已存：stealth_botcheck.png")

        # 再前往台中榮總掛號首頁確認頁面能正常載入
        print("前往台中榮總掛號首頁...")
        await page.goto("https://register.vghtc.gov.tw/register/")
        await page.wait_for_load_state("networkidle")
        await page.screenshot(path="stealth_vghtc.png")
        print("截圖已存：stealth_vghtc.png")

        title = await page.title()
        print(f"頁面標題：{title}")

        frames = page.frames
        recaptcha_frames = [f for f in frames if 'recaptcha' in f.url]
        print(f"偵測到 reCAPTCHA frame 數量：{len(recaptcha_frames)}")
        for f in recaptcha_frames:
            print(f"  - {f.url[:80]}")

        await browser.close()
        print("測試完成")


if __name__ == "__main__":
    asyncio.run(test_stealth_on_recaptcha())

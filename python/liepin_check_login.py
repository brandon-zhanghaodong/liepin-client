#!/usr/bin/env python3
"""
猎聘登录 — 手机号+验证码
先检查登录页结构，然后自动填号+发码
"""

import time, requests, json
from pathlib import Path
from playwright.sync_api import sync_playwright

CHROME_PORT = 9222
PHONE = "1812600131"  # 等一下，我检查下代码...先看看页面

OUTPUT_DIR = Path(__file__).parent.parent / "candidates"

def main():
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{CHROME_PORT}")
        context = browser.contexts[0]
        page = context.new_page()
        
        print("🌐 打开猎聘登录页...")
        page.goto("https://h.liepin.com/account/login", wait_until="domcontentloaded")
        time.sleep(3)
        
        # 截图看看页面长什么样
        page.screenshot(path=f"{OUTPUT_DIR}/login_page.png")
        print("📸 已截图: login_page.png")
        
        # 打印页面上所有可交互元素
        print("\n🔍 分析页面可交互元素...")
        elements = page.evaluate("""() => {
            const inputs = document.querySelectorAll('input, button, a, [role="button"]');
            return Array.from(inputs).map(el => ({
                tag: el.tagName,
                type: el.type || '',
                placeholder: el.placeholder || '',
                text: el.innerText?.trim()?.substring(0, 50) || '',
                id: el.id || '',
                className: el.className?.substring(0, 80) || '',
                name: el.name || '',
                visible: el.offsetParent !== null
            }));
        }""")
        
        for el in elements:
            if el['visible']:
                print(f"  <{el['tag']}> id={el['id']} type={el['type']} placeholder={el['placeholder']} text={el['text'][:30]} class={el['className'][:40]}")
        
        # 打印全部文字
        body = page.inner_text("body")
        print(f"\n📄 页面文字内容:\n{body[:1500]}")
        
        input("\n按 Enter 继续...")
        page.close()

if __name__ == "__main__":
    main()

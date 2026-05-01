#!/usr/bin/env python3
"""
猎聘搜索 - Playwright方案 (已连接Chrome实例)
连接已有Chrome实例，通过CDP协议控制
"""
import time, csv
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

PORT = 9222  # Chrome远程调试端口
KW = "字节跳动 HRD"  # 默认搜索关键词
OUT = Path(__file__).parent.parent / "candidates"

def search_liepin(keyword, headless=False):
    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    print("="*60)
    print(f"猎聘搜索: {keyword}")
    print("="*60)
    
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        context = browser.contexts[0]
        page = context.new_page()
        
        # 打开找简历页面（猎头端的搜索页面）
        print("\n🌐 打开猎聘找简历页面...")
        page.goto("https://h.liepin.com/search/getConditionItem", wait_until="domcontentloaded")
        time.sleep(3)
        
        # 找到搜索框
        print("🔍 找搜索框...")
        search_input = page.query_selector('.search-component-input, input.search-component-input')
        if not search_input:
            print("  ❌ 未找到搜索框")
            page.close()
            return []
        
        print("  ✅ 找到搜索框!")
        
        # 点击并清空
        search_input.click()
        time.sleep(0.3)
        page.keyboard.press("Control+a")
        time.sleep(0.2)
        search_input.fill("")
        time.sleep(0.2)
        
        # 输入关键词
        search_input.type(keyword, delay=80)
        print(f"  ✅ 输入: {keyword}")
        time.sleep(0.5)
        
        # 按回车
        page.keyboard.press("Enter")
        print("  ✅ 按回车")
        
        time.sleep(5)
        
        # 截图
        sp = f"{OUT}/liepin_search_{ts}.png"
        page.screenshot(path=sp, full_page=True)
        print(f"  截图: {sp}")
        
        # 提取候选人
        print("\n📋 提取候选人...")
        body = page.inner_text("body")
        
        candidates = []
        current = {}
        
        lines = body.split("\n")
        for line in lines:
            line = line.strip()
            if not line or len(line) < 2:
                continue
            if any(char in line for char in ['岁', '年经验']) and len(line) < 50:
                if current and current.get("姓名"):
                    candidates.append(current)
                current = {"姓名": line.split("岁")[0].strip() if "岁" in line else ""}
            if "·" in line and len(line) < 60:
                if current and not current.get("公司"):
                    current["公司"] = line
            if any(kw in line for kw in ["总监", "经理", "VP", "CTO", "COO", "总裁", "总经理", "HRD", "CHO", "负责人"]):
                if current and not current.get("职位"):
                    current["职位"] = line
            if "平安" in line:
                if current:
                    current["平安相关"] = True
        
        if current and current.get("姓名"):
            candidates.append(current)
        
        print(f"\n找到 {len(candidates)} 个候选人:")
        pingan = [c for c in candidates if c.get("平安相关") or (c.get("公司") and "平安" in c.get("公司",""))]
        
        for i, c in enumerate(candidates[:20]):
            mark = " 🅿️" if c.get("平安相关") else ""
            print(f"  [{i+1}] {c.get('姓名','?')} | {c.get('职位','?')} | {c.get('公司','?')}{mark}")
        
        if pingan:
            print(f"\n🎯 平安背景候选人 ({len(pingan)}人):")
            for c in pingan:
                print(f"  - {c.get('姓名')} | {c.get('职位')} | {c.get('公司')}")
        
        # 保存CSV
        if candidates:
            csv_path = f"{OUT}/liepin_search_{ts}.csv"
            with open(csv_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(["姓名", "职位", "公司", "关键词", "时间"])
                for c in candidates:
                    w.writerow([c.get("姓名",""), c.get("职位",""), c.get("公司",""), keyword, datetime.now().isoformat()])
            print(f"\n📁 CSV: {csv_path}")
        
        page.close()
        return candidates
    
    print("\n✅ 完成!")

if __name__ == "__main__":
    import sys
    keyword = sys.argv[1] if len(sys.argv) > 1 else KW
    search_liepin(keyword)

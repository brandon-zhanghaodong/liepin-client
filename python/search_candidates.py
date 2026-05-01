#!/usr/bin/env python3
"""
猎聘候选人自动搜索（Python + Playwright）
由 Electron 主进程调用，连接本机已登录的 Chrome 实例
"""

import json
import sys
import time
from datetime import datetime
from pathlib import Path


def log(msg):
    print(f"[playwright] {msg}", flush=True)


def search_liepin(keyword=None, max_results=50, cdp_port=9222, output_dir=None):
    """
    通过 CDP 连接到已打开的 Chrome，在猎聘搜索候选人
    """
    from playwright.sync_api import sync_playwright

    if not keyword:
        keyword = "HRD"

    if not output_dir:
        output_dir = str(Path.home() / "Documents" / "liepin_candidates")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    with sync_playwright() as p:
        log(f"🔗 连接 Chrome CDP ws://127.0.0.1:{cdp_port}")
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")

        if len(browser.contexts) == 0:
            log("❌ 没有浏览器上下文")
            return []

        context = browser.contexts[0]
        page = context.new_page()

        try:
            log(f"🔍 搜索: {keyword}")
            page.goto("https://h.liepin.com/search/getConditionItem",
                       wait_until="domcontentloaded", timeout=30000)
            time.sleep(3)

            # 点击搜索框（ant-select）
            coords = page.evaluate("""() => {
                const el = document.querySelector('#rc_select_1');
                if (!el) return null;
                const p = el.closest('.ant-select');
                if (!p) return null;
                const r = p.getBoundingClientRect();
                return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
            }""")

            if coords:
                page.mouse.click(coords["x"], coords["y"])
                time.sleep(0.5)
                page.keyboard.type(keyword, delay=80)
                time.sleep(0.5)
                page.keyboard.press("Enter")
                time.sleep(1)

            # 点搜索按钮
            search_btn = page.query_selector("button:has-text('搜 索')")
            if search_btn:
                search_btn.click()
                log("✅ 搜索按钮已点击")
            else:
                page.keyboard.press("Enter")

            time.sleep(5)

            # 提取候选人
            cards = page.query_selector_all(".tlog-common-resume-card")
            log(f"📋 找到 {len(cards)} 个候选人卡片")

            for i, card in enumerate(cards[:max_results]):
                try:
                    name_el = card.query_selector(".new-resume-personal-name")
                    name = name_el.inner_text().strip() if name_el else ""

                    detail_el = card.query_selector(".new-resume-personal-detail")
                    detail = detail_el.inner_text().strip() if detail_el else ""

                    expect_el = card.query_selector(".new-resume-personal-expect")
                    expect = expect_el.inner_text().strip() if expect_el else ""

                    skills_el = card.query_selector(".new-resume-personal-skills")
                    skills = skills_el.inner_text().strip() if skills_el else ""

                    candidate = {
                        "index": i + 1,
                        "name": name,
                        "detail": detail,
                        "expect": expect,
                        "skills": skills,
                    }
                    results.append(candidate)
                    log(f"  [{i+1}] {name} | {detail[:80]}")
                except Exception as e:
                    log(f"  ⚠️ 解析卡片 {i+1} 出错: {e}")

            # 保存截图
            screenshot_path = str(Path(output_dir) / f"search_{timestamp}.png")
            page.screenshot(path=screenshot_path)
            log(f"📸 截图: {screenshot_path}")

        except Exception as e:
            log(f"❌ 搜索出错: {e}")
        finally:
            page.close()

    return results


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="猎聘候选人搜索")
    parser.add_argument("--keyword", default="HRD", help="搜索关键词")
    parser.add_argument("--max", type=int, default=50, help="最大结果数")
    parser.add_argument("--cdp-port", type=int, default=9222, help="Chrome CDP 端口")
    parser.add_argument("--output", default=None, help="输出目录")
    parser.add_argument("--json", action="store_true", help="以 JSON 格式输出")

    args = parser.parse_args()

    candidates = search_liepin(
        keyword=args.keyword,
        max_results=args.max,
        cdp_port=args.cdp_port,
        output_dir=args.output,
    )

    output = {
        "keyword": args.keyword,
        "timestamp": datetime.now().isoformat(),
        "total": len(candidates),
        "candidates": candidates,
    }

    if args.json:
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"\n✅ 搜索完成: 共 {len(candidates)} 个候选人")

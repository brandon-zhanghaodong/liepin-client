#!/usr/bin/env python3
"""
猎聘候选人搜索 - 已验证✅ 正确操作方式 (2026-05-01)
使用已有 Chrome 会话（无需重新登录）

内置自检机制 + 自动重试（最多2次）

用法：
  python3 liepin_search_connected.py <关键词>

示例：
  python3 liepin_search_connected.py "字节跳动 HRD"
  python3 liepin_search_connected.py "人工智能 CTO"
"""

import time, csv, sys, requests, json
from datetime import datetime
from pathlib import Path
from playwright.sync_api import sync_playwright

PORT = 9222
OUT = Path(__file__).parent.parent / "candidates"
BITABLE = ("WXHObDl8eahIVEs06phcpzPDncb", "tblxmUAD1XrA4XTP")
CANDIDATE_SELECTOR = ".tlog-common-resume-card"
MAX_RETRIES = 2  # 每个步骤最多重试次数

# ── 飞书认证 ─────────────────────────────────────────────────────────────────

def get_token():
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": "cli_a917170b57f89cd6", "app_secret": "5jo3BXlMlZUuwYWsdVrQQc07Rn4HM3Qz"},
        timeout=10
    )
    return r.json().get("tenant_access_token", "")

def bitable_add(fields):
    app, tbl = BITABLE
    t = get_token()
    r = requests.post(
        f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app}/tables/{tbl}/records",
        headers={"Authorization": f"Bearer {t}", "Content-Type": "application/json"},
        json={"fields": fields}, timeout=10
    )
    return r.json()

# ── 自检函数 ────────────────────────────────────────────────────────────────

def verify_search_box_coords(page) -> bool:
    """验证搜索框坐标有效（x>0 且 coords 不为 None）"""
    coords = get_search_box_coords(page)
    if not coords:
        print("  ❌ verify_search_box_coords: 坐标为空")
        return False
    if coords.get("x", 0) <= 0:
        print(f"  ❌ verify_search_box_coords: x坐标无效 {coords}")
        return False
    # y 可以是负值（元素在视口上方），只要 x 有效就能点击
    return True

def verify_page_loaded(page) -> bool:
    """验证 找人 页面已正确加载"""
    if "search/getConditionItem" not in page.url:
        print(f"  ❌ verify_page_loaded: URL 不对 {page.url}")
        return False
    el = page.query_selector("#rc_select_1")
    if not el:
        print("  ❌ verify_page_loaded: 找不到 #rc_select_1")
        return False
    return True

def verify_search_success(page) -> bool:
    """验证搜索成功：候选人卡片数量 > 0"""
    count = page.evaluate(f"() => document.querySelectorAll('{CANDIDATE_SELECTOR}').length")
    if count == 0:
        print(f"  ❌ verify_search_success: 没有候选人卡片")
        return False
    print(f"  ✅ verify_search_success: 找到 {count} 个候选人卡片")
    return True

def verify_candidate_data(candidates: list) -> bool:
    """验证候选人数据完整性"""
    if not candidates:
        print("  ❌ verify_candidate_data: 候选人为空")
        return False
    first = candidates[0]
    if not first.get("name"):
        print("  ❌ verify_candidate_data: 第一个候选人缺少 name")
        return False
    if not first.get("detail"):
        print("  ❌ verify_candidate_data: 第一个候选人缺少 detail")
        return False
    if not first.get("expect"):
        print("  ❌ verify_candidate_data: 第一个候选人缺少 expect")
        return False
    return True

# ── 带重试的执行封装 ─────────────────────────────────────────────────────────

def with_retry(verify_fn, retry_fn, step_name: str) -> bool:
    """验证失败时重试（最多 MAX_RETRIES 次）"""
    for attempt in range(MAX_RETRIES + 1):
        if verify_fn():
            return True
        if attempt < MAX_RETRIES:
            print(f"  ⚠️  {step_name} 验证失败，第 {attempt + 1} 次重试...")
            retry_fn()
    return False

# ── 核心搜索逻辑 ─────────────────────────────────────────────────────────────

def get_search_box_coords(page):
    """获取搜索框中心坐标（ant-select 组件不能直接 click，要用坐标）"""
    return page.evaluate("""() => {
        const el = document.querySelector('#rc_select_1');
        if (!el) return null;
        const parent = el.closest('.ant-select');
        if (!parent) return null;
        const r = parent.getBoundingClientRect();
        return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
    }""")

def search_liepin(keyword):
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{PORT}")
        ctx = browser.contexts[0]

        # 使用找人页面 tab
        if len(ctx.pages) > 2:
            page = ctx.pages[2]
        else:
            page = ctx.new_page()

        # ── Step 1: 导航 ──────────────────────────────────────────────────
        print("[Step 1] 导航到搜索页...")
        if "search/getConditionItem" not in page.url:
            page.goto("https://h.liepin.com/search/getConditionItem", wait_until="domcontentloaded")
            page.wait_for_timeout(3000)

        if not with_retry(
            lambda: verify_page_loaded(page),
            lambda: page.goto("https://h.liepin.com/search/getConditionItem", wait_until="domcontentloaded") or page.wait_for_timeout(3000),
            "页面加载"
        ):
            print("❌ 页面加载失败，退出")
            return []

        # ── Step 2: 验证搜索框坐标 ─────────────────────────────────────────
        print("[Step 2] 检查搜索框坐标...")
        coords = get_search_box_coords(page)
        if not coords:
            print("❌ 找不到搜索框坐标")
            return []

        if not with_retry(
            lambda: verify_search_box_coords(page),
            lambda: page.wait_for_timeout(1000),
            "搜索框坐标"
        ):
            print("❌ 搜索框坐标无效，退出")
            return []

        print(f"  ✅ 搜索框坐标: ({coords['x']:.0f}, {coords['y']:.0f})")

        # ── Step 3: 输入关键词 ─────────────────────────────────────────────
        print(f"[Step 3] 输入关键词: {keyword}")
        page.mouse.click(coords['x'], coords['y'])
        page.wait_for_timeout(1500)

        # ⚠️ 关键修复：先清除旧输入，否则关键词会叠加
        page.keyboard.press("Meta+a")
        page.wait_for_timeout(300)
        page.keyboard.press("Backspace")
        page.wait_for_timeout(500)

        page.keyboard.type(keyword, delay=80)
        page.wait_for_timeout(1000)

        # ── Step 4: 按回车 ────────────────────────────────────────────────
        print("[Step 4] 按回车...")
        page.keyboard.press("Enter")
        page.wait_for_timeout(2000)

        # ── Step 5: 点搜索按钮 ────────────────────────────────────────────
        print("[Step 5] 点击搜索按钮...")
        btn = page.query_selector("button:has-text('搜 索')")
        if btn:
            btn.click()
        page.wait_for_timeout(5000)

        # ── Step 6: 验证搜索成功 ──────────────────────────────────────────
        print("[Step 6] 验证搜索结果...")
        if not with_retry(
            lambda: verify_search_success(page),
            lambda: (
                page.keyboard.press("Enter"),
                page.wait_for_timeout(2000),
                btn.click() if btn else None,
                page.wait_for_timeout(5000)
            ),
            "搜索结果"
        ):
            print("❌ 搜索未返回有效结果")
            return []

        # ── Step 7: 提取候选人 ────────────────────────────────────────────
        print("[Step 7] 提取候选人数据...")
        candidates = page.evaluate(f"""() => {{
            const cards = document.querySelectorAll('{CANDIDATE_SELECTOR}');
            return Array.from(cards).slice(0, 30).map(card => ({{
                name: card.querySelector('.new-resume-personal-name')?.innerText?.trim() || '',
                detail: card.querySelector('.new-resume-personal-detail')?.innerText?.trim() || '',
                expect: card.querySelector('.new-resume-personal-expect')?.innerText?.trim() || '',
                skills: card.querySelector('.new-resume-personal-skills')?.innerText?.trim() || ''
            }}));
        }}""")

        if not with_retry(
            lambda: verify_candidate_data(candidates),
            lambda: None,  # 数据问题不重试，直接失败
            "候选人数据"
        ):
            print("❌ 候选人数据不完整")
            return []

        print(f"  ✅ 共提取 {len(candidates)} 个候选人")
        return candidates

def save_and_import(candidates, keyword):
    if not candidates:
        print("❌ 没有候选人数据")
        return

    ts = datetime.now().strftime('%Y%m%d_%H%M%S')
    csv_path = f"{OUT}/liepin_{keyword.replace(' ', '_')}_{ts}.csv"

    with open(csv_path, 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(["姓名", "详情", "期望职位", "技能标签", "关键词", "时间"])
        for c in candidates:
            w.writerow([c['name'], c['detail'], c['expect'], c['skills'], keyword, datetime.now().isoformat()])

    print(f"✅ CSV已保存: {csv_path}")
    print(f"📊 共找到 {len(candidates)} 个候选人")

    # 打印前10个
    print("\n前10个候选人:")
    for i, c in enumerate(candidates[:10], 1):
        # 解析 detail
        detail_parts = c['detail'].split('\n')
        age = detail_parts[0] if len(detail_parts) > 0 else ''
        years = detail_parts[1] if len(detail_parts) > 1 else ''
        edu = detail_parts[2] if len(detail_parts) > 2 else ''
        location = detail_parts[3] if len(detail_parts) > 3 else ''
        print(f"  {i}. {c['name']} | {age} | {years} | {edu} | {location}")
        print(f"     期望: {c['expect'].replace('求职期望：', '')}")

def main():
    if len(sys.argv) < 2:
        print("用法: python3 liepin_search_connected.py <关键词>")
        print("示例: python3 liepin_search_connected.py '字节跳动 HRD'")
        sys.exit(1)

    keyword = sys.argv[1]
    print("=" * 60)
    print(f"猎聘候选人搜索 | 关键词: {keyword}")
    print("=" * 60)

    candidates = search_liepin(keyword)
    save_and_import(candidates, keyword)

    print("\n✅ 完成!")

if __name__ == "__main__":
    main()

# ── 附录: 已验证防错手册摘要 ─────────────────────────────────────────────────
# 搜索框: 不用 element.click()，用 mouse.click(coords)
# 候选人选择器: .tlog-common-resume-card（不是 .resume-item / .candidate）
# 浏览器: 用 connect_over_cdp，不 launch 新浏览器
# 等待: 搜索后至少等 5 秒

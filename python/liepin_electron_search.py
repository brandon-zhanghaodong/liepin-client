#!/usr/bin/env python3
"""
招聘工厂 · Electron 客户端搜索桥接
被 main.js 的 runPythonScript 调用

用法:
  python3 liepin_electron_search.py <keyword> [max_count]

输出:
  JSON 到 stdout，包含搜索结果或错误信息
"""

import sys
import json
import os
import csv
import re
import time
import random
from datetime import datetime
from pathlib import Path

# ── 搜索核心（不要导入 liepin_client_gui，因为 tkinter 可能不可用）──
STORAGE_PATH = os.path.expanduser("~/.liepin_client/liepin_storage.json")
OUTPUT_DIR = Path.home() / ".liepin_client" / "candidates"
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/7b488565d8454ef7a70d43f9539ec61e"
CONFIG_FILE = os.path.expanduser("~/.liepin_client/config.json")


def load_storage_cookies():
    if os.path.exists(STORAGE_PATH):
        try:
            with open(STORAGE_PATH) as f:
                data = json.load(f)
            return data.get("cookies", [])
        except:
            pass
    return []


def save_storage_cookies(ctx):
    try:
        cookies = ctx.cookies()
        state = {"cookies": cookies, "updated": datetime.now().isoformat()}
        os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
        with open(STORAGE_PATH, "w") as f:
            json.dump(state, f, ensure_ascii=False)
        return len(cookies)
    except:
        return 0


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except:
            pass
    return {"wecom_webhook": ""}


def save_csv(candidates, keyword):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_kw = re.sub(r"[^\w]", "_", keyword)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUTPUT_DIR / f"liepin_{safe_kw}_{ts}.csv"
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=[
            "name", "age", "years", "edu", "location",
            "company", "position", "expect", "salary", "active", "link"
        ])
        w.writeheader()
        w.writerows(candidates)
    return csv_path


def sync_to_feishu(candidates, keyword):
    import requests
    results = {"bitable": 0, "group": False}
    app_token = "WXHObDl8eahIVEs06phcpzPDncb"
    table_id = "tblxmUAD1XrA4XTP"
    try:
        r = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": "cli_a917170b57f89cd6", "app_secret": "5jo3BXlMlZUuwYWsdVrQQc07Rn4HM3Qz"},
            timeout=10
        )
        token = r.json().get("tenant_access_token", "")
        if token:
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            now_ms = int(time.time() * 1000)
            records = []
            for c in candidates:
                fields = {
                    "姓名": c.get("name", ""),
                    "年龄": int(c.get("age", 0)) if str(c.get("age", "")).isdigit() else None,
                    "工作年限": c.get("years", ""),
                    "学历": c.get("edu", ""),
                    "所在城市": c.get("location", ""),
                    "当前公司": c.get("company", ""),
                    "当前职位": c.get("position", ""),
                    "求职期望": c.get("expect", ""),
                    "期望薪酬": c.get("salary", ""),
                    "猎聘链接": {"link": c.get("link", ""), "text": "查看简历"},
                    "关键词": keyword,
                    "抓取时间": now_ms,
                }
                fields = {k: v for k, v in fields.items() if v not in (None, "", [])}
                records.append({"fields": fields})
            total = 0
            for i in range(0, len(records), 20):
                batch = records[i:i+20]
                resp = requests.post(
                    f"https://open.feishu.cn/open-apis/bitable/v1/apps/{app_token}/tables/{table_id}/records/batch_create",
                    headers=headers, json={"records": batch}, timeout=15
                )
                if resp.json().get("code") == 0:
                    total += len(batch)
                time.sleep(0.3)
            results["bitable"] = total
    except:
        pass
    try:
        top = candidates[:10]
        preview_lines = []
        for c in top:
            parts = []
            if c.get("name"): parts.append(c["name"])
            if c.get("age"): parts.append(f"{c['age']}岁")
            if c.get("company"): parts.append(c["company"])
            if c.get("position"): parts.append(c["position"])
            preview_lines.append("  " + " | ".join(parts))
        msg = (
            f"🔍 猎聘搜索完成\n"
            f"关键词: {keyword}\n"
            f"共 {len(candidates)} 人，入库 {results['bitable']} 人\n\n"
            f"📋 预览（前10人）:\n" + "\n".join(preview_lines)
        )
        requests.post(FEISHU_WEBHOOK, json={"msg_type": "text", "content": {"text": msg}}, timeout=10)
        results["group"] = True
    except:
        pass
    return results


def sync_to_wecom(candidates, keyword):
    config = load_config()
    webhook = config.get("wecom_webhook", "")
    if not webhook:
        return False
    try:
        import requests
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"🔍 **招聘工厂 · 猎聘搜索结果 | {now}**",
                 f"**关键词：** {keyword}",
                 f"**共找到：** {len(candidates)} 人", ""]
        for i, c in enumerate(candidates[:10], 1):
            parts = [c.get("name", "?")]
            if c.get("age"): parts.append(f"{c['age']}岁")
            if c.get("company"): parts.append(c["company"])
            if c.get("position"): parts.append(c["position"])
            lines.append(f"{i}. {' | '.join(parts)}")
        if len(candidates) > 10:
            lines.append(f"\n... 共 {len(candidates)} 人（仅显示前10人）")
        resp = requests.post(webhook, json={
            "msgtype": "markdown",
            "markdown": {"content": "\n".join(lines)}
        }, timeout=10)
        return resp.json().get("errcode") == 0
    except:
        return False


def _ensure_chromium():
    """自动检查并安装 Chromium"""
    import subprocess
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            _ = p.chromium.executable_path
            return True
    except:
        pass
    print("⏳ 正在安装 Chromium 浏览器（首次运行自动安装）...", flush=True)
    try:
        result = subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            capture_output=True, text=True, timeout=300
        )
        return result.returncode == 0
    except:
        return False


def crawl_liepin(keyword, max_count=45, progress_callback=None):
    """猎聘搜索核心 - 复制自 liepin_client_gui 但无 tkinter 依赖"""
    _ensure_chromium()
    from playwright.sync_api import sync_playwright

    candidates = []
    saved_cookies = load_storage_cookies()

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-first-run", "--no-sandbox", "--disable-setuid-sandbox",
                  "--disable-dev-shm-usage", "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        if saved_cookies:
            ctx.add_cookies(saved_cookies)

        page = ctx.new_page()
        page.goto("https://h.liepin.com/search/getConditionItem", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

        if not saved_cookies:
            save_storage_cookies(ctx)

        try:
            clear_btn = page.locator("text=清空筛选条件")
            if clear_btn.is_visible(timeout=2000):
                clear_btn.click()
                page.wait_for_timeout(1500)
        except:
            pass

        try:
            rc1 = page.locator("#rc_select_1")
            rc1.wait_for(state="visible", timeout=5000)
            rc1.focus()
            page.wait_for_timeout(500)
            rc1.clear()
            page.wait_for_timeout(500)
            rc1.fill(keyword)
            page.wait_for_timeout(400)
            actual = page.evaluate("document.getElementById('rc_select_1').value")
            if keyword not in actual:
                escaped_kw = keyword.replace("'", "\\'")
                page.evaluate(f"""
                    var el = document.getElementById('rc_select_1');
                    var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
                    setter.call(el, '{escaped_kw}');
                    el.dispatchEvent(new Event('input', {{bubbles: true}}));
                    el.dispatchEvent(new Event('change', {{bubbles: true}}));
                """)
                page.wait_for_timeout(400)
        except Exception as e:
            print(f"  [*] 输入异常: {e}", flush=True)

        try:
            page.get_by_role("button", name=re.compile("搜 索")).click(timeout=5000)
        except:
            try:
                page.locator("button").filter(has_text="搜 索").first.click(timeout=3000)
            except:
                page.keyboard.press("Enter")
        page.wait_for_timeout(5000)

        max_pages = max(1, (max_count + 29) // 30)
        for page_num in range(1, max_pages + 1):
            try:
                page.wait_for_selector("table.new-resume-card", timeout=15000)
                time.sleep(2)
            except:
                break

            rows = page.evaluate(r"""
                function() {
                    var items = [];
                    var table = document.querySelector('table.new-resume-card');
                    if (!table) return items;
                    var rows = table.querySelectorAll('tbody tr[data-tlg-ext]');
                    for (var ri = 0; ri < rows.length; ri++) {
                        var row = rows[ri];
                        try {
                            var ext = row.getAttribute('data-tlg-ext') || '';
                            var resId = '';
                            try { resId = JSON.parse(decodeURIComponent(ext)).res_id || ''; } catch(e2) {}
                            if (!resId) continue;
                            var text = row.innerText;
                            var lines = text.split('\n').map(function(l){return l.trim()}).filter(function(l){return l});
                            if (lines.length < 4) continue;
                            var name = '';
                            var ems = row.querySelectorAll('em');
                            for (var em of ems) {
                                var t = em.innerText.trim();
                                if (t.indexOf('**') >= 0 && t.length <= 6 && t.indexOf('活跃') < 0 && t.indexOf('在线') < 0) {
                                    name = t; break;
                                }
                            }
                            if (!name) continue;
                            var age='', years='', edu='', location='', expect='', salary='', company='', position='', active='';
                            var first = lines[0] || '';
                            if (first.indexOf('今天活跃') >= 0) active = '今天活跃';
                            else if (first.indexOf('3天内活跃') >= 0) active = '3天内活跃';
                            else if (first.indexOf('7天内活跃') >= 0) active = '7天内活跃';
                            else if (first.indexOf('30天内活跃') >= 0) active = '30天内活跃';
                            else if (first.indexOf('在线') >= 0) active = '在线';
                            for (var li = 0; li < lines.length; li++) {
                                var l = lines[li];
                                var m;
                                if (!age && l.match(/\u5c81/)) {
                                    m = l.match(/(\d+)\u5c81/);
                                    if (m) age = m[1];
                                }
                                if (!years && l.match(/\u5de5\u4f5c/)) {
                                    m = l.match(/\u5de5\u4f5c(\d+)\u5e74/);
                                    if (m) years = m[1];
                                }
                                if (!edu && l.match(/\u535a\u58eb|\u535a\u58eb\u540e|\u7855\u58eb|MBA|\u672c\u79d1|\u5927\u4e13/)) {
                                    edu = l;
                                }
                                if (!location && (l.indexOf('\u533a') >= 0 || l.indexOf('\u5e02') >= 0 || l.indexOf('\u7701') >= 0) && l.indexOf('\u6d3b') < 0 && l.indexOf('\u5728\u7ebf') < 0 && l.indexOf('\u5929\u5185') < 0 && l.indexOf('\u5c81') < 0 && l.indexOf('\u5de5\u4f5c') < 0) {
                                    location = l;
                                }
                                if (l.indexOf('\u6c42\u804c\u671f\u671b') >= 0) {
                                    var ex = l.split('\u6c42\u804c\u671f\u671b').pop().replace(/^[\s\u3000-\u303f]+/, '').trim();
                                    if (ex && ex.indexOf('\u5b57\u8282') < 0) expect = ex;
                                }
                                if (!salary) {
                                    m = l.match(/\d+[kK]\s*[-~\u2013\u2014]\s*\d+[kK]/);
                                    if (m) salary = m[0];
                                }
                                if (l.indexOf('\u00b7') >= 0 && (l.indexOf('\u516c\u53f8') >= 0 || l.indexOf('\u79d1\u6280') >= 0 || l.indexOf('\u96c6\u56e2') >= 0 || l.indexOf('\u80a1\u4efd') >= 0 || l.indexOf('\u94f6\u884c') >= 0)) {
                                    var parts = l.split('\u00b7');
                                    if (parts.length >= 2) {
                                        company = parts[0].trim();
                                        position = parts.slice(1).join(' \u00b7 ').trim();
                                    }
                                }
                            }
                            var link = 'https://h.liepin.com/resume/showresumedetail/?res_id_encode=' + resId;
                            items.push({name: name, age: age, years: years, edu: edu, location: location, expect: expect, salary: salary, company: company, position: position, active: active, link: link});
                        } catch(e3) {}
                    }
                    return items;
                }
            """)
            candidates.extend(rows)

            if len(candidates) >= max_count:
                candidates = candidates[:max_count]
                break

            if page_num < max_pages:
                try:
                    next_btn = page.query_selector(".ant-pagination-next")
                    if next_btn:
                        next_btn.click()
                        time.sleep(random.uniform(5, 12))
                    else:
                        break
                except:
                    break

        save_storage_cookies(ctx)
        browser.close()

    return candidates


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"status": "error", "message": "请提供关键词"}))
        sys.exit(1)

    keyword = sys.argv[1]
    max_count = int(sys.argv[2]) if len(sys.argv) > 2 and sys.argv[2].isdigit() else 45
    sync_enabled = len(sys.argv) > 3 and sys.argv[3] == "--sync"

    try:
        candidates = crawl_liepin(keyword, max_count)
        csv_path = str(save_csv(candidates, keyword)) if candidates else None

        result = {
            "status": "ok",
            "keyword": keyword,
            "count": len(candidates),
            "csv": csv_path,
            "candidates": candidates[:20],
        }

        if sync_enabled and candidates:
            feishu_result = sync_to_feishu(candidates, keyword)
            if feishu_result.get("bitable") or feishu_result.get("group"):
                result["feishu"] = feishu_result
            config = load_config()
            if config.get("wecom_webhook"):
                result["wecom"] = sync_to_wecom(candidates, keyword)

        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    except Exception as e:
        print(json.dumps({"status": "error", "message": str(e)}, ensure_ascii=False))
        sys.exit(1)


if __name__ == "__main__":
    main()

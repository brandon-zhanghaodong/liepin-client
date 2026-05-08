#!/usr/bin/env python3
"""
招聘工厂 · 猎聘搜人客户端 v1.2
终端交互版 — 无需 tkinter/PyQt，纯 CLI
首次运行自动检测并安装 Chromium
"""

import os
import sys
import json
import csv
import re
import time
import random
import subprocess
from datetime import datetime
from pathlib import Path

# ── 配置 ─────────────────────────────────────────────────────────────────
STORAGE_PATH = os.path.expanduser("~/.liepin_client/liepin_storage.json")
OUTPUT_DIR = Path.home() / ".liepin_client" / "candidates"
CONFIG_FILE = os.path.expanduser("~/.liepin_client/config.json")
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/7b488565d8454ef7a70d43f9539ec61e"

# ── 颜色 ─────────────────────────────────────────────────────────────────
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD = "\033[1m"
RESET = "\033[0m"


# ==============================================================
#  环境自检 + 自动安装
# ==============================================================

def ensure_chromium():
    """检查并自动安装 Playwright + Chromium"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            _ = p.chromium.executable_path
        return True
    except ImportError:
        print(f"{RED}❌ playwright 模块未安装{RESET}")
        print(f"   请运行: pip3 install playwright")
        return False
    except Exception:
        print(f"\n{YELLOW}⏳ 正在下载 Chromium 浏览器（约 336MB，仅首次需要）...{RESET}",
              flush=True)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                # 显示进度信息
                lines = [l for l in result.stdout.split("\n") if l.strip()]
                for l in lines[-5:]:
                    print(f"  {l}")
                print(f"{GREEN}✅ Chromium 安装完成{RESET}")
                return True
            else:
                print(f"{RED}❌ 安装失败: {result.stderr[:300]}{RESET}")
                return False
        except subprocess.TimeoutExpired:
            print(f"{RED}❌ 安装超时（5分钟），请重试{RESET}")
            return False
        except Exception as e:
            print(f"{RED}❌ 安装异常: {e}{RESET}")
            return False


# ==============================================================
#  登录态管理
# ==============================================================

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


# ==============================================================
#  猎聘搜索核心
# ==============================================================

def crawl_liepin(keyword, max_count=45):
    from playwright.sync_api import sync_playwright

    candidates = []
    saved_cookies = load_storage_cookies()
    print(f"  📥 登录态: {len(saved_cookies)} cookies")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=["--no-first-run", "--no-sandbox",
                  "--disable-setuid-sandbox", "--disable-dev-shm-usage",
                  "--disable-blink-features=AutomationControlled"]
        )
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        if saved_cookies:
            ctx.add_cookies(saved_cookies)

        page = ctx.new_page()
        print(f"  🌐 打开猎聘找简历页面...")
        page.goto("https://h.liepin.com/search/getConditionItem",
                   wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

        # 首次保存登录态
        if not saved_cookies:
            n = save_storage_cookies(ctx)
            print(f"  💾 登录态已保存 ({n} cookies)")
            print(f"  {YELLOW}⚠️  请确认浏览器已登录猎聘，然后按回车继续...{RESET}", end="")
            input()
            page.bring_to_front()

        # 清空筛选条件
        try:
            btn = page.locator("text=清空筛选条件")
            if btn.is_visible(timeout=2000):
                btn.click()
                page.wait_for_timeout(1500)
        except:
            pass

        # 输入关键词
        print(f"  ⌨️  输入: {keyword}")
        try:
            rc1 = page.locator("#rc_select_1")
            rc1.wait_for(state="visible", timeout=5000)
            rc1.focus()
            rc1.clear()
            rc1.fill(keyword)
            page.wait_for_timeout(400)
        except Exception as e:
            print(f"  ⚠️  输入异常: {e}")

        # 搜索
        print(f"  🔍 执行搜索...")
        try:
            page.get_by_role("button", name=re.compile("搜 索")).click(timeout=5000)
        except:
            try:
                page.locator("button").filter(has_text="搜 索").first.click(timeout=3000)
            except:
                page.keyboard.press("Enter")
        page.wait_for_timeout(5000)

        # 翻页提取
        max_pages = max(1, (max_count + 29) // 30)
        for page_num in range(1, max_pages + 1):
            try:
                page.wait_for_selector("table.new-resume-card", timeout=15000)
                time.sleep(2)
            except:
                print(f"  ⚠️  第{page_num}页无结果")
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
                                if (t.indexOf('**') >= 0 && t.length <= 6 && t.indexOf('活跃') < 0 && t.indexOf('在线') < 0) { name = t; break; }
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
                                var l = lines[li]; var m;
                                if (!age && l.match(/\u5c81/)) { m = l.match(/(\d+)\u5c81/); if (m) age = m[1]; }
                                if (!years && l.match(/\u5de5\u4f5c/)) { m = l.match(/\u5de5\u4f5c(\d+)\u5e74/); if (m) years = m[1]; }
                                if (!edu && l.match(/\u535a\u58eb|\u7855\u58eb|MBA|\u672c\u79d1|\u5927\u4e13/)) { edu = l; }
                                if (!location && (l.indexOf('\u533a') >= 0 || l.indexOf('\u5e02') >= 0) && l.indexOf('\u6d3b') < 0 && l.indexOf('\u5728\u7ebf') < 0 && l.indexOf('\u5929\u5185') < 0) { location = l; }
                                if (l.indexOf('\u6c42\u804c\u671f\u671b') >= 0) { var ex = l.split('\u6c42\u804c\u671f\u671b').pop().replace(/^[\s\u3000-\u303f]+/, '').trim(); if (ex) expect = ex; }
                                if (!salary) { m = l.match(/\d+[kK]\s*[-~\u2013\u2014]\s*\d+[kK]/); if (m) salary = m[0]; }
                                if (l.indexOf('\u00b7') >= 0 && (l.indexOf('\u516c\u53f8') >= 0 || l.indexOf('\u79d1\u6280') >= 0)) { var parts = l.split('\u00b7'); if (parts.length >= 2) { company = parts[0].trim(); position = parts.slice(1).join(' \u00b7 ').trim(); }}
                            }
                            var link = 'https://h.liepin.com/resume/showresumedetail/?res_id_encode=' + resId;
                            items.push({name: name, age: age, years: years, edu: edu, location: location, expect: expect, salary: salary, company: company, position: position, active: active, link: link});
                        } catch(e3) {}
                    }
                    return items;
                }
            """)
            candidates.extend(rows)
            print(f"  📄 第{page_num}页: {len(rows)}人 (累计{len(candidates)})")

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
        print(f"  🚪 关闭浏览器...")
        browser.close()

    return candidates


# ==============================================================
#  数据同步
# ==============================================================

def sync_to_feishu(candidates, keyword):
    results = {"bitable": 0, "group": False}
    try:
        import requests
        r = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": "cli_a917170b57f89cd6", "app_secret": "5jo3BXlMlZUuwYWsdVrQQc07Rn4HM3Qz"},
            timeout=10
        )
        token = r.json().get("tenant_access_token", "")
        if not token:
            print(f"  ⚠️  飞书 token 获取失败")
            return results

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
        app_token = "WXHObDl8eahIVEs06phcpzPDncb"
        table_id = "tblxmUAD1XrA4XTP"
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
        print(f"  ✅ 飞书 Bitable: {total} 条")

        # 飞书群通知
        top = candidates[:10]
        preview = "\n".join([
            f"  {c['name']} {c.get('age','?')}岁 {c.get('company','')} {c.get('position','')}"
            for c in top if c.get("name")
        ])
        msg = f"🔍 猎聘搜索完成\n关键词: {keyword}\n共 {len(candidates)} 人, 入库 {total} 人\n\n📋 预览：\n{preview}"
        requests.post(FEISHU_WEBHOOK, json={"msg_type": "text", "content": {"text": msg}}, timeout=10)
        results["group"] = True
        print(f"  ✅ 飞书群通知已发送")
    except Exception as e:
        print(f"  ⚠️  飞书同步异常: {e}")
    return results


def sync_to_wecom(candidates, keyword):
    config_path = os.path.expanduser("~/.liepin_client/config.json")
    webhook = ""
    if os.path.exists(config_path):
        try:
            with open(config_path) as f:
                webhook = json.load(f).get("wecom_webhook", "")
        except:
            pass
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
            lines.append(f"\n... 共 {len(candidates)} 人")
        resp = requests.post(webhook, json={
            "msgtype": "markdown",
            "markdown": {"content": "\n".join(lines)}
        }, timeout=10)
        ok = resp.json().get("errcode") == 0
        print(f"  {'✅' if ok else '❌'} 企微: {'成功' if ok else '失败'}")
        return ok
    except Exception as e:
        print(f"  ⚠️  企微异常: {e}")
        return False


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
    print(f"  📁 CSV: {csv_path}")
    return csv_path


# ==============================================================
#  主程序
# ==============================================================

def print_banner():
    os.system("clear" if os.name == "nt" else "clear")
    print(f"""{CYAN}
╔═══════════════════════════════════════════════════════╗
║             招聘工厂 · 猎聘搜人客户端                 ║
║             v1.2 · 独立浏览器版                       ║
╚═══════════════════════════════════════════════════════╝{RESET}
""")


def main():
    print_banner()

    # Step 1: 环境自检
    print(f"{BOLD}[1/4] 环境检测{RESET}")
    if not ensure_chromium():
        input(f"\n按回车退出...")
        return
    print()

    # Step 2: 关键词输入
    print(f"{BOLD}[2/4] 输入搜索关键词{RESET}")
    print(f"  提示：可以输入「公司 职位」格式，例如「字节跳动 HRD」")
    print(f"  输入 {CYAN}help{RESET} 查看帮助，输入 {RED}exit{RESET} 退出")

    while True:
        keyword = input(f"\n{CYAN}🔍 关键词 > {RESET}").strip()
        if not keyword:
            continue
        if keyword.lower() in ("exit", "quit", "q"):
            print(f"\n{GREEN}👋 再见！{RESET}")
            return
        if keyword.lower() == "help":
            print(f"  用法: <公司> <职位>")
            print(f"  示例: 字节跳动 HRD")
            print(f"  示例: 人工智能 CTO")
            print(f"  示例: 华为 产品经理")
            continue

        # Step 3: 搜索
        print(f"\n{BOLD}[3/4] 开始搜索{RESET}")
        print(f"{'='*50}")
        start = time.time()
        try:
            candidates = crawl_liepin(keyword)
        except Exception as e:
            print(f"\n{RED}❌ 搜索失败: {e}{RESET}")
            import traceback
            traceback.print_exc()
            continue

        elapsed = time.time() - start
        print(f"\n{'='*50}")
        print(f"📊 共找到 {len(candidates)} 人 (耗时 {elapsed:.0f}s)")

        if not candidates:
            print(f"  {YELLOW}未找到候选人，请尝试其他关键词{RESET}")
            continue

        # 预览
        print(f"\n📋 预览（前10人）:")
        for i, c in enumerate(candidates[:10], 1):
            parts = [c.get("name", "?")]
            if c.get("age"): parts.append(f"{c['age']}岁")
            if c.get("company"): parts.append(c["company"])
            if c.get("position"): parts.append(c["position"])
            print(f"  {i}. {' | '.join(parts)}")

        # Step 4: 同步
        print(f"\n{BOLD}[4/4] 数据同步{RESET}")

        # CSV 保存
        print(f"  💾 保存本地 CSV...")
        csv_path = save_csv(candidates, keyword)

        # 飞书同步
        print(f"  📤 同步到飞书...")
        sync_to_feishu(candidates, keyword)

        # 企微同步
        print(f"  📤 同步到企微...")
        sync_to_wecom(candidates, keyword)

        print(f"\n{GREEN}{'='*50}{RESET}")
        print(f"{GREEN}✅ 全部完成！{RESET}")
        print(f"{'='*50}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{GREEN}👋 再见！{RESET}")

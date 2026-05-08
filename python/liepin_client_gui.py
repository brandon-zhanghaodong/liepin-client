#!/usr/bin/env python3
"""
招聘工厂 · 猎聘搜人客户端
独立 Playwright 浏览器 + tkinter GUI
PyInstaller 打包用
"""

import os
import sys
import json
import csv
import re
import time
import random
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
from pathlib import Path
from threading import Thread

# ── 打包路径兼容 ─────────────────────────────────────────────────────────
if getattr(sys, 'frozen', False):
    BASE_DIR = sys._MEIPASS
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ── 配置 ─────────────────────────────────────────────────────────────────
STORAGE_PATH = os.path.expanduser("~/.liepin_client/liepin_storage.json")
OUTPUT_DIR = Path.home() / ".liepin_client" / "candidates"
FEISHU_WEBHOOK = "https://open.feishu.cn/open-apis/bot/v2/hook/7b488565d8454ef7a70d43f9539ec61e"

# 企微配置（从环境变量或配置文件读取）
CONFIG_FILE = os.path.expanduser("~/.liepin_client/config.json")

# ── 自检项 ──────────────────────────────────────────────────────────────
CHECKS = []


# ==============================================================
#  搜索引擎
# ==============================================================

def load_storage_cookies():
    """加载持久化登录态"""
    if os.path.exists(STORAGE_PATH):
        try:
            with open(STORAGE_PATH) as f:
                data = json.load(f)
            return data.get("cookies", [])
        except:
            pass
    return []


def save_storage_cookies(ctx):
    """保存登录态"""
    try:
        cookies = ctx.cookies()
        state = {"cookies": cookies, "updated": datetime.now().isoformat()}
        os.makedirs(os.path.dirname(STORAGE_PATH), exist_ok=True)
        with open(STORAGE_PATH, "w") as f:
            json.dump(state, f, ensure_ascii=False)
        return len(cookies)
    except:
        return 0


def crawl_liepin(keyword, max_count=45, progress_callback=None):
    """
    猎聘搜索核心函数
    使用独立 Playwright Chromium 浏览器
    """
    from playwright.sync_api import sync_playwright

    candidates = []
    saved_cookies = load_storage_cookies()

    if progress_callback:
        progress_callback(f"📥 加载登录态 ({len(saved_cookies)} cookies)", 5)

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False,
            args=[
                "--no-first-run",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
            ]
        )
        ctx = browser.new_context(
            viewport={"width": 1920, "height": 1080},
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        if saved_cookies:
            ctx.add_cookies(saved_cookies)

        page = ctx.new_page()

        if progress_callback:
            progress_callback("🌐 打开猎聘找简历页面...", 10)

        page.goto("https://h.liepin.com/search/getConditionItem",
                   wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(3000)
        page.wait_for_load_state("networkidle")

        # 保存更新后的登录态
        if not saved_cookies:
            n = save_storage_cookies(ctx)
            if progress_callback:
                progress_callback(f"💾 登录态已保存 ({n} cookies)", 15)

        # 清空筛选条件
        try:
            clear_btn = page.locator("text=清空筛选条件")
            if clear_btn.is_visible(timeout=2000):
                clear_btn.click()
                page.wait_for_timeout(1500)
        except:
            pass

        # ── 输入关键词 ──
        if progress_callback:
            progress_callback("⌨️ 输入搜索关键词...", 20)

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
                # 备选：JS 注入
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
            if progress_callback:
                progress_callback(f"⚠️ 输入异常: {e}", 20)

        # ── 点击搜索按钮 ──
        if progress_callback:
            progress_callback("🔍 执行搜索...", 25)

        try:
            page.get_by_role("button", name=re.compile("搜 索")).click(timeout=5000)
        except:
            try:
                page.locator("button").filter(has_text="搜 索").first.click(timeout=3000)
            except:
                page.keyboard.press("Enter")
        page.wait_for_timeout(5000)

        # ── 翻页提取 ──
        max_pages = max(1, (max_count + 29) // 30)

        for page_num in range(1, max_pages + 1):
            pct = 25 + (page_num / max_pages) * 65
            try:
                page.wait_for_selector("table.new-resume-card", timeout=15000)
                time.sleep(2)
            except:
                if progress_callback:
                    progress_callback(f"⚠️ 第{page_num}页无结果", int(pct))
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

            if progress_callback:
                progress_callback(f"📄 第{page_num}页: {len(rows)}人 (累计{len(candidates)})", int(pct))

            if len(candidates) >= max_count:
                candidates = candidates[:max_count]
                break

            # 翻页
            if page_num < max_pages:
                try:
                    next_btn = page.query_selector(".ant-pagination-next")
                    if next_btn:
                        next_btn.click()
                        delay = random.uniform(5, 12)
                        if progress_callback:
                            progress_callback(f"➡️ 翻到第{page_num+1}页 (等待{int(delay)}s)...", int(pct))
                        time.sleep(delay)
                    else:
                        break
                except:
                    break

        # 保存登录态
        save_storage_cookies(ctx)
        browser.close()

    return candidates


# ==============================================================
#  数据同步
# ==============================================================

def sync_to_feishu(candidates, keyword):
    """推送到飞书群 + 飞书 Bitable"""
    results = {"bitable": 0, "group": False}

    # ── 飞书 Bitable ──
    app_token = "WXHObDl8eahIVEs06phcpzPDncb"
    table_id = "tblxmUAD1XrA4XTP"
    try:
        import requests
        r = requests.post(
            "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
            json={"app_id": "cli_a917170b57f89cd6", "app_secret": "5jo3BXlMlZUuwYWsdVrQQc07Rn4HM3Qz"},
            timeout=10
        )
        token = r.json().get("tenant_access_token", "")
        if not token:
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

    # ── 飞书群通知 ──
    try:
        import requests
        top = candidates[:10]
        preview_lines = []
        for c in top:
            parts = []
            if c.get("name"):
                parts.append(c["name"])
            if c.get("age"):
                parts.append(f"{c['age']}岁")
            if c.get("years"):
                parts.append(c["years"])
            if c.get("edu"):
                parts.append(c["edu"])
            if c.get("company"):
                parts.append(c["company"])
            if c.get("position"):
                parts.append(c["position"])
            preview_lines.append("  " + " | ".join(parts))

        msg = (
            f"🔍 猎聘搜索完成\n"
            f"关键词: {keyword}\n"
            f"共 {len(candidates)} 人，入库 {results['bitable']} 人\n\n"
            f"📋 预览（前10人）:\n" + "\n".join(preview_lines)
        )
        requests.post(
            FEISHU_WEBHOOK,
            json={"msg_type": "text", "content": {"text": msg}},
            timeout=10
        )
        results["group"] = True
    except:
        pass

    return results


def sync_to_wecom(candidates, keyword):
    """推送到企微群"""
    config = load_config()
    webhook = config.get("wecom_webhook", "")
    if not webhook:
        return False

    try:
        import requests
        now = datetime.now().strftime("%Y-%m-%d %H:%M")
        lines = [f"🔍 **招聘工厂 · 猎聘搜索结果 | {now}**",
                 f"**关键词：** {keyword}",
                 f"**共找到：** {len(candidates)} 人",
                 ""]

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


def save_csv(candidates, keyword):
    """保存到本地 CSV"""
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


# ==============================================================
#  配置管理
# ==============================================================

def load_config():
    """加载客户端配置"""
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE) as f:
                return json.load(f)
        except:
            pass
    return {
        "wecom_webhook": "",
        "default_keyword": "CTO",
        "max_results": 45,
    }


def save_config(config):
    """保存客户端配置"""
    os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ==============================================================
#  初始化自检
# ==============================================================

def check_and_install_playwright():
    """检查并自动安装 Playwright + Chromium"""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            _ = p.chromium.executable_path
            return True, ""  # 已就绪
    except ImportError:
        return False, "playwright 模块未安装"
    except Exception:
        # Chromium 未安装，自动安装
        import subprocess
        print("⏳ 正在安装 Playwright Chromium 浏览器...", flush=True)
        try:
            result = subprocess.run(
                [sys.executable, "-m", "playwright", "install", "chromium"],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                return True, "Chromium 已安装"
            else:
                return False, f"安装失败: {result.stderr[:200]}"
        except Exception as e:
            return False, f"安装异常: {e}"


def check_environment():
    """运行环境自检"""
    results = []

    # 检查 playwright 是否可用
    try:
        from playwright.sync_api import sync_playwright
        results.append(("playwright", True, ""))
    except ImportError:
        results.append(("playwright", False, "playwright 未安装"))
        return results

    # 检查 chromium 是否已安装 + 自动安装
    ok, detail = check_and_install_playwright()
    if ok:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            ep = p.chromium.executable_path
        results.append(("chromium", True, ep))
    else:
        results.append(("chromium", False, detail))

    # 检查登录态
    storage_exists = os.path.exists(STORAGE_PATH)
    if storage_exists:
        try:
            with open(STORAGE_PATH) as f:
                data = json.load(f)
            n = len(data.get("cookies", []))
            results.append(("登录态", True, f"{n} cookies"))
        except:
            results.append(("登录态", False, "登录态文件损坏"))
    else:
        results.append(("登录态", False, "未找到登录态，首次使用需要扫码登录"))

    # 检查网络连通
    try:
        import requests
        r = requests.get("https://h.liepin.com", timeout=5)
        results.append(("网络", True, f"猎聘可达 ({r.status_code})"))
    except:
        results.append(("网络", False, "无法访问猎聘"))

    return results


# ==============================================================
#  GUI 界面
# ==============================================================

class LiepinClientGUI:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("招聘工厂 · 猎聘搜人")
        self.root.geometry("800x650")
        self.root.minsize(600, 500)
        self.config = load_config()
        self._setup_ui()
        self._run_startup_checks()

    def _setup_ui(self):
        # ── 顶部信息栏 ──
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=15, pady=(15, 5))

        ttk.Label(header, text="招聘工厂 · 猎聘搜人",
                  font=("", 16, "bold")).pack(side="left")
        ttk.Label(header, text="v1.2  ·  独立浏览器版",
                  foreground="gray").pack(side="left", padx=10)

        # ── 搜索区域 ──
        search_frame = ttk.LabelFrame(self.root, text="搜索", padding=10)
        search_frame.pack(fill="x", padx=15, pady=10)

        row1 = ttk.Frame(search_frame)
        row1.pack(fill="x", pady=5)
        ttk.Label(row1, text="关键词:").pack(side="left")
        self.keyword_var = tk.StringVar(value=self.config.get("default_keyword", ""))
        self.keyword_entry = ttk.Entry(row1, textvariable=self.keyword_var, width=40)
        self.keyword_entry.pack(side="left", padx=10)
        self.keyword_entry.bind("<Return>", lambda e: self._do_search())

        ttk.Label(row1, text="最多:").pack(side="left")
        self.max_var = tk.StringVar(value=str(self.config.get("max_results", 45)))
        self.max_spin = ttk.Spinbox(row1, from_=10, to=100, textvariable=self.max_var, width=6)
        self.max_spin.pack(side="left", padx=5)
        ttk.Label(row1, text="人").pack(side="left")

        self.search_btn = ttk.Button(row1, text="🔍 开始搜索", command=self._do_search)
        self.search_btn.pack(side="left", padx=15)

        # ── 同步选项 ──
        sync_frame = ttk.Frame(search_frame)
        sync_frame.pack(fill="x", pady=5)

        self.sync_feishu = tk.BooleanVar(value=True)
        ttk.Checkbutton(sync_frame, text="同步到飞书", variable=self.sync_feishu).pack(side="left", padx=5)

        self.sync_wecom = tk.BooleanVar(value=bool(self.config.get("wecom_webhook")))
        ttk.Checkbutton(sync_frame, text="同步到企微", variable=self.sync_wecom).pack(side="left", padx=5)

        self.sync_csv = tk.BooleanVar(value=True)
        ttk.Checkbutton(sync_frame, text="保存本地CSV", variable=self.sync_csv).pack(side="left", padx=5)

        self.sync_bitable = tk.BooleanVar(value=True)
        ttk.Checkbutton(sync_frame, text="同步到飞书Bitable", variable=self.sync_bitable).pack(side="left", padx=5)

        # ── 日志区域 ──
        log_frame = ttk.LabelFrame(self.root, text="执行日志", padding=5)
        log_frame.pack(fill="both", expand=True, padx=15, pady=10)

        self.log_area = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, height=15,
            font=("Menlo", 10), bg="#1e1e1e", fg="#d4d4d4",
            insertbackground="white"
        )
        self.log_area.pack(fill="both", expand=True)

        # 日志标签颜色
        self.log_area.tag_config("info", foreground="#b0b0b0")
        self.log_area.tag_config("ok", foreground="#4ec9b0")
        self.log_area.tag_config("warn", foreground="#cea84b")
        self.log_area.tag_config("err", foreground="#f14c4c")
        self.log_area.tag_config("bold", font=("Menlo", 10, "bold"))

        # ── 进度条 ──
        progress_frame = ttk.Frame(self.root)
        progress_frame.pack(fill="x", padx=15, pady=(0, 10))
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(
            progress_frame, variable=self.progress_var,
            maximum=100, mode="determinate"
        )
        self.progress_bar.pack(fill="x")
        self.progress_label = ttk.Label(progress_frame, text="就绪", foreground="gray")
        self.progress_label.pack(pady=2)

        # ── 状态栏 ──
        self.status_var = tk.StringVar(value="就绪")
        status_bar = ttk.Label(self.root, textvariable=self.status_var,
                                relief="sunken", anchor="w", padding=5)
        status_bar.pack(fill="x", side="bottom")

    # ── 启动自检 ──
    def _run_startup_checks(self):
        def run():
            self._log("⏳ 运行环境自检...\n")
            results = check_environment()
            all_ok = True
            for name, ok, detail in results:
                icon = "✅" if ok else "❌"
                tag = "ok" if ok else "err"
                self._log(f"  {icon} {name}: {detail}\n", tag)
                if not ok:
                    all_ok = False
            if not all_ok:
                self._log("\n⚠️ 部分检查未通过，请修复后使用\n", "warn")
            else:
                self._log("\n✅ 环境就绪，可以开始搜索\n", "ok")
            self._update_status("就绪")

        Thread(target=run, daemon=True).start()

    # ── 搜索线程 ──
    def _do_search(self):
        keyword = self.keyword_var.get().strip()
        if not keyword:
            messagebox.showwarning("提示", "请输入搜索关键词")
            return

        try:
            max_count = int(self.max_var.get())
        except:
            max_count = 45

        self.search_btn.config(state="disabled")
        self.progress_var.set(0)
        self.log_area.delete("1.0", tk.END)

        def progress_callback(msg, pct):
            self.root.after(0, lambda: self._update_progress(msg, pct))

        def run():
            start = time.time()

            self.root.after(0, lambda: self._log(f"🚀 开始搜索: {keyword} (最多{max_count}人)\n", "bold"))
            self.root.after(0, lambda: self._update_status(f"搜索中: {keyword}"))

            try:
                candidates = crawl_liepin(keyword, max_count, progress_callback)
            except Exception as e:
                self.root.after(0, lambda: self._log(f"\n❌ 搜索失败: {e}\n", "err"))
                self.root.after(0, lambda: self._update_status("搜索失败"))
                self.root.after(0, lambda: self.search_btn.config(state="normal"))
                self.root.after(0, lambda: self.progress_var.set(0))
                return

            elapsed = time.time() - start
            self.root.after(0, lambda: self._log(f"\n📊 共找到 {len(candidates)} 人 (耗时 {elapsed:.0f}s)\n",
                                                   "bold"))

            if not candidates:
                self.root.after(0, lambda: self._log("⚠️ 未找到候选人\n", "warn"))
                self.root.after(0, lambda: self._update_status("搜索完成，无结果"))
                self.root.after(0, lambda: self.search_btn.config(state="normal"))
                return

            # 打印预览
            lines = []
            for i, c in enumerate(candidates[:10], 1):
                parts = [c.get("name", "?")]
                if c.get("age"): parts.append(f"{c['age']}岁")
                if c.get("years"): parts.append(c["years"])
                if c.get("edu"): parts.append(c["edu"])
                if c.get("company"): parts.append(c["company"])
                if c.get("position"): parts.append(c["position"])
                lines.append(f"  {i}. {' | '.join(parts)}")
            self.root.after(0, lambda: self._log(f"\n📋 预览（前10人）:\n" + "\n".join(lines) + "\n"))

            # CSV 保存
            csv_path = None
            if self.sync_csv.get():
                csv_path = save_csv(candidates, keyword)
                self.root.after(0, lambda: self._log(f"📁 CSV已保存: {csv_path}\n", "ok"))

            # 异步同步
            sync_results = {}
            self.root.after(0, lambda: self._update_status("正在同步数据..."))

            # 飞书同步
            if self.sync_feishu.get() or self.sync_bitable.get():
                self.root.after(0, lambda: self._log("📤 同步到飞书...\n"))
                feishu_ok = sync_to_feishu(candidates, keyword)
                if feishu_ok.get("bitable", 0) > 0:
                    self.root.after(0, lambda n=feishu_ok["bitable"]: self._log(f"  ✅ Bitable: {n}条\n", "ok"))
                if feishu_ok.get("group"):
                    self.root.after(0, lambda: self._log(f"  ✅ 飞书群通知已发送\n", "ok"))

            # 企微同步
            if self.sync_wecom.get():
                self.root.after(0, lambda: self._log("📤 同步到企微...\n"))
                if sync_to_wecom(candidates, keyword):
                    self.root.after(0, lambda: self._log(f"  ✅ 企微群通知已发送\n", "ok"))
                else:
                    self.root.after(0, lambda: self._log(f"  ⚠️ 企微同步失败（未配置 webhook？）\n", "warn"))

            self.root.after(0, lambda: self._log(f"\n{'='*50}\n✅ 全部完成！\n", "bold"))
            self.root.after(0, lambda: self._update_status(f"完成 - {len(candidates)}人, 耗时{elapsed:.0f}s"))
            self.root.after(0, lambda: self.progress_var.set(100))
            self.root.after(0, lambda: self.search_btn.config(state="normal"))

        Thread(target=run, daemon=True).start()

    # ── 辅助方法 ──
    def _log(self, text, tag=None):
        if tag:
            self.log_area.insert(tk.END, text, tag)
        else:
            self.log_area.insert(tk.END, text, "info")
        self.log_area.see(tk.END)
        self.log_area.update()

    def _update_progress(self, msg, pct):
        self.progress_var.set(min(pct, 100))
        self.progress_label.config(text=msg)
        if pct < 100:
            self._log(f"{msg}\n")

    def _update_status(self, text):
        self.status_var.set(text)

    def run(self):
        self.root.mainloop()


# ==============================================================
#  入口
# ==============================================================

def main():
    app = LiepinClientGUI()
    app.run()


if __name__ == "__main__":
    main()

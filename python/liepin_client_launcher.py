#!/usr/bin/env python3
"""
招聘工厂 · 猎聘搜人工具
一键启动器（客户版）
https://github.com/AIHR007/crawler-client

用法：双击运行，按提示输入关键词即可搜索
"""

import subprocess
import sys
import time
import os

# ── 配置 ────────────────────────────────────────────────────────────────────
CDP_PORT = 9222
SERVER_HOST = "8.135.58.6"   # 招聘工厂服务器地址（无需修改）
SERVER_PORT = None            # 客户专属端口（开通后告知）
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEARCH_SCRIPT = os.path.join(SCRIPT_DIR, "liepin_search_connected.py")

# ── 颜色 ───────────────────────────────────────────────────────────────────
RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def clear():
    os.system("cls" if os.name == "nt" else "clear")

def print_banner():
    clear()
    print(f"""{CYAN}
╔══════════════════════════════════════════════════════╗
║       招聘工厂 · 猎聘搜人工具  {BOLD}v1.0{RESET}{CYAN}                    ║
║       客户版 · 一键启动器                               ║
╚══════════════════════════════════════════════════════╝{RESET}
""")

def check_chrome_running():
    """检查 Chrome 是否已开启远程调试端口"""
    import socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    result = sock.connect_ex(("127.0.0.1", CDP_PORT))
    sock.close()
    return result == 0

def get_chrome_pid():
    """获取已连接 Chrome 的 PID"""
    try:
        import urllib.request
        import json
        resp = urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json", timeout=3)
        pages = json.loads(resp.read())
        if pages:
            return pages[0].get("id", ""), pages[0].get("title", "")
    except:
        pass
    return None, None

def check_chrome_installation():
    """检查 Chrome 是否安装"""
    import shutil
    return shutil.which("google-chrome") or shutil.which("chrome") or \
           os.path.exists("/Applications/Google Chrome.app") or \
           os.path.exists(os.path.expanduser("~/AppData/Local/Google/Chrome/Application/chrome.exe"))

def restart_chrome_guide():
    """输出重启 Chrome 的指引"""
    print(f"""
{YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}
{BOLD}⚠️  需要先重启 Chrome{Reset}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}

请按以下步骤操作：

1️⃣  关闭所有 Chrome 窗口

2️⃣  打开终端（Terminal），复制粘贴以下命令并回车：

    # macOS:
    /Applications/Google\\ Chrome.app/Contents/MacOS/Google\\ Chrome \\
        --remote-debugging-port={CDP_PORT} \\
        --user-data-dir=$HOME/chrome-debug-profile

    # Windows (CMD):
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe" ^
        --remote-debugging-port={CDP_PORT} ^
        --user-data-dir=%USERPROFILE%\\chrome-debug-profile

    # Linux:
    google-chrome --remote-debugging-port={CDP_PORT} \\
        --user-data-dir=$HOME/chrome-debug-profile

3️⃣  Chrome 重启后，确认已登录猎聘（https://www.liepin.com）

4️⃣  重新运行本工具

{YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{RESET}
""")

def run_search(keyword):
    """运行搜索脚本"""
    import urllib.request
    import json

    # 检查服务器连通性
    print(f"\n{GREEN}🔍 正在搜索：{BOLD}{keyword}{RESET}")
    print(f"📡 连接服务器 {SERVER_HOST}...")

    # 先验证 CDP 端口
    try:
        resp = urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json/version", timeout=5)
        version = json.loads(resp.read())
        print(f"✅ Chrome 远程调试已就绪（Chrome/{version.get('Browser', '?')}）")
    except Exception as e:
        print(f"❌ 无法连接到 Chrome 远程调试端口: {e}")
        return False

    # 运行搜索脚本
    try:
        result = subprocess.run(
            [sys.executable, SEARCH_SCRIPT, keyword],
            capture_output=False
        )
        return result.returncode == 0
    except FileNotFoundError:
        print(f"❌ 找不到搜索脚本：{SEARCH_SCRIPT}")
        print(f"   请确认 liepin_search_connected.py 与本工具在同一目录")
        return False

def main():
    print_banner()

    # ① 检查 Chrome 安装
    if not check_chrome_installation():
        print(f"{RED}❌ 未检测到 Google Chrome，请先安装 Chrome{Reset}")
        print(f"   下载地址：https://www.google.com/chrome/")
        input(f"\n按回车退出...")
        return

    # ② 检查远程调试端口
    if not check_chrome_running():
        restart_chrome_guide()
        input(f"\n按回车退出...")
        return

    # ③ 获取已连接 Chrome 信息
    pid, title = get_chrome_pid()
    if pid:
        print(f"{GREEN}✅ 检测到 Chrome 远程调试（PID: {pid}）{Reset}")
        if title:
            print(f"   当前标签页：{title[:50]}")
    print()

    # ④ 循环搜索
    while True:
        try:
            keyword = input(f"{CYAN}🔍 请输入搜索关键词（回车发送，空格回车退出）:{RESET}\n   ").strip()
            if not keyword:
                print(f"\n{GREEN}👋 再见！{RESET}")
                break
            run_search(keyword)
            print()
        except KeyboardInterrupt:
            print(f"\n{GREEN}👋 再见！{RESET}")
            break
        except Exception as e:
            print(f"{RED}❌ 错误: {e}{RESET}")
            time.sleep(2)

if __name__ == "__main__":
    main()
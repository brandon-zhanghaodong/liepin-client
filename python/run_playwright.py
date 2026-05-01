#!/usr/bin/env python3
"""
猎聘 Playwright 工具 - 由 Electron 主进程通过 child_process 调用
提供搜索、截图、检查登录态等功能
"""

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# 当打包后，Python 脚本和资源在一起
_BUNDLE_DIR = Path(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))))


def ensure_browser():
    """确保 Playwright 浏览器已安装（打包后首次可能会缺失）"""
    try:
        from playwright.sync_api import sync_playwright
        # 尝试简单创建以验证安装
        with sync_playwright() as p:
            browsers = p.chromium  # 不会真的启动，只是检查可用性
        return True
    except Exception:
        log("⚠️ Playwright 浏览器未安装，尝试安装 chromium...")
        os.system(f"{sys.executable} -m playwright install chromium")
        return True


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else "help"

    if action == "check":
        """检查 Playwright 安装状态"""
        try:
            import playwright
            ver = playwright.__version__
            # 检查浏览器
            from playwright.sync_api import sync_playwright
            msg = f'{{"status":"ok","version":"{ver}"}}'
            print(msg, flush=True)
        except ImportError as e:
            print(f'{{"status":"error","message":"{str(e)}"}}', flush=True)

    elif action == "install":
        """安装 Playwright 浏览器"""
        ensure_browser()
        print('{"status":"ok","message":"Browser installed"}', flush=True)

    elif action == "search":
        """执行猎聘搜索 — 参数通过环境变量或 JSON 文件传递"""
        config_file = sys.argv[2] if len(sys.argv) > 2 else None
        if config_file and Path(config_file).exists():
            config = json.loads(Path(config_file).read_text())
        else:
            config = {
                "keyword": sys.argv[2] if len(sys.argv) > 2 else "HRD",
                "max_results": int(sys.argv[3]) if len(sys.argv) > 3 else 50,
                "cdp_port": int(sys.argv[4]) if len(sys.argv) > 4 else 9222,
            }

        # 导入搜索模块
        sys.path.insert(0, str(_BUNDLE_DIR))
        from search_candidates import search_liepin

        candidates = search_liepin(
            keyword=config.get("keyword", "HRD"),
            max_results=config.get("max_results", 50),
            cdp_port=config.get("cdp_port", 9222),
            output_dir=config.get("output_dir"),
        )

        result = json.dumps({
            "keyword": config.get("keyword"),
            "timestamp": datetime.now().isoformat(),
            "total": len(candidates),
            "candidates": candidates
        }, ensure_ascii=False)
        print(result, flush=True)

    elif action == "snapshot":
        """截取猎聘页面截图"""
        cdp_port = int(sys.argv[2]) if len(sys.argv) > 2 else 9222
        output_path = sys.argv[3] if len(sys.argv) > 3 else str(Path.home() / "Desktop" / f"liepin_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png")

        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(f"http://127.0.0.1:{cdp_port}")
            context = browser.contexts[0]
            page = context.new_page()
            page.goto("https://www.liepin.com/", wait_until="domcontentloaded")
            time.sleep(3)
            page.screenshot(path=output_path)
            page.close()

        print(f'{{"status":"ok","path":"{output_path}"}}', flush=True)

    elif action == "help":
        print("""猎聘 Playwright 工具
用法:
  python run_playwright.py check              — 检查安装状态
  python run_playwright.py install            — 安装浏览器
  python run_playwright.py search <keyword>   — 执行搜索
  python run_playwright.py snapshot [port]     — 页面截图
""", flush=True)

    else:
        print(f'{{"status":"error","message":"未知操作: {action}"}}', flush=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
PyInstaller 打包脚本 - 招聘工厂猎聘搜人客户端

用法:
  python3 build_client.py            # 默认打包当前平台
  python3 build_client.py --clean    # 清理后重新打包
"""

import os
import sys
import shutil
import subprocess
import argparse

VERSION = "1.2.0"
APP_NAME = "招聘工厂"
ENTRY_SCRIPT = "liepin_client_gui.py"

# ── 检查依赖 ─────────────────────────────────────────────────────────────
def check_dependencies():
    missing = []
    try:
        import PyInstaller
    except ImportError:
        missing.append("pyinstaller")
    try:
        import playwright
    except ImportError:
        missing.append("playwright")

    if missing:
        print(f"❌ 缺少依赖: {', '.join(missing)}")
        print(f"   安装: pip install {' '.join(missing)}")
        sys.exit(1)

    # 检查 Chromium
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            path = p.chromium.executable_path
            print(f"  ✅ Chromium: {path}")
    except Exception as e:
        print(f"⚠️  Chromium 未安装, 自动安装中...")
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)


# ── 创建 PyInstaller spec ────────────────────────────────────────────────
def create_spec(platform="auto"):
    """创建 .spec 配置"""
    plat = platform
    if plat == "auto":
        if sys.platform == "darwin":
            plat = "darwin"
        elif sys.platform == "win32":
            plat = "win32"
        else:
            plat = "linux"

    # 收集 playwright 的浏览器二进制路径
    from playwright._impl._driver import compute_driver_executable
    from playwright._repo_version import version as pw_version

    spec_content = f"""# -*- mode: python ; coding: utf-8 -*-

a = Analysis(
    ['{ENTRY_SCRIPT}'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'playwright.sync_api',
        'playwright.async_api',
        'playwright._impl._driver',
        'playwright._impl._browser',
        'playwright._impl._browser_context',
        'playwright._impl._page',
        'playwright._impl._api_structures',
        'playwright._impl._connection',
        'playwright._impl._transport',
        'playwright._impl._helper',
        'playwright._impl._js_snippet',
        'playwright._impl._greenlets',
        'playwright._impl._errors',
        'playwright._impl._locator',
        'playwright._impl._network',
        'playwright._impl._element_handle',
        'playwright._impl._frame',
        'playwright._impl._selectors',
        'playwright._impl._clock',
        'playwright._impl._fetch',
        'playwright._impl._artifact',
        'playwright._impl._file_chooser',
        'playwright._impl._dialog',
        'playwright._impl._console_message',
        'playwright._impl._download',
        'playwright._impl._video',
        'playwright._impl._set_input_files_helpers',
        'greenlet',
        'PIL',
        'PIL._tkinter_finder',
    ],
    hookspath=[],
    hooksconfig={{}},
    runtime_hooks=[],
    excludes=[
        'tkinter.test',
        'unittest',
        'test',
        'distutils',
        'setuptools',
        'pydoc',
        'email',
        'http.server',
        'xmlrpc',
        'venv',
        'sqlite3',
        'curses',
        'readline',
        'dbm',
    ],
    noarchive=False,
)

# Playwright 的 chromium 浏览器二进制
from playwright._impl._driver import compute_driver_executable
import glob

# 查找 playwright 浏览器安装目录
playwright_browsers_dir = None
for candidate in [
    os.path.expanduser("~/.cache/ms-playwright"),
    os.path.expanduser("~/.cache/playwright"),
    os.environ.get("PLAYWRIGHT_BROWSERS_PATH", ""),
]:
    if candidate and os.path.isdir(candidate):
        playwright_browsers_dir = candidate
        break

# 查找 chromium
chromium_dir = None
if playwright_browsers_dir:
    for d in os.listdir(playwright_browsers_dir):
        if d.startswith("chromium-") or d.startswith("chromium_headless_shell-"):
            full = os.path.join(playwright_browsers_dir, d)
            if os.path.isdir(full):
                # 查找 chrome-* 可执行文件
                chrome_files = glob.glob(os.path.join(full, "**", "chrome*"), recursive=True)
                if chrome_files:
                    chromium_dir = full
                    break

if chromium_dir:
    print(f"  发现 Chromium: {{chromium_dir}}")
    # 添加整个 chromium 目录为 Tree
    a.datas += Tree(chromium_dir, prefix=os.path.basename(chromium_dir))
else:
    print("  ⚠️  未找到 Chromium 二进制，请在打包前运行: playwright install chromium")

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='{APP_NAME}',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    contents_directory='.',
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='{APP_NAME}',
)
"""

    # Mac 需要 APP
    if plat == "darwin":
        spec_content += f"""
app = BUNDLE(
    coll,
    name='{APP_NAME}.app',
    icon=None,
    bundle_identifier='com.talent-ai.liepin-client',
    info_plist={{
        'CFBundleName': '{APP_NAME}',
        'CFBundleDisplayName': '{APP_NAME} · 猎聘搜人',
        'CFBundleVersion': '{VERSION}',
        'CFBundleShortVersionString': '{VERSION}',
        'NSHighResolutionCapable': True,
    }},
)
"""

    spec_path = f"{APP_NAME}.spec"
    with open(spec_path, "w") as f:
        f.write(spec_content)
    print(f"  ✅ 已生成 spec: {spec_path}")
    return spec_path


def build(clean=False):
    """执行打包"""
    print(f"\n{'='*60}")
    print(f"  招聘工厂 · 猎聘搜人客户端 v{VERSION}")
    print(f"  PyInstaller 打包")
    print(f"{'='*60}\n")

    check_dependencies()

    if clean:
        dist_dir = os.path.join(os.path.dirname(ENTRY_SCRIPT), "dist")
        build_dir = os.path.join(os.path.dirname(ENTRY_SCRIPT), "build")
        for d in [dist_dir, build_dir]:
            if os.path.exists(d):
                shutil.rmtree(d)
                print(f"  🗑️  已清理: {d}")
        spec_file = f"{APP_NAME}.spec"
        if os.path.exists(spec_file):
            os.remove(spec_file)
            print(f"  🗑️  已清理: {spec_file}")

    spec_path = create_spec()

    print(f"\n🚀 开始打包...\n")
    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", spec_path, "--clean", "--noconfirm"],
        capture_output=False
    )
    if result.returncode == 0:
        print(f"\n✅ 打包完成!")
    else:
        print(f"\n❌ 打包失败 (exit code: {result.returncode})")

    return result.returncode == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="打包猎聘搜人客户端")
    parser.add_argument("--clean", action="store_true", help="清理后重新打包")
    args = parser.parse_args()
    success = build(clean=args.clean)
    sys.exit(0 if success else 1)

#!/bin/bash
# ==============================================================
# 招聘工厂 · 猎聘搜人客户端 — 一键安装脚本 (Mac / Linux)
# ==============================================================
# 用法: 在终端执行: bash install.sh
# ==============================================================

set -e

GREEN='\033[92m'
CYAN='\033[96m'
YELLOW='\033[93m'
RED='\033[91m'
BOLD='\033[1m'
RESET='\033[0m'

echo -e "${CYAN}"
echo "╔═══════════════════════════════════════════════════════╗"
echo "║             招聘工厂 · 猎聘搜人客户端                 ║"
echo "║             v1.2 · 一键安装                          ║"
echo "╚═══════════════════════════════════════════════════════╝"
echo -e "${RESET}"

# ── 检查 Python ──
echo -e "${BOLD}[1/3] 检查 Python 环境...${RESET}"
PYTHON=""
for cmd in python3 python; do
    if command -v $cmd &>/dev/null; then
        PYTHON=$cmd
        break
    fi
done

if [ -z "$PYTHON" ]; then
    echo -e "${RED}❌ 未找到 Python，请先安装:${RESET}"
    echo "   https://www.python.org/downloads/"
    exit 1
fi

PY_VER=$($PYTHON --version 2>&1)
echo -e "${GREEN}  ✅ $PY_VER${RESET}"

# ── 安装 playwright ──
echo -e "${BOLD}[2/3] 安装 Playwright...${RESET}"
$PYTHON -m pip install playwright requests --quiet 2>/dev/null || $PYTHON -m pip install playwright requests
echo -e "${GREEN}  ✅ 依赖安装完成${RESET}"

# ── 安装 Chromium ──
echo -e "${BOLD}[3/3] 下载 Chromium 浏览器（约 336MB）...${RESET}"
$PYTHON -m playwright install chromium 2>&1 | tail -3
echo -e "${GREEN}  ✅ Chromium 安装完成${RESET}"

# ── 下载搜索脚本 ──
echo ""
echo -e "${BOLD}下载搜索脚本...${RESET}"
SCRIPT_DIR="$HOME/.liepin_client"
mkdir -p "$SCRIPT_DIR"
SCRIPT_URL="https://raw.githubusercontent.com/brandon-zhanghaodong/recruitment-factory-client/main/python/liepin_cli.py"

# 尝试下载，如果失败则提示手动复制
if command -v curl &>/dev/null; then
    curl -sSL "$SCRIPT_URL" -o "$SCRIPT_DIR/liepin_cli.py" 2>/dev/null && echo -e "${GREEN}  ✅ 脚本已下载${RESET}" || echo -e "${YELLOW}  ⚠️  下载失败，请手动复制脚本${RESET}"
elif command -v wget &>/dev/null; then
    wget -q "$SCRIPT_URL" -O "$SCRIPT_DIR/liepin_cli.py" 2>/dev/null && echo -e "${GREEN}  ✅ 脚本已下载${RESET}" || echo -e "${YELLOW}  ⚠️  下载失败，请手动复制脚本${RESET}"
fi

# ── 完成 ──
echo ""
echo -e "${GREEN}${BOLD}✅ 安装完成！${RESET}"
echo ""
echo -e "使用方法："
echo -e "  ${CYAN}cd ~/.liepin_client && python3 liepin_cli.py${RESET}"
echo ""
echo -e "或添加别名方便调用："
echo -e "  ${CYAN}echo 'alias liepin=\"cd ~/.liepin_client && python3 liepin_cli.py\"' >> ~/.zshrc${RESET}"
echo -e "  ${CYAN}source ~/.zshrc${RESET}"
echo -e "  ${CYAN}liepin${RESET}"
echo ""
echo -e "首次运行会打开浏览器，请扫码登录猎聘。"
echo -e "之后搜索会自动使用已保存的登录态。"

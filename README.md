# 猎聘客户端 (Liepin Client)

> 继承本机 Chrome 登录态的猎聘桌面客户端，内置 Playwright 自动化搜索引擎。

## 功能

- 🚀 **零配置启动** — 自动镜像本机 Chrome 的登录态，打开即用
- 🔍 **内置自动化搜索** — Python + Playwright 驱动的候选人搜索引擎
- 🎯 **候选人批量提取** — 支持关键词搜索、多字段解析、截图保存
- 🖥 **跨平台** — macOS (Intel + Apple Silicon) / Windows x64

## 架构

```
┌──────────────────────────────────┐
│    Electron (Chromium 窗口)       │ ← 加载猎聘，继承本机登录
├──────────────────────────────────┤
│    Electron ↔ IPC Bridge          │ ← 主进程管理 Python 子进程
├──────────────────────────────────┤
│    Python 3 + Playwright          │ ← 通过 CDP 连接 Chrome 执行搜索
│    └── run_playwright.py          │
│    └── search_candidates.py       │
└──────────────────────────────────┘
```

## 下载安装包

前往 [GitHub Releases](https://github.com/brandon-zhanghaodong/liepin-client/releases) 下载：

| 文件 | 平台 | 架构 |
|------|------|------|
| `liepin-client-*.dmg` | macOS | x64 / arm64 |
| `liepin-client-*.exe` | Windows | x64 |

## 本地开发

```bash
# 安装依赖
npm install

# 安装 Playwright 浏览器
pip install -r python/requirements.txt
python -m playwright install chromium

# 启动
npm start
```

## 构建

```bash
# Mac
npm run build:mac

# Windows
npm run build:win

# 全部
npm run build:all
```

CI/CD (GitHub Actions) 会在推送 tag `v*` 时自动构建并发布到 Releases。

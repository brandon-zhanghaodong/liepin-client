# 招聘工厂 · 猎聘搜人客户端

## 两种使用方式

### 方式一：GUI 客户端（推荐给最终客户）

```
# 1. 安装依赖
pip install playwright requests
playwright install chromium

# 2. 运行
python3 liepin_client_gui.py
```

- 漂亮的 tkinter 界面
- 进度条显示搜索状态
- 一键同步到飞书群/Bitable/企微
- 支持 PyInstaller 打包为独立应用

### 方式二：CLI 客户端（推荐给 Electron 集成 / 自动化）

```
# 搜索（不自动同步）
python3 liepin_electron_search.py "字节跳动 HRD" 45

# 搜索 + 自动同步到飞书和企微
python3 liepin_electron_search.py "字节跳动 HRD" 45 --sync
```

输出 JSON:
```json
{
  "status": "ok",
  "keyword": "字节跳动 HRD",
  "count": 30,
  "csv": "/Users/xx/.liepin_client/candidates/liepin_...csv",
  "candidates": [
    {"name": "**张", "age": "35", "company": "字节跳动", ...}
  ],
  "feishu": {"bitable": 30, "group": true}
}
```

## 数据持久化

- 登录态: `~/.liepin_client/liepin_storage.json`
- 本地 CSV: `~/.liepin_client/candidates/`
- 配置: `~/.liepin_client/config.json`

## 首次使用

第一次运行时，会打开独立 Chromium 浏览器窗口。
请扫码登录猎聘，搜索会自动开始。
首次登录后，登录态会自动保存到本地，后续无需重复登录。

## PyInstaller 打包

```bash
python3 build_client.py
```

生成的独立应用在 `dist/招聘工厂/` 目录下。
Mac 会生成 `.app` 包，Windows 会生成 `.exe`。

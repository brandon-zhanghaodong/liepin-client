/**
 * 猎聘客户端 - Electron Builder 配置
 * 打包 Mac + Windows 安装包，包含：
 *   - Electron 应用本体
 *   - Python 3 + Playwright 运行时（嵌入式）
 *   - Playwright 浏览器（Chromium）
 *   - 自动化搜索脚本
 *
 * 注意：完整的 Python/Playwright 打包体积较大（~200MB+）。
 * CI/CD 中使用 setup-python + install playwright 自动处理。
 */

const path = require('path');

module.exports = {
  appId: 'com.talent-ai.liepin-client',
  productName: '猎聘客户端',
  directories: {
    output: 'dist',
  },

  /* ──────── Mac ──────── */
  mac: {
    category: 'public.app-category.productivity',
    target: [
      { target: 'dmg', arch: ['x64', 'arm64'] },
      { target: 'zip', arch: ['x64', 'arm64'] },
    ],
    icon: 'assets/icon.png',
    hardenedRuntime: true,
    // CI 中需要 Apple Developer ID 证书；本地开发可注释掉
    // sign: process.env.CSC_LINK ? {} : false,
    // notarize: process.env.APPLE_ID ? { teamId: process.env.APPLE_TEAM_ID } : false,
    extendInfo: {
      LSUIElement: true, // 无 Dock 图标模式（可选）
    },
  },

  /* ──────── Windows ──────── */
  win: {
    target: [
      { target: 'nsis', arch: ['x64'] },
    ],
    icon: 'assets/icon.ico',
    // sign: process.env.CSC_LINK ? {} : undefined,
  },
  nsis: {
    oneClick: false,          // 让用户选择安装路径
    perMachine: false,
    allowToChangeInstallationDirectory: true,
    runAfterFinish: true,
    installerIcon: 'assets/icon.ico',
    uninstallerIcon: 'assets/icon.ico',
  },

  /* ──────── 打包内容 ──────── */
  files: [
    'main.js',
    'preload.js',
    'python/**/*',
    'assets/**/*',
  ],
  /* Node modules — 自动包含 dependencies，排除 devDependencies */
  /* electron-builder 默认会自动处理 node_modules */
  extraResources: [
    {
      from: 'python',
      to: 'python',
      filter: ['**/*'],
    },
  ],

  /* ──────── 打包后体积优化 ──────── */
  asar: true,
  asarUnpack: [
    'python/**',
  ],

  /* ──────── 发布 ▸ GitHub Releases ──────── */
  /* CI 中通过 publish: always 启用，本地构建时使用 --publish=never */
  publish: null,
};

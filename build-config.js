module.exports = {
  appId: 'com.talent-ai.liepin-client',
  productName: '招聘工厂',
  directories: {
    output: 'dist',
  },

  /* ──────── Mac ──────── */
  mac: {
    category: 'public.app-category.productivity',
    target: [
      { target: 'dmg', arch: ['arm64', 'x64'] },
    ],
    icon: 'assets/icon.png',
    hardenedRuntime: true,
    extendInfo: {
      LSUIElement: true,
    },
  },

  /* ──────── Windows ──────── */
  win: {
    target: [{ target: 'nsis', arch: ['x64'] }],
    icon: 'assets/icon.ico',
  },
  nsis: {
    oneClick: false,
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
    'control.html',
    'assets/**/*',
    'node_modules/**/*',
  ],

  /* ──────── asar 打包排除（playwright 的 node driver 不能放 asar 里）── */
  asar: true,
  asarUnpack: [
    'node_modules/playwright/**',
    'node_modules/playwright-core/**',
  ],

  publish: null,
};

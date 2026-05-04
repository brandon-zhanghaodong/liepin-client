module.exports = {
  appId: 'com.talent-ai.liepin-client',
  productName: '猎聘客户端',
  directories: {
    output: 'dist',
  },

  /* ──────── Mac ──────── */
  mac: {
    category: 'public.app-category.productivity',
    /* arch 通过 CLI --x64 / --arm64 指定 */
    target: ['dmg'],
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
    'assets/**/*',
    'node_modules/**/*',
  ],

  asar: true,
  publish: null,
};

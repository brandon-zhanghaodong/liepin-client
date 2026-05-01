const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // 平台信息
  getPlatform: () => ipcRenderer.invoke('get-platform'),

  // Playwright 自动化
  playwrightCheck: () => ipcRenderer.invoke('playwright:check'),
  playwrightInstall: () => ipcRenderer.invoke('playwright:install'),
  playwrightSearch: (keyword, maxResults) => ipcRenderer.invoke('playwright:search', keyword, maxResults),
  playwrightSnapshot: () => ipcRenderer.invoke('playwright:snapshot'),
});

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // 平台信息
  getPlatform: () => ipcRenderer.invoke('get-platform'),

  // Playwright / 猎聘自动化
  playwrightCheck: () => ipcRenderer.invoke('playwright:check'),
  playwrightSearch: (keyword, maxResults) => ipcRenderer.invoke('playwright:search', keyword, maxResults),
  checkLogin: () => ipcRenderer.invoke('liepin:check'),
});

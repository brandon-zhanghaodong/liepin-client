const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  getPlatform: () => ipcRenderer.invoke('get-platform'),
  playwrightCheck: () => ipcRenderer.invoke('playwright:check'),
  playwrightSearch: (keyword, maxResults) => ipcRenderer.invoke('playwright:search', keyword, maxResults),
  checkLogin: () => ipcRenderer.invoke('liepin:check'),
  getConfig: () => ipcRenderer.invoke('config:get'),
  saveConfig: (config) => ipcRenderer.invoke('config:save', config),
  openLoginBrowser: () => ipcRenderer.invoke('browser:open-login'),
  reconnectWs: () => ipcRenderer.invoke('ws:reconnect'),
  onWsStatus: (callback) => ipcRenderer.on('ws-status', (_event, data) => callback(data)),
  onTaskReceived: (callback) => ipcRenderer.on('task-received', (_event, data) => callback(data)),
  onTaskComplete: (callback) => ipcRenderer.on('task-complete', (_event, data) => callback(data)),
});

const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('electronAPI', {
  // 平台
  getPlatform: () => ipcRenderer.invoke('get-platform'),

  // 搜索
  playwrightCheck: () => ipcRenderer.invoke('playwright:check'),
  playwrightSearch: (keyword, maxResults) => ipcRenderer.invoke('playwright:search', keyword, maxResults),
  checkLogin: () => ipcRenderer.invoke('liepin:check'),

  // 配置
  getConfig: () => ipcRenderer.invoke('config:get'),
  saveConfig: (config) => ipcRenderer.invoke('config:save', config),

  // WebSocket 状态
  getWsStatus: () => ipcRenderer.invoke('ws:status'),
  reconnectWs: () => ipcRenderer.invoke('ws:reconnect'),

  // WebSocket 事件（主进程推送）
  onWsStatus: (callback) => ipcRenderer.on('ws-status', (_event, data) => callback(data)),
  onTaskReceived: (callback) => ipcRenderer.on('task-received', (_event, data) => callback(data)),
  onTaskComplete: (callback) => ipcRenderer.on('task-complete', (_event, data) => callback(data)),
});

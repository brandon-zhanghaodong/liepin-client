const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn } = require('child_process');
const fs = require('fs');

// —— 配置 ——
const TARGET_URL = 'https://www.liepin.com/';
const PLATFORM_NAME = '猎聘';

// —— 创建主窗口 ——
let mainWindow = null;

function createWindow() {
  const { screen } = require('electron');
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.workAreaSize;

  mainWindow = new BrowserWindow({
    width: Math.min(1280, width),
    height: Math.min(800, height),
    minWidth: 900,
    minHeight: 600,
    title: PLATFORM_NAME,
    icon: path.join(__dirname, 'assets', 'icon.png'),
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
    }
  });

  mainWindow.loadURL(TARGET_URL);

  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });

  mainWindow.on('closed', () => { mainWindow = null; });
}

// —— 启动 ——
app.whenReady().then(() => {
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// ============ IPC: Playwright / Python 自动化 ============

/**
 * 运行 Python Playwright 脚本并返回 JSON
 */
function runPythonScript(scriptName, args = []) {
  return new Promise((resolve, reject) => {
    const pythonPath = getPythonPath();
    const scriptPath = path.join(
      app.isPackaged ? path.join(process.resourcesPath, 'python') : path.join(__dirname, 'python'),
      scriptName
    );

    if (!fs.existsSync(scriptPath)) {
      return reject(new Error(`脚本未找到: ${scriptPath}`));
    }

    console.log(`🐍 运行: ${pythonPath} ${scriptPath} ${args.join(' ')}`);

    const proc = spawn(pythonPath, [scriptPath, ...args], {
      cwd: path.dirname(scriptPath),
      env: {
        ...process.env,
        PYTHONUNBUFFERED: '1',
      }
    });

    let stdout = '';
    let stderr = '';

    proc.stdout.on('data', (data) => { stdout += data.toString(); });
    proc.stderr.on('data', (data) => { stderr += data.toString(); });

    proc.on('close', (code) => {
      console.log(`  exit code: ${code}`);
      if (stderr) console.warn(`  stderr: ${stderr.slice(0, 500)}`);

      if (code !== 0 && !stdout.trim()) {
        return reject(new Error(stderr || `退出码 ${code}`));
      }

      // 尝试解析 JSON 输出
      try {
        const jsonStart = stdout.indexOf('{');
        if (jsonStart >= 0) {
          const jsonStr = stdout.slice(jsonStart);
          const result = JSON.parse(jsonStr);
          resolve(result);
        } else {
          resolve({ stdout: stdout.trim(), stderr: stderr.trim() });
        }
      } catch {
        resolve({ stdout: stdout.trim(), stderr: stderr.trim() });
      }
    });

    proc.on('error', reject);
  });
}

/**
 * 检查 Playwright 是否就绪
 */
async function checkPlaywright() {
  try {
    const result = await runPythonScript('liepin_check_login.py');
    return result;
  } catch (err) {
    return { status: 'error', message: err.message };
  }
}

/**
 * 执行猎聘候选人搜索
 * 通过 API 调用服务器端（不依赖本地 Python/Playwright）
 */
async function searchLiepin(keyword = 'CTO', maxResults = 50) {
  try {
    const response = await fetch('http://8.135.58.6:7895/api/wecom-search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword, max_count: maxResults }),
    });
    const data = await response.json();
    return data;
  } catch (err) {
    return { status: 'error', message: err.message };
  }
}

/**
 * 检查猎聘登录态（通过服务器 API）
 */
async function checkLiepinLogin() {
  try {
    const response = await fetch('http://8.135.58.6:7895/api/check-login', { method: 'GET' });
    const data = await response.json();
    return data;
  } catch (err) {
    return { status: 'error', message: err.message };
  }
}

// 注册 IPC 通道
ipcMain.handle('get-platform', () => ({
  name: PLATFORM_NAME,
  url: TARGET_URL,
}));

ipcMain.handle('playwright:check', async () => {
  return await checkPlaywright();
});

ipcMain.handle('playwright:search', async (_event, keyword, maxResults) => {
  return await searchLiepin(keyword, maxResults);
});

ipcMain.handle('liepin:check-login', async () => {
  return await checkLiepinLogin();
});

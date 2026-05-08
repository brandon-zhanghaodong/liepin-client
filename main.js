const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { spawn, execSync } = require('child_process');
const fs = require('fs');
const os = require('os');

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
 * 获取系统 Python 路径
 */
function getPythonPath() {
  const candidates = ['python3', 'python'];
  for (const cmd of candidates) {
    try {
      const out = execSync(`${cmd} --version`, { encoding: 'utf-8', timeout: 3000 });
      if (out.toLowerCase().includes('python')) {
        return cmd;
      }
    } catch {}
  }
  return 'python3'; // fallback
}

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
 * 检查 Python + Playwright 环境
 */
async function checkPlaywright() {
  try {
    const pythonPath = getPythonPath();
    const checkResult = execSync(`${pythonPath} -c "from playwright.sync_api import sync_playwright; print('ok')"`, {
      timeout: 10000,
      encoding: 'utf-8',
      stdio: ['ignore', 'pipe', 'pipe'],
    });
    if (checkResult.trim() === 'ok') {
      return { status: 'ready', message: 'Playwright 就绪' };
    }
    return { status: 'error', message: 'Playwright 未正确安装' };
  } catch (err) {
    return { status: 'error', message: `Python/Playwright 检查失败: ${err.message}` };
  }
}

/**
 * 执行本地猎聘搜索
 * 调用 Python 独立浏览器脚本，不走服务器
 */
async function searchLiepin(keyword = 'CTO', maxResults = 50) {
  console.log(`🔍 本地搜索: ${keyword} (最多${maxResults}人)`);
  
  try {
    // 调用 Python 桥接脚本
    const result = await runPythonScript('liepin_electron_search.py', [keyword, String(maxResults)]);
    
    if (result.status === 'ok') {
      console.log(`✅ 搜索完成: ${result.count} 人`);
      return result;
    }
    
    return { status: 'error', message: result.message || '搜索结果为空' };
  } catch (err) {
    console.error(`❌ 搜索异常: ${err.message}`);
    // 备用方案：尝试服务器 API
    try {
      console.log('⚠️  本地搜索失败，尝试服务器 API...');
      const response = await fetch('http://8.135.58.6:7895/api/search', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ keyword, max_count: maxResults }),
        signal: AbortSignal.timeout(60000),
      });
      const data = await response.json();
      return data;
    } catch (apiErr) {
      return { status: 'error', message: `本地搜索失败: ${err.message}; 服务器回退也失败: ${apiErr.message}` };
    }
  }
}

/**
 * 检查猎聘登录态（本地检查）
 */
async function checkLiepinLogin() {
  // 检查本地存储的 cookie 文件
  const storagePath = path.join(os.homedir(), '.liepin_client', 'liepin_storage.json');
  try {
    if (fs.existsSync(storagePath)) {
      const data = JSON.parse(fs.readFileSync(storagePath, 'utf-8'));
      const count = (data.cookies || []).length;
      return { status: count > 0 ? 'ok' : 'empty', cookieCount: count };
    }
    return { status: 'not_found', message: '未找到本地登录态' };
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

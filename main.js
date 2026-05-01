const { app, BrowserWindow, ipcMain, shell, dialog } = require('electron');
const path = require('path');
const fs = require('fs-extra');
const { spawn, execSync } = require('child_process');

// —— 配置 ——
const TARGET_URL = 'https://www.liepin.com/';
const PLATFORM_NAME = '猎聘';

// —— Python 运行时路径 ——
function getPythonPath() {
  // 打包后: <app>/Resources/python/bin/python3  (Mac)
  //         <app>/resources/python/python.exe     (Win)
  const isPackaged = app.isPackaged;
  const resourcePath = isPackaged
    ? path.join(process.resourcesPath, 'python')
    : path.join(__dirname, 'python');

  if (process.platform === 'win32') {
    const embedded = path.join(resourcePath, 'python.exe');
    if (fs.existsSync(embedded)) return embedded;
    return 'python'; // fallback
  }

  // Mac / Linux — 打包后从 resources 取，开发模式从目录取
  const bundled = path.join(resourcePath, 'bin', 'python3');
  if (fs.existsSync(bundled)) return bundled;
  return 'python3'; // fallback to system
}

function getScriptPath(name) {
  return path.join(
    app.isPackaged ? path.join(process.resourcesPath, 'python') : path.join(__dirname, 'python'),
    name
  );
}

// —— Chrome 用户数据目录 ——
function getChromeUserDataDir() {
  const home = app.getPath('home');
  switch (process.platform) {
    case 'darwin':
      return path.join(home, '/Library/Application Support/Google/Chrome');
    case 'win32':
      return path.join(process.env.LOCALAPPDATA || '', '/Google/Chrome/User Data');
    case 'linux':
      return path.join(home, '/.config/google-chrome');
    default:
      return null;
  }
}

function getAppProfileDir() {
  return path.join(app.getPath('userData'), 'chrome-profile');
}

// —— 首次启动：镜像本机 Chrome Profile ——
async function ensureProfile() {
  const src = getChromeUserDataDir();
  const dst = getAppProfileDir();

  if (!src) {
    console.warn('⚠️ 未知平台，使用空 profile');
    return;
  }

  const srcExists = await fs.pathExists(src);
  if (!srcExists) {
    console.warn('⚠️ 未找到本机 Chrome 用户数据目录，将使用空 profile');
    return;
  }

  const dstExists = await fs.pathExists(dst);
  if (dstExists) {
    console.log('✅ 使用已有 Chrome profile 副本');
    return;
  }

  console.log('📦 首次启动：正在复制 Chrome 用户数据...');

  const itemsToCopy = [
    'Default', 'Profile 1', 'Profile 2', 'Profile 3', 'Profile 4', 'Profile 5',
    'Local State', 'Bookmarks', 'Login Data', 'Cookies',
    'Network Persistent State', 'Preferences', 'Secure Preferences',
  ];

  let profiles = ['Default'];
  try {
    const ls = await fs.readdir(src);
    profiles = ls.filter(x => x.startsWith('Profile ') || x === 'Default');
  } catch (_) { /* 忽略 */ }

  profiles.forEach(p => {
    if (!itemsToCopy.includes(p)) itemsToCopy.push(p);
  });

  const skipDirs = new Set([
    'Cache', 'Code Cache', 'Service Worker', 'GPUCache',
    'DawnCache', 'ShaderCache', 'Crashpad', 'GrShaderCache',
    'GraphiteDawnCache', 'component_crx_cache',
    'File System', 'IndexedDB', 'Extensions', 'PepperFlash', 'WidevineCdm',
  ]);

  for (const item of itemsToCopy) {
    const srcPath = path.join(src, item);
    const dstPath = path.join(dst, item);
    try {
      const stat = await fs.stat(srcPath);
      if (stat.isDirectory()) {
        if (skipDirs.has(item)) continue;
        await fs.copy(srcPath, dstPath, {
          filter: (p) => {
            const name = path.basename(p);
            return !skipDirs.has(name);
          }
        });
      } else if (stat.isFile()) {
        await fs.copy(srcPath, dstPath);
      }
    } catch (err) {
      console.warn(`⚠️  跳过 ${item}: ${err.message}`);
    }
  }

  console.log('✅ Chrome profile 复制完成');
}

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
app.whenReady().then(async () => {
  await ensureProfile();

  const profileDir = getAppProfileDir();
  app.commandLine.appendSwitch('user-data-dir', profileDir);
  app.commandLine.appendSwitch('enable-features', 'NetworkService,NetworkServiceInProcess');
  app.commandLine.appendSwitch('disable-features', 'ChromeWhatsNewUI');

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
    const result = await runPythonScript('run_playwright.py', ['check']);
    return result;
  } catch (err) {
    return { status: 'error', message: err.message };
  }
}

/**
 * 安装 Playwright 浏览器
 */
async function installPlaywrightBrowser() {
  try {
    const result = await runPythonScript('run_playwright.py', ['install']);
    return result;
  } catch (err) {
    return { status: 'error', message: err.message };
  }
}

/**
 * 执行猎聘搜索
 */
async function searchLiepin(keyword, maxResults = 50) {
  try {
    const result = await runPythonScript('run_playwright.py', [
      'search',
      keyword,
      String(maxResults),
    ]);
    return result;
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

ipcMain.handle('playwright:install', async () => {
  return await installPlaywrightBrowser();
});

ipcMain.handle('playwright:search', async (_event, keyword, maxResults) => {
  return await searchLiepin(keyword, maxResults);
});

ipcMain.handle('playwright:snapshot', async () => {
  const outPath = path.join(app.getPath('documents'), `liepin_snapshot_${Date.now()}.png`);
  try {
    const result = await runPythonScript('run_playwright.py', ['snapshot', '9222', outPath]);
    return { status: 'ok', path: outPath };
  } catch (err) {
    return { status: 'error', message: err.message };
  }
});

const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('path');
const { execSync, spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const { chromium } = require('playwright');

// —— 配置 ——
const TARGET_URL = 'https://www.liepin.com/';
const PLATFORM_NAME = '猎聘';
const STORAGE_PATH = path.join(os.homedir(), '.liepin_client', 'liepin_storage.json');
const CONFIG_PATH = path.join(os.homedir(), '.liepin_client', 'config.json');
const OUTPUT_DIR = path.join(os.homedir(), '.liepin_client', 'candidates');
const FEISHU_WEBHOOK = 'https://open.feishu.cn/open-apis/bot/v2/hook/7b488565d8454ef7a70d43f9539ec61e';
const FEISHU_APP_ID = 'cli_a917170b57f89cd6';
const FEISHU_APP_SECRET = '5jo3BXlMlZUuwYWsdVrQQc07Rn4HM3Qz';
const BITABLE_APP_TOKEN = 'WXHObDl8eahIVEs06phcpzPDncb';
const BITABLE_TABLE_ID = 'tblxmUAD1XrA4XTP';

// —— 创建主窗口（猎聘网页）——
let mainWindow = null;

function createMainWindow() {
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

// —— 创建控制台窗口（搜索面板）——
let controlWindow = null;

function createControlWindow() {
  controlWindow = new BrowserWindow({
    width: 440,
    height: 640,
    minWidth: 380,
    minHeight: 520,
    title: '招聘工厂 · 搜索控制台',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    alwaysOnTop: false,
    skipTaskbar: false,
    show: false,
    resizable: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    }
  });

  controlWindow.loadFile(path.join(__dirname, 'control.html'));
  controlWindow.once('ready-to-show', () => controlWindow.show());
  
  // 点击猎聘窗口时不会隐藏控制台
  controlWindow.on('closed', () => { controlWindow = null; });
  
  // 阻止关闭（用户以为关的是猎聘页面）
  controlWindow.on('close', (e) => {
    if (mainWindow && !mainWindow.isDestroyed()) {
      // 如果猎聘窗口还在，点关闭控制台时最小化到dock
      e.preventDefault();
      controlWindow.hide();
    }
  });
}

// —— 保存配置 ——
function saveConfig(config) {
  try {
    fs.mkdirSync(path.dirname(CONFIG_PATH), { recursive: true });
    fs.writeFileSync(CONFIG_PATH, JSON.stringify(config, null, 2));
    return true;
  } catch { return false; }
}

function loadConfig() {
  try {
    if (fs.existsSync(CONFIG_PATH)) {
      return JSON.parse(fs.readFileSync(CONFIG_PATH, 'utf-8'));
    }
  } catch {}
  return {};
}

// —— 启动 ——
app.whenReady().then(() => {
  createMainWindow();
  createControlWindow();

  app.on('activate', () => {
    // 恢复所有窗口
    if (!mainWindow || mainWindow.isDestroyed()) {
      createMainWindow();
    } else {
      mainWindow.show();
    }
    if (!controlWindow || controlWindow.isDestroyed()) {
      createControlWindow();
    } else {
      controlWindow.show();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// ==============================================================
//  Playwright 引擎（纯 Node.js，不依赖 Python）
// ==============================================================

/**
 * 确保 Chromium 已安装，未安装则自动下载
 */
async function ensureChromium() {
  try {
    const execPath = chromium.executablePath();
    if (fs.existsSync(execPath)) {
      console.log(`✅ Chromium 就绪: ${execPath}`);
      return true;
    }
  } catch {}

  console.log('⏳ 下载 Chromium 浏览器（约 336MB，仅首次需要）...');
  return new Promise((resolve) => {
    const proc = spawn('npx', ['playwright', 'install', 'chromium'], {
      stdio: ['inherit', 'pipe', 'pipe'],
      shell: true,
    });

    proc.stdout.on('data', (d) => process.stdout.write(d));
    proc.stderr.on('data', (d) => process.stderr.write(d));

    proc.on('close', (code) => {
      if (code === 0) {
        console.log('✅ Chromium 下载完成');
        resolve(true);
      } else {
        console.error('❌ Chromium 下载失败');
        resolve(false);
      }
    });

    proc.on('error', (e) => {
      console.error(`❌ Chromium 下载异常: ${e.message}`);
      resolve(false);
    });
  });
}

/**
 * 加载本地登录态
 */
function loadCookies() {
  try {
    if (fs.existsSync(STORAGE_PATH)) {
      const data = JSON.parse(fs.readFileSync(STORAGE_PATH, 'utf-8'));
      return data.cookies || [];
    }
  } catch {}
  return [];
}

/**
 * 保存登录态
 */
function saveCookies(context) {
  return context.cookies().then((cookies) => {
    const state = { cookies, updated: new Date().toISOString() };
    fs.mkdirSync(path.dirname(STORAGE_PATH), { recursive: true });
    fs.writeFileSync(STORAGE_PATH, JSON.stringify(state, null, 2));
    return cookies.length;
  });
}

/**
 * 同步到飞书（群 + Bitable）
 */
async function syncToFeishu(candidates, keyword) {
  const results = { bitable: 0, group: false };
  if (!candidates || candidates.length === 0) return results;

  try {
    // 获取 token
    const tokenRes = await fetch('https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ app_id: FEISHU_APP_ID, app_secret: FEISHU_APP_SECRET }),
    });
    const tokenData = await tokenRes.json();
    const token = tokenData.tenant_access_token;
    if (!token) return results;

    const headers = { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' };
    const nowMs = Date.now();

    // 批量写入 Bitable
    const records = candidates.map((c) => ({
      fields: Object.fromEntries(
        Object.entries({
          姓名: c.name || '',
          年龄: c.age ? parseInt(c.age) : null,
          工作年限: c.years || '',
          学历: c.edu || '',
          所在城市: c.location || '',
          当前公司: c.company || '',
          当前职位: c.position || '',
          求职期望: c.expect || '',
          期望薪酬: c.salary || '',
          猎聘链接: { link: c.link || '', text: '查看简历' },
          关键词: keyword,
          抓取时间: nowMs,
        }).filter(([, v]) => v !== null && v !== '' && !(Array.isArray(v) && v.length === 0))
      ),
    }));

    let total = 0;
    for (let i = 0; i < records.length; i += 20) {
      const batch = records.slice(i, i + 20);
      const resp = await fetch(
        `https://open.feishu.cn/open-apis/bitable/v1/apps/${BITABLE_APP_TOKEN}/tables/${BITABLE_TABLE_ID}/records/batch_create`,
        { method: 'POST', headers, body: JSON.stringify({ records: batch }) }
      );
      const data = await resp.json();
      if (data.code === 0) total += batch.length;
    }
    results.bitable = total;

    // 飞书群通知
    const top = candidates.slice(0, 10);
    const preview = top
      .map((c) => `  ${c.name || '?'} ${c.age ? c.age + '岁' : ''} ${c.company || ''} ${c.position || ''}`.trim())
      .join('\n');

    await fetch(FEISHU_WEBHOOK, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        msg_type: 'text',
        content: {
          text: `🔍 猎聘搜索完成\n关键词: ${keyword}\n共 ${candidates.length} 人, 入库 ${total} 人\n\n📋 预览：\n${preview}`,
        },
      }),
    });
    results.group = true;
  } catch (e) {
    console.error('飞书同步异常:', e.message);
  }
  return results;
}

/**
 * 自动安装 Chromium（如果未安装）
 */
async function autoInstallChromium() {
  try {
    const execPath = chromium.executablePath();
    if (execPath && fs.existsSync(execPath)) {
      return { status: 'ready', message: 'Chromium 就绪' };
    }
  } catch {}

  console.log('⏳ 首次运行，自动安装 Chromium 浏览器...');
  try {
    execSync('npx playwright install chromium', { stdio: 'inherit', timeout: 600000 });
    return { status: 'ready', message: 'Chromium 安装完成' };
  } catch (e) {
    return { status: 'error', message: `安装失败: ${e.message}` };
  }
}

/**
 * 猎聘搜索核心
 */
async function searchLiepin(keyword = 'CTO', maxResults = 50) {
  console.log(`🔍 搜索: ${keyword} (最多${maxResults}人)`);

  // 确保 Chromium 已安装
  const installResult = await autoInstallChromium();
  if (installResult.status === 'error') {
    return { status: 'error', message: installResult.message };
  }

  const candidates = [];
  const cookies = loadCookies();
  console.log(`  📥 登录态: ${cookies.length} cookies`);

  const browser = await chromium.launch({
    headless: false,
    args: [
      '--no-first-run',
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--disable-dev-shm-usage',
      '--disable-blink-features=AutomationControlled',
    ],
  });

  try {
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      userAgent:
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    });

    if (cookies.length > 0) {
      await context.addCookies(cookies);
    }

    const page = await context.newPage();

    // 导航
    console.log('  🌐 打开猎聘找简历页面...');
    await page.goto('https://h.liepin.com/search/getConditionItem', {
      waitUntil: 'domcontentloaded',
      timeout: 30000,
    });
    await page.waitForTimeout(3000);
    await page.waitForLoadState('networkidle');

    // 首次保存登录态
    if (cookies.length === 0) {
      const n = await saveCookies(context);
      console.log(`  💾 登录态已保存 (${n} cookies)`);
    }

    // 清空筛选条件
    try {
      const clearBtn = page.locator('text=清空筛选条件');
      if (await clearBtn.isVisible({ timeout: 2000 })) {
        await clearBtn.click();
        await page.waitForTimeout(1500);
      }
    } catch {}

    // 输入关键词
    console.log(`  ⌨️  输入: ${keyword}`);
    try {
      const rc1 = page.locator('#rc_select_1');
      await rc1.waitFor({ state: 'visible', timeout: 5000 });
      await rc1.focus();
      await rc1.clear();
      await rc1.fill(keyword);
      await page.waitForTimeout(400);

      // 验证 + JS 注入备选
      const actual = await page.evaluate("document.getElementById('rc_select_1').value");
      if (!actual.includes(keyword)) {
        await page.evaluate(`
          var el = document.getElementById('rc_select_1');
          var setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
          setter.call(el, '${keyword.replace(/'/g, "\\'")}');
          el.dispatchEvent(new Event('input', {bubbles: true}));
          el.dispatchEvent(new Event('change', {bubbles: true}));
        `);
        await page.waitForTimeout(400);
      }
    } catch (e) {
      console.error(`  ⚠️  输入异常: ${e.message}`);
    }

    // 点击搜索
    console.log('  🔍 执行搜索...');
    try {
      await page.getByRole('button', { name: /搜 索/ }).click({ timeout: 5000 });
    } catch {
      try {
        await page.locator('button').filter({ hasText: '搜 索' }).first().click({ timeout: 3000 });
      } catch {
        await page.keyboard.press('Enter');
      }
    }
    await page.waitForTimeout(5000);

    // 翻页提取候选人
    const maxPages = Math.max(1, Math.ceil(maxResults / 30));
    for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
      try {
        await page.waitForSelector('table.new-resume-card', { timeout: 15000 });
        await page.waitForTimeout(2000);
      } catch {
        console.log(`  ⚠️  第${pageNum}页无结果`);
        break;
      }

      const rows = await page.evaluate(() => {
        const items = [];
        const table = document.querySelector('table.new-resume-card');
        if (!table) return items;
        const rows = table.querySelectorAll('tbody tr[data-tlg-ext]');
        for (const row of rows) {
          try {
            const ext = row.getAttribute('data-tlg-ext') || '';
            let resId = '';
            try { resId = JSON.parse(decodeURIComponent(ext)).res_id || ''; } catch {}
            if (!resId) continue;

            const text = row.innerText;
            const lines = text.split('\n').map((l) => l.trim()).filter((l) => l);
            if (lines.length < 4) continue;

            let name = '';
            const ems = row.querySelectorAll('em');
            for (const em of ems) {
              const t = em.innerText.trim();
              if (t.includes('**') && t.length <= 6 && !t.includes('活跃') && !t.includes('在线')) {
                name = t;
                break;
              }
            }
            if (!name) continue;

            let age = '', years = '', edu = '', location = '', expect = '', salary = '', company = '', position = '', active = '';
            const first = lines[0] || '';
            if (first.includes('今天活跃')) active = '今天活跃';
            else if (first.includes('3天内活跃')) active = '3天内活跃';
            else if (first.includes('7天内活跃')) active = '7天内活跃';
            else if (first.includes('30天内活跃')) active = '30天内活跃';
            else if (first.includes('在线')) active = '在线';

            for (const l of lines) {
              let m;
              if (!age && l.match(/\u5c81/)) { m = l.match(/(\d+)\u5c81/); if (m) age = m[1]; }
              if (!years && l.match(/\u5de5\u4f5c/)) { m = l.match(/\u5de5\u4f5c(\d+)\u5e74/); if (m) years = m[1]; }
              if (!edu && l.match(/\u535a\u58eb|\u7855\u58eb|MBA|\u672c\u79d1|\u5927\u4e13/)) edu = l;
              if (!location && (l.includes('\u533a') || l.includes('\u5e02')) && !l.includes('\u6d3b') && !l.includes('\u5728\u7ebf') && !l.includes('\u5929\u5185') && !l.includes('\u5c81') && !l.includes('\u5de5\u4f5c')) location = l;
              if (l.includes('\u6c42\u804c\u671f\u671b')) {
                const ex = l.split('\u6c42\u804c\u671f\u671b').pop().replace(/^[\s\u3000-\u303f]+/, '').trim();
                if (ex) expect = ex;
              }
              if (!salary) { m = l.match(/\d+[kK]\s*[-~\u2013\u2014]\s*\d+[kK]/); if (m) salary = m[0]; }
              if (l.includes('\u00b7') && (l.includes('\u516c\u53f8') || l.includes('\u79d1\u6280'))) {
                const parts = l.split('\u00b7');
                if (parts.length >= 2) { company = parts[0].trim(); position = parts.slice(1).join(' \u00b7 ').trim(); }
              }
            }

            items.push({
              name, age, years, edu, location, expect, salary, company, position, active,
              link: 'https://h.liepin.com/resume/showresumedetail/?res_id_encode=' + resId,
            });
          } catch {}
        }
        return items;
      });

      candidates.push(...rows);
      console.log(`  📄 第${pageNum}页: ${rows.length}人 (累计${candidates.length})`);

      if (candidates.length >= maxResults) {
        candidates.length = maxResults;
        break;
      }

      // 翻页
      if (pageNum < maxPages) {
        try {
          const nextBtn = await page.querySelector('.ant-pagination-next');
          if (nextBtn) {
            await nextBtn.click();
            const delay = 5000 + Math.random() * 7000;
            console.log(`  ➡️  翻到第${pageNum + 1}页 (等待${Math.round(delay / 1000)}s)...`);
            await page.waitForTimeout(delay);
          } else {
            break;
          }
        } catch {
          break;
        }
      }
    }

    // 保存登录态
    await saveCookies(context);

    // 保存 CSV
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const safeKw = keyword.replace(/[^\w]/g, '_');
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    const csvPath = path.join(OUTPUT_DIR, `liepin_${safeKw}_${ts}.csv`);

    const csvHeader = 'name,age,years,edu,location,company,position,expect,salary,active,link\n';
    const csvRows = candidates
      .map((c) =>
        [
          c.name || '',
          c.age || '',
          c.years || '',
          c.edu || '',
          c.location || '',
          c.company || '',
          c.position || '',
          c.expect || '',
          c.salary || '',
          c.active || '',
          c.link || '',
        ]
          .map((v) => `"${v.replace(/"/g, '""')}"`)
          .join(',')
      )
      .join('\n');
    fs.writeFileSync(csvPath, '\uFEFF' + csvHeader + csvRows, 'utf-8');
    console.log(`  📁 CSV: ${csvPath}`);

    // 同步 — 根据用户配置选择通道
    const config = loadConfig();
    const syncResults = {};
    
    if (config.channelFeishu !== false) {
      console.log('  📤 同步到飞书...');
      const feishuResult = await syncToFeishu(candidates, keyword);
      if (feishuResult.bitable > 0) console.log(`  ✅ 飞书 Bitable: ${feishuResult.bitable} 条`);
      if (feishuResult.group) console.log('  ✅ 飞书群通知已发送');
      syncResults.feishu = feishuResult;
    }
    
    if (config.channelWecom) {
      console.log('  📤 同步到企微...');
      try {
        await syncToWecom(candidates, keyword, config);
        syncResults.wecom = true;
      } catch (e) {
        console.error('  ❌ 企微同步失败:', e.message);
        syncResults.wecom = false;
      }
    }

    await browser.close();

    return {
      status: 'ok',
      keyword,
      count: candidates.length,
      csv: csvPath,
      candidates: candidates.slice(0, 20),
      feishu: syncResults.feishu || { bitable: 0, group: false },
    };
  } catch (e) {
    await browser.close().catch(() => {});
    console.error(`❌ 搜索异常:`, e);
    return { status: 'error', message: e.message };
  }
}

/**
 * 检查环境状态
 */
async function checkEnvironment() {
  const results = [];

  // Playwright
  try {
    results.push({ name: 'Playwright', ok: true, detail: require('playwright/package.json').version });
  } catch {
    results.push({ name: 'Playwright', ok: false, detail: '模块未加载' });
  }

  // Chromium
  try {
    const execPath = chromium.executablePath();
    const exists = fs.existsSync(execPath);
    results.push({ name: 'Chromium', ok: exists, detail: exists ? execPath : '需要下载' });
  } catch {
    results.push({ name: 'Chromium', ok: false, detail: '未安装' });
  }

  // 登录态
  const cookies = loadCookies();
  results.push({
    name: '登录态',
    ok: cookies.length > 0,
    detail: cookies.length > 0 ? `${cookies.length} cookies` : '未登录',
  });

  // 网络
  try {
    const r = await fetch('https://h.liepin.com', { method: 'HEAD', signal: AbortSignal.timeout(5000) });
    results.push({ name: '网络', ok: true, detail: `猎聘可达 (${r.status})` });
  } catch {
    results.push({ name: '网络', ok: false, detail: '无法访问猎聘' });
  }

  return results;
}

// ==============================================================
//  IPC 通道
// ==============================================================

ipcMain.handle('get-platform', () => ({
  name: PLATFORM_NAME,
  url: TARGET_URL,
}));

ipcMain.handle('playwright:check', async () => {
  const results = await checkEnvironment();
  const allOk = results.every((r) => r.ok);
  return { status: allOk ? 'ready' : 'issues', checks: results };
});

ipcMain.handle('playwright:search', async (_event, keyword, maxResults) => {
  return await searchLiepin(keyword, maxResults);
});

/**
 * 同步到企微
 */
async function syncToWecom(candidates, keyword, config) {
  const webhook = config.wecomWebhook;
  if (!webhook) return false;

  const now = new Date().toLocaleString('zh-CN', { hour12: false });
  const lines = [`🔍 **招聘工厂 · 猎聘搜索结果 | ${now}**`];
  lines.push(`**关键词：** ${keyword}`);
  lines.push(`**共找到：** ${candidates.length} 人`);
  lines.push('');

  for (let i = 0; i < Math.min(candidates.length, 10); i++) {
    const c = candidates[i];
    const parts = [c.name || '?'];
    if (c.age) parts.push(`${c.age}岁`);
    if (c.company) parts.push(c.company);
    if (c.position) parts.push(c.position);
    lines.push(`${i + 1}. ${parts.join(' | ')}`);
  }
  if (candidates.length > 10) {
    lines.push(`\n... 共 ${candidates.length} 人`);
  }

  const resp = await fetch(webhook, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      msgtype: 'markdown',
      markdown: { content: lines.join('\n') },
    }),
  });
  const data = await resp.json();
  return data.errcode === 0;
}

ipcMain.handle('liepin:check', async () => {
  const cookies = loadCookies();
  return {
    status: cookies.length > 0 ? 'ok' : 'not_found',
    cookieCount: cookies.length,
    storagePath: STORAGE_PATH,
  };
});

ipcMain.handle('config:get', async () => {
  return loadConfig();
});

ipcMain.handle('config:save', async (_event, config) => {
  saveConfig(config);
  return { ok: true };
});

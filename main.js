const { app, BrowserWindow, ipcMain, shell, Tray, Menu, Notification } = require('electron');
const path = require('path');
const { execSync, spawn } = require('child_process');
const fs = require('fs');
const os = require('os');
const { chromium } = require('playwright');
const WebSocket = require('ws');

// —— 配置 ——
const TARGET_URL = 'https://www.liepin.com/';
const WS_SERVER = 'ws://8.135.58.6:7896/ws';
const PLATFORM_NAME = '猎聘';
const STORAGE_PATH = path.join(os.homedir(), '.liepin_client', 'liepin_storage.json');
const CONFIG_PATH = path.join(os.homedir(), '.liepin_client', 'config.json');
const OUTPUT_DIR = path.join(os.homedir(), '.liepin_client', 'candidates');
const FEISHU_APP_ID = 'cli_a917170b57f89cd6';
const FEISHU_APP_SECRET = '5jo3BXlMlZUuwYWsdVrQQc07Rn4HM3Qz';
const BITABLE_APP_TOKEN = 'WXHObDl8eahIVEs06phcpzPDncb';
const BITABLE_TABLE_ID = 'tblxmUAD1XrA4XTP';

// —— 状态 ——
let mainWindow = null;
let controlWindow = null;
let wsClient = null;
let wsReconnectTimer = null;
let currentSearch = null;

// ==============================================================
//  WebSocket 客户端（连接服务器，接收远程指令）
// ==============================================================

function getClientId() {
  const config = loadConfig();
  if (!config.clientId) {
    config.clientId = 'client_' + Date.now().toString(36) + Math.random().toString(36).slice(2, 8);
    saveConfig(config);
  }
  return config.clientId;
}

function connectWebSocket() {
  if (wsClient && wsClient.readyState === WebSocket.OPEN) return;

  const clientId = getClientId();
  const url = `${WS_SERVER}?client_id=${clientId}`;

  console.log(`🔗 WebSocket 连接中: ${url}`);

  try {
    wsClient = new WebSocket(url);

    wsClient.on('open', () => {
      console.log('✅ WebSocket 已连接');
      sendToControl('ws-status', { connected: true });
      if (wsReconnectTimer) {
        clearTimeout(wsReconnectTimer);
        wsReconnectTimer = null;
      }
    });

    wsClient.on('message', async (data) => {
      try {
        const msg = JSON.parse(data.toString());
        console.log('📩 收到指令:', msg);

        // 处理搜索指令
        if (msg.action === 'search') {
          const { keyword, max_count, task_id, reply_channel } = msg;
          sendToControl('task-received', { keyword, taskId: task_id });

          // 执行搜索（异步，不阻塞消息处理）
          currentSearch = { keyword, maxCount: max_count || 45, taskId: task_id, replyChannel: reply_channel || 'feishu' };
          executeRemoteSearch(currentSearch);

        } else if (msg.action === 'ping') {
          // 心跳回复
          wsClient.send(JSON.stringify({ action: 'pong', client_id: clientId }));
        }
      } catch (e) {
        console.error('❌ 指令解析失败:', e.message);
      }
    });

    wsClient.on('close', (code, reason) => {
      console.log(`🔌 WebSocket 断开 (${code}): ${reason || '无原因'}`);
      wsClient = null;
      sendToControl('ws-status', { connected: false });
      scheduleReconnect();
    });

    wsClient.on('error', (err) => {
      console.error('❌ WebSocket 错误:', err.message);
      wsClient = null;
      sendToControl('ws-status', { connected: false });
      scheduleReconnect();
    });
  } catch (e) {
    console.error('❌ WebSocket 连接失败:', e.message);
    scheduleReconnect();
  }
}

function scheduleReconnect() {
  if (wsReconnectTimer) return;
  wsReconnectTimer = setTimeout(() => {
    wsReconnectTimer = null;
    connectWebSocket();
  }, 10000); // 10秒后重连
}

function sendToServer(msg) {
  if (wsClient && wsClient.readyState === WebSocket.OPEN) {
    wsClient.send(JSON.stringify(msg));
  }
}

function sendToControl(channel, data) {
  if (controlWindow && !controlWindow.isDestroyed()) {
    controlWindow.webContents.send(channel, data);
  }
}

/**
 * 执行远程下发的搜索任务
 */
async function executeRemoteSearch(task) {
  try {
    const result = await searchLiepin(task.keyword, task.maxCount);

    // 通知服务器结果
    sendToServer({
      action: 'search_result',
      client_id: getClientId(),
      task_id: task.taskId,
      reply_channel: task.replyChannel,
      status: result.status,
      count: result.count || 0,
      candidates: (result.candidates || []).slice(0, 10),
      csv: result.csv,
      feishu: result.feishu || { bitable: 0, group: false },
      error: result.message,
    });

    // 显示通知
    if (result.status === 'ok') {
      new Notification({
        title: '搜索完成',
        body: `「${task.keyword}」找到 ${result.count} 人`,
      }).show();
      sendToControl('task-complete', { status: 'ok', count: result.count, keyword: task.keyword });
    } else {
      new Notification({
        title: '搜索失败',
        body: result.message,
      }).show();
      sendToControl('task-complete', { status: 'error', message: result.message });
    }
  } catch (e) {
    console.error('❌ 远程搜索异常:', e);
    sendToServer({
      action: 'search_result',
      client_id: getClientId(),
      task_id: task.taskId,
      reply_channel: task.replyChannel,
      status: 'error',
      error: e.message,
    });
    sendToControl('task-complete', { status: 'error', message: e.message });
  } finally {
    currentSearch = null;
  }
}

// ==============================================================
//  窗口管理
// ==============================================================

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
    webPreferences: { preload: path.join(__dirname, 'preload.js') },
  });

  mainWindow.loadURL(TARGET_URL);
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: 'deny' };
  });
  mainWindow.on('closed', () => { mainWindow = null; });
}

function createControlWindow() {
  controlWindow = new BrowserWindow({
    width: 440,
    height: 640,
    minWidth: 380,
    minHeight: 520,
    title: '招聘工厂 · 搜索控制台',
    icon: path.join(__dirname, 'assets', 'icon.png'),
    resizable: true,
    show: false,
    // 控制台窗口只加载本地control.html，安全可控，关闭隔离确保按钮可点击
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: false,
      nodeIntegration: true,
    },
  });

  controlWindow.loadFile(path.join(__dirname, 'control.html'));
  controlWindow.once('ready-to-show', () => controlWindow.show());

  controlWindow.on('close', (e) => {
    // 直接关闭，不再隐藏（没有主窗口了）
  });
  controlWindow.on('closed', () => { controlWindow = null; });
}

// ==============================================================
//  配置
// ==============================================================

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

// ==============================================================
//  Playwright 引擎
// ==============================================================

async function ensureChromium() {
  try {
    const execPath = chromium.executablePath();
    if (execPath && fs.existsSync(execPath)) {
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
      console.log(code === 0 ? '✅ Chromium 下载完成' : '❌ Chromium 下载失败');
      resolve(code === 0);
    });
    proc.on('error', (e) => {
      console.error(`❌ Chromium 下载异常: ${e.message}`);
      resolve(false);
    });
  });
}

function loadCookies() {
  try {
    if (fs.existsSync(STORAGE_PATH)) {
      return JSON.parse(fs.readFileSync(STORAGE_PATH, 'utf-8')).cookies || [];
    }
  } catch {}
  return [];
}

function saveCookies(context) {
  return context.cookies().then((cookies) => {
    const state = { cookies, updated: new Date().toISOString() };
    fs.mkdirSync(path.dirname(STORAGE_PATH), { recursive: true });
    fs.writeFileSync(STORAGE_PATH, JSON.stringify(state, null, 2));
    return cookies.length;
  });
}

async function syncToFeishu(candidates, keyword) {
  const results = { bitable: 0, group: false };
  if (!candidates || candidates.length === 0) return results;

  try {
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
    const records = candidates.map((c) => ({
      fields: Object.fromEntries(
        Object.entries({
          姓名: c.name || '',
          年龄: c.age ? parseInt(c.age) : null,
          工作年限: c.years || '',
          学历: c.edu || '',
          所在地: c.location || '',
          公司: c.company || '',
          职位: c.position || '',
          求职期望: c.expect || '',
          猎聘链接: { link: c.link || '', text: '查看简历' },
          来源: '猎聘',
          应聘岗位: keyword,
          入库时间: nowMs,
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

    // 推送飞书群通知（用API方式，不走Webhook）
    try {
      const top = candidates.slice(0, 10);
      const preview = top.map(c =>
        `  ${c.name || '?'} ${c.age ? c.age + '岁' : ''} ${c.company || ''} ${c.position || ''}`
      ).join('\n');
      const now = new Date();
      const timeStr = now.toLocaleString('zh-CN', { hour12: false });
      const text = [
        '🔍 **猎聘搜索完成**',
        '',
        '**关键词：** ' + keyword,
        '**数量：** ' + candidates.length + ' 人',
        '**时间：** ' + timeStr,
        '',
        '**候选人速览：**',
        preview,
        '',
        '✅ 已自动入库 Bitable | 共入库 ' + total + ' 条'
      ].join('\n');
      // 用飞书 API 发消息到群聊
      const msgResp = await fetch('https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id', {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}`, 'Content-Type': 'application/json' },
        body: JSON.stringify({
          receive_id: 'oc_d04f6841458b08b1ca4f3126c302e3d3',
          msg_type: 'text',
          content: JSON.stringify({ text }),
        }),
      });
      const msgData = await msgResp.json();
      results.group = msgData.code === 0;
      console.log(`  飞书群通知: ${results.group ? '成功' : '失败 ' + JSON.stringify(msgData)}`);
    } catch (e) {
      console.error(`  飞书群通知异常: ${e.message}`);
    }
  } catch (e) {
    console.error(`  飞书同步异常: ${e.message}`);
  }
  return results;
}

async function autoInstallChromium() {
  try {
    const execPath = chromium.executablePath();
    if (execPath && fs.existsSync(execPath)) {
      return { status: 'ready', message: 'Chromium 就绪' };
    }
  } catch {}
  return { status: 'need_install' };
}

async function searchLiepin(keyword = 'CTO', maxResults = 45) {
  console.log(`🔍 搜索: ${keyword} (最多${maxResults}人)`);

  const installResult = await autoInstallChromium();
  if (installResult.status === 'need_install') {
    const ok = await ensureChromium();
    if (!ok) return { status: 'error', message: 'Chromium 安装失败' };
  }

  const candidates = [];
  const cookies = loadCookies();
  console.log(`  📥 登录态: ${cookies.length} cookies`);

  // ⚠️ 深度记忆：必须使用 chromium.launch() 启动独立 Playwright Chromium
  // 绝对禁止使用 connect_over_cdp() 或任何方式连接用户正在使用的 Chrome
  // 禁止在 args 中使用 --user-data-dir（新版 Playwright 不支持，要用 launchPersistentContext）
  const browser = await chromium.launch({
    headless: false,
    args: [
      '--no-first-run', '--no-sandbox', '--disable-setuid-sandbox',
      '--disable-dev-shm-usage', '--disable-blink-features=AutomationControlled',
    ],
  });

  try {
    const context = await browser.newContext({
      viewport: { width: 1920, height: 1080 },
      userAgent: 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
    });
    if (cookies.length > 0) await context.addCookies(cookies);

    const page = await context.newPage();
    await page.goto('https://h.liepin.com/search/getConditionItem', { waitUntil: 'domcontentloaded', timeout: 30000 });
    await page.waitForTimeout(3000);
    await page.waitForLoadState('networkidle');

    if (cookies.length === 0) await saveCookies(context);

    try {
      const clearBtn = page.locator('text=清空筛选条件');
      if (await clearBtn.isVisible({ timeout: 2000 })) {
        await clearBtn.click();
        await page.waitForTimeout(1500);
      }
    } catch {}

    try {
      const rc1 = page.locator('#rc_select_1');
      await rc1.waitFor({ state: 'visible', timeout: 5000 });
      await rc1.focus();
      await rc1.clear();
      await rc1.fill(keyword);
      await page.waitForTimeout(400);
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

    try { await page.getByRole('button', { name: /搜 索/ }).click({ timeout: 5000 }); }
    catch {
      try { await page.locator('button').filter({ hasText: '搜 索' }).first().click({ timeout: 3000 }); }
      catch { await page.keyboard.press('Enter'); }
    }
    await page.waitForTimeout(5000);

    const maxPages = Math.max(1, Math.ceil(maxResults / 30));
    for (let pageNum = 1; pageNum <= maxPages; pageNum++) {
      try {
        await page.waitForSelector('table.new-resume-card', { timeout: 15000 });
        await page.waitForTimeout(2000);
      } catch { break; }

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
            for (const em of row.querySelectorAll('em')) {
              const t = em.innerText.trim();
              if (t.includes('**') && t.length <= 6 && !t.includes('活跃') && !t.includes('在线')) { name = t; break; }
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
              if (!location && (l.includes('\u533a') || l.includes('\u5e02')) && !l.includes('\u6d3b') && !l.includes('\u5728\u7ebf') && !l.includes('\u5929\u5185')) location = l;
              if (l.includes('\u6c42\u804c\u671f\u671b')) { const ex = l.split('\u6c42\u804c\u671f\u671b').pop().replace(/^[\s\u3000-\u303f]+/, '').trim(); if (ex) expect = ex; }
              if (!salary) { m = l.match(/\d+[kK]\s*[-~\u2013\u2014]\s*\d+[kK]/); if (m) salary = m[0]; }
              if (l.includes('\u00b7') && (l.includes('\u516c\u53f8') || l.includes('\u79d1\u6280'))) { const parts = l.split('\u00b7'); if (parts.length >= 2) { company = parts[0].trim(); position = parts.slice(1).join(' \u00b7 ').trim(); } }
            }
            items.push({ name, age, years, edu, location, expect, salary, company, position, active, link: 'https://h.liepin.com/resume/showresumedetail/?res_id_encode=' + resId });
          } catch {}
        }
        return items;
      });

      candidates.push(...rows);
      console.log(`  📄 第${pageNum}页: ${rows.length}人 (累计${candidates.length})`);
      if (candidates.length >= maxResults) { candidates.length = maxResults; break; }

      if (pageNum < maxPages) {
        try {
          const nextBtn = await page.querySelector('.ant-pagination-next');
          if (nextBtn) { await nextBtn.click(); await page.waitForTimeout(5000 + Math.random() * 7000); } else break;
        } catch { break; }
      }
    }

    await saveCookies(context);

    // 保存 CSV
    const ts = new Date().toISOString().replace(/[:.]/g, '-').slice(0, 19);
    const safeKw = keyword.replace(/[^\w]/g, '_');
    fs.mkdirSync(OUTPUT_DIR, { recursive: true });
    const csvPath = path.join(OUTPUT_DIR, `liepin_${safeKw}_${ts}.csv`);
    const csvHeader = 'name,age,years,edu,location,company,position,expect,salary,active,link\n';
    const csvRows = candidates.map((c) => ['name','age','years','edu','location','company','position','expect','salary','active','link'].map(k => `"${(c[k]||'').replace(/"/g,'""')}"`).join(',')).join('\n');
    fs.writeFileSync(csvPath, '\uFEFF' + csvHeader + csvRows, 'utf-8');
    console.log(`  📁 CSV: ${csvPath}`);

    // 同步飞书 Bitable + 群通知
    const feishuResult = await syncToFeishu(candidates, keyword);
    if (feishuResult.bitable > 0) console.log(`  ✅ 飞书 Bitable: ${feishuResult.bitable} 条`);
    if (feishuResult.group) console.log(`  ✅ 飞书群通知已发送`);

    // 同步企微（如果配置了）
    const searchConfig = loadConfig();
    let wecomSent = false;
    if (searchConfig.channelWecom && searchConfig.wecomWebhook) {
      try {
        console.log(`  📤 同步到企微...`);
        const now = new Date().toLocaleString('zh-CN', { hour12: false });
        const top10 = candidates.slice(0, 10);
        const preview = top10.map(c =>
          `${c.name || '?'} ${c.age ? c.age + '岁' : ''} ${c.company || ''} ${c.position || ''}`
        ).join('\n');
        const wecomText = [
          `🔍 **猎聘搜索完成 | ${now}**`,
          `**关键词：** ${keyword}`,
          `**数量：** ${candidates.length} 人`,
          '',
          `**候选人速览：**`,
          preview,
          '',
          `✅ 已同步 Bitable`,
        ].join('\n');
        const whResp = await fetch(searchConfig.wecomWebhook, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ msgtype: 'markdown', markdown: { content: wecomText } }),
        });
        const whData = await whResp.json();
        wecomSent = whData.errcode === 0;
        console.log(`  企微通知: ${wecomSent ? '成功' : '失败'}`);
      } catch (e) {
        console.error(`  企微通知异常: ${e.message}`);
      }
    }

    await browser.close();
    return {
      status: 'ok',
      keyword,
      count: candidates.length,
      csv: csvPath,
      candidates: candidates.slice(0, 20),
      feishu: feishuResult,
      wecom: wecomSent,
    };
  } catch (e) {
    await browser.close().catch(() => {});
    console.error(`❌ 搜索异常:`, e);
    return { status: 'error', message: e.message };
  }
}

async function checkEnvironment() {
  const results = [];
  try { results.push({ name: 'Playwright', ok: true, detail: require('playwright/package.json').version }); }
  catch { results.push({ name: 'Playwright', ok: false, detail: '模块未加载' }); }

  try { const p = chromium.executablePath(); results.push({ name: 'Chromium', ok: fs.existsSync(p), detail: fs.existsSync(p) ? p : '需要下载' }); }
  catch { results.push({ name: 'Chromium', ok: false, detail: '未安装' }); }

  const cookies = loadCookies();
  results.push({ name: '登录态', ok: cookies.length > 0, detail: cookies.length > 0 ? `${cookies.length} cookies` : '未登录' });

  results.push({ name: '服务连接', ok: wsClient && wsClient.readyState === WebSocket.OPEN, detail: (wsClient && wsClient.readyState === WebSocket.OPEN) ? '已连接' : '未连接' });

  try { const r = await fetch('https://h.liepin.com', { method: 'HEAD', signal: AbortSignal.timeout(5000) }); results.push({ name: '网络', ok: true, detail: `猎聘可达 (${r.status})` }); }
  catch { results.push({ name: '网络', ok: false, detail: '无法访问猎聘' }); }

  return results;
}

// ==============================================================
//  应用启动
// ==============================================================

app.whenReady().then(async () => {
  // 去掉猎聘主窗口（避免用户混淆，搜索使用独立 Playwright Chromium 浏览器）
  createControlWindow();

  // 开机自启
  app.setLoginItemSettings({ openAtLogin: true });

  // 连接 WebSocket
  connectWebSocket();

  app.on('activate', () => {
    if (!controlWindow || controlWindow.isDestroyed()) createControlWindow(); else controlWindow.show();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});

// ==============================================================
//  IPC 通道
// ==============================================================

ipcMain.handle('get-platform', () => ({ name: PLATFORM_NAME, url: TARGET_URL }));

ipcMain.handle('playwright:check', async () => {
  const results = await checkEnvironment();
  return { status: results.every((r) => r.ok) ? 'ready' : 'issues', checks: results };
});

ipcMain.handle('playwright:search', async (_event, keyword, maxResults) => {
  return await searchLiepin(keyword, maxResults);
});

ipcMain.handle('liepin:check', async () => {
  const cookies = loadCookies();
  return { status: cookies.length > 0 ? 'ok' : 'not_found', cookieCount: cookies.length, storagePath: STORAGE_PATH };
});

ipcMain.handle('config:get', async () => loadConfig());
ipcMain.handle('config:save', async (_event, config) => { saveConfig(config); return { ok: true }; });

ipcMain.handle('ws:status', async () => {
  return { connected: wsClient && wsClient.readyState === WebSocket.OPEN, clientId: getClientId() };
});

ipcMain.handle('ws:reconnect', async () => {
  if (wsClient) { wsClient.close(); wsClient = null; }
  connectWebSocket();
  return { ok: true };
});

ipcMain.handle('browser:open-login', async () => {
  // 打开独立 Playwright Chromium 浏览器让用户登录猎聘
  // ⚠️ 使用 chromium.launch()，绝对不碰用户的 Chrome
  // 登录态自动保存，后续搜索带上 cookies 无需重复登录
  try {
    const cookies = loadCookies();
    const browser = await chromium.launch({
      headless: false,
      args: ['--no-first-run', '--no-sandbox', '--disable-setuid-sandbox'],
    });
    const context = await browser.newContext();
    // 如果有已保存的登录态，直接带上
    if (cookies.length > 0) await context.addCookies(cookies);
    const page = await context.newPage();
    await page.goto('https://h.liepin.com/search/getConditionItem', { waitUntil: 'domcontentloaded' });
    
    // 监听浏览器关闭，保存登录态
    const checkInterval = setInterval(async () => {
      try {
        const pages = context.pages();
        if (pages.length === 0 || pages.every(p => p.isClosed())) {
          clearInterval(checkInterval);
          await saveCookies(context);
          await browser.close();
          console.log('💾 登录态已保存');
        }
      } catch {}
    }, 5000);
    
    // 5 分钟超时关闭
    setTimeout(async () => {
      clearInterval(checkInterval);
      try {
        await saveCookies(context);
        await browser.close();
      } catch {}
    }, 300000);
    return { status: 'ok' };
  } catch (e) {
    return { status: 'error', message: e.message };
  }
});

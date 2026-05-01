const { app, BrowserWindow, screen } = require('electron');
const path = require('path');
const fs = require('fs');

app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: 1280, height: 800,
    show: false,  // 不显示窗口，减少资源
    webPreferences: { offscreen: true }  // 离屏渲染
  });

  win.loadURL('https://www.liepin.com/');

  // 等待加载完成
  await new Promise(r => setTimeout(r, 15000));

  // 截屏
  const image = await win.webContents.capturePage();
  const png = image.toPNG();
  fs.writeFileSync('/Users/brandon/.openclaw/workspace/liepin-snapshot.png', png);
  console.log('screenshot saved, size:', png.length);
  console.log('page title:', await win.webContents.executeJavaScript('document.title'));
  console.log('url:', win.webContents.getURL());

  // 检查页面是否有猎聘元素
  const hasLogin = await win.webContents.executeJavaScript(
    'document.body.innerText.includes("登录") || document.body.innerText.includes("注册")'
  );
  console.log('has login text:', hasLogin);

  // 检查 cookies
  const cookies = await win.webContents.session.cookies.get({});
  console.log('cookies count:', cookies.length);
  if (cookies.length > 0) {
    console.log('sample cookie:', JSON.stringify(cookies[0]));
  }

  app.quit();
});

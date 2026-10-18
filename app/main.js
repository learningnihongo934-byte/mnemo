// Mnemo desktop app: starts the Python brain, shows the UI, and hosts the browser Mnemo controls.

const { app, BrowserWindow, WebContentsView, ipcMain, shell, dialog, powerSaveBlocker } = require('electron');
const { spawn } = require('child_process');
const crypto = require('crypto');
const net = require('net');
const path = require('path');
const fs = require('fs');
const WebSocket = require('ws');
const ctl = require('./browser-control');

// Where the Python brain lives: bundled inside Mnemo.app, or the project folder when run from source.
const ROOT = app.isPackaged ? path.join(process.resourcesPath, 'brain') : path.resolve(__dirname, '..');
const ICON = path.join(__dirname, 'build', 'icon-1024.png');
const TOKEN = crypto.randomBytes(16).toString('hex');
let PORT = 0;
let win, view, py, bridge;

// Python with Mnemo's dependencies: $MNEMO_PYTHON, the environment recorded when the app was
// built (build-config.json), ~/.mnemo/venv, the project's .venv, then plain python3.
function pythonPath() {
  const bin = process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python';
  const candidates = [process.env.MNEMO_PYTHON];
  try { candidates.push(JSON.parse(fs.readFileSync(path.join(__dirname, 'build-config.json'), 'utf8')).python); } catch {}
  candidates.push(path.join(app.getPath('home'), '.mnemo', 'venv', bin), path.join(path.resolve(__dirname, '..'), '.venv', bin));
  return candidates.find((p) => p && fs.existsSync(p)) || 'python3';
}

function freePort() {
  return new Promise((resolve) => {
    const s = net.createServer();
    s.listen(0, '127.0.0.1', () => { const p = s.address().port; s.close(() => resolve(p)); });
  });
}

async function api(method, route, body) {
  const res = await fetch(`http://127.0.0.1:${PORT}${route}`, {
    method, headers: { 'content-type': 'application/json', 'x-mnemo-token': TOKEN },
    body: body ? JSON.stringify(body) : undefined,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(data.detail || data.error || res.statusText);
  return data;
}

async function startBrain() {
  PORT = await freePort();
  py = spawn(pythonPath(), ['-m', 'mnemo.server', '--port', String(PORT)], {
    cwd: ROOT, env: { ...process.env, MNEMO_TOKEN: TOKEN, PYTHONUNBUFFERED: '1' },
  });
  py.stdout.on('data', (d) => process.stdout.write(`[brain] ${d}`));
  py.stderr.on('data', (d) => process.stderr.write(`[brain] ${d}`));
  py.on('exit', (code) => win && !win.isDestroyed() && win.webContents.send('brain-exit', code));
  for (let i = 0; i < 600; i++) {
    try { await api('GET', '/api/status'); return; } catch { await new Promise((r) => setTimeout(r, 250)); }
  }
  throw new Error('Mnemo brain did not start');
}

// ---------------------------------------------------------------- browser control
const wc = () => view.webContents;
const wait = (ms) => new Promise((r) => setTimeout(r, ms));

function waitForLoad(timeout = 15000) {
  return new Promise((resolve) => {
    const done = () => { clearTimeout(t); wc().off('did-stop-loading', done); resolve(); };
    const t = setTimeout(done, timeout);
    wc().on('did-stop-loading', done);
  });
}

async function settle() {
  await wait(250);
  if (wc().isLoading()) await waitForLoad(10000);
}

async function mouseClick(x, y) {
  for (const type of ['mouseMove', 'mouseDown', 'mouseUp']) {
    wc().sendInputEvent({ type, x, y, button: 'left', clickCount: 1 });
    await wait(30);
  }
}

async function pressKey(key) {
  const k = { enter: 'Enter', return: 'Enter', tab: 'Tab', escape: 'Escape', esc: 'Escape', backspace: 'Backspace',
    down: 'Down', up: 'Up', left: 'Left', right: 'Right', pagedown: 'PageDown', pageup: 'PageUp', space: 'Space' }[String(key).toLowerCase()] || key;
  wc().sendInputEvent({ type: 'keyDown', keyCode: k });
  if (k === 'Enter') wc().sendInputEvent({ type: 'char', keyCode: '\r' });
  wc().sendInputEvent({ type: 'keyUp', keyCode: k });
}

const handlers = {
  async navigate({ url }) {
    if (!/^https?:\/\//i.test(url)) throw new Error('only http(s) URLs');
    const p = wc().loadURL(url).catch(() => {});
    await Promise.race([p, wait(15000)]);
    return { url: wc().getURL(), title: wc().getTitle() };
  },
  async snapshot() { return wc().executeJavaScript(ctl.SNAPSHOT); },
  async click({ ref }) {
    await wc().executeJavaScript(ctl.SNAPSHOT);
    const box = await wc().executeJavaScript(ctl.locate(ref));
    if (!box) throw new Error(`no element [${ref}]`);
    await wc().executeJavaScript(ctl.highlight(box, `Mnemo · click [${ref}]`));
    await wait(350);
    await mouseClick(box.x, box.y);
    await settle();
    return { url: wc().getURL() };
  },
  async type({ ref, text, submit }) {
    await wc().executeJavaScript(ctl.SNAPSHOT);
    const box = await wc().executeJavaScript(ctl.locate(ref));
    if (!box) throw new Error(`no element [${ref}]`);
    if (box.password) throw new Error('Mnemo does not type into password fields');
    await wc().executeJavaScript(ctl.highlight(box, `Mnemo · type`));
    await mouseClick(box.x, box.y);
    await wc().executeJavaScript(ctl.clearField(ref));
    await wc().insertText(String(text));
    if (submit) { await wait(150); await pressKey('Enter'); await settle(); }
    return { url: wc().getURL() };
  },
  async scroll({ direction = 'down' }) {
    const dy = direction === 'up' ? -0.8 : 0.8;
    await wc().executeJavaScript(`window.scrollBy({top: innerHeight * ${dy}, behavior: 'smooth'})`);
    await wait(400);
    return {};
  },
  async key({ key }) { await pressKey(key); await settle(); return {}; },
  async read() { return wc().executeJavaScript(ctl.READ); },
  async screenshot() {
    const img = await wc().capturePage();
    return { png: img.resize({ width: 1024 }).toDataURL() };
  },
  async back() { if (wc().navigationHistory.canGoBack()) wc().navigationHistory.goBack(); await settle(); return {}; },
  async forward() { if (wc().navigationHistory.canGoForward()) wc().navigationHistory.goForward(); await settle(); return {}; },
  async reload() { wc().reload(); await settle(); return {}; },
};

function connectBridge() {
  bridge = new WebSocket(`ws://127.0.0.1:${PORT}/ws/browser?token=${TOKEN}`);
  bridge.on('message', async (raw) => {
    const { id, method, params } = JSON.parse(raw);
    try {
      if (!handlers[method]) throw new Error(`unknown action ${method}`);
      win.webContents.send('agent-action', { method, params });
      const result = await handlers[method](params || {});
      bridge.send(JSON.stringify({ id, result }));
    } catch (e) {
      bridge.send(JSON.stringify({ id, error: String(e.message || e) }));
    }
  });
  bridge.on('close', () => setTimeout(() => py && py.exitCode === null && connectBridge(), 1000));
  bridge.on('error', () => {});
}

// ---------------------------------------------------------------- window
function sendNav() {
  if (!win || win.isDestroyed()) return;
  win.webContents.send('nav', {
    url: wc().getURL(), title: wc().getTitle(), loading: wc().isLoading(),
    canBack: wc().navigationHistory.canGoBack(), canForward: wc().navigationHistory.canGoForward(),
  });
}

const boundsFile = () => path.join(app.getPath('userData'), 'window.json');
function savedBounds() {
  try { return JSON.parse(fs.readFileSync(boundsFile(), 'utf8')); } catch { return {}; }
}

async function createWindow() {
  win = new BrowserWindow({
    width: 1480, height: 920, ...savedBounds(), minWidth: 1000, minHeight: 640, title: 'Mnemo', backgroundColor: '#0e0f13', icon: ICON,
    titleBarStyle: process.platform === 'darwin' ? 'hiddenInset' : 'default',
    webPreferences: { preload: path.join(__dirname, 'preload.js'), contextIsolation: true, nodeIntegration: false },
  });
  view = new WebContentsView({ webPreferences: { sandbox: true, contextIsolation: true, nodeIntegration: false } });
  win.contentView.addChildView(view);
  win.on('close', () => { try { fs.writeFileSync(boundsFile(), JSON.stringify(win.getBounds())); } catch {} });
  view.setBounds({ x: 0, y: 0, width: 0, height: 0 });
  for (const ev of ['did-navigate', 'did-navigate-in-page', 'page-title-updated', 'did-start-loading', 'did-stop-loading']) {
    wc().on(ev, sendNav);
  }
  wc().setWindowOpenHandler(({ url }) => { wc().loadURL(url); return { action: 'deny' }; });
  await win.loadFile(path.join(__dirname, 'renderer', 'index.html'));
}

ipcMain.handle('config', () => ({ port: PORT, token: TOKEN }));
ipcMain.handle('pick', async (_e, kind) => {
  const r = await dialog.showOpenDialog(win, {
    title: kind === 'folder' ? 'Teach Mnemo a folder' : 'Teach Mnemo files',
    properties: kind === 'folder' ? ['openDirectory', 'multiSelections'] : ['openFile', 'multiSelections'],
  });
  return r.canceled ? [] : r.filePaths;
});
let awakeId = null;
ipcMain.on('keep-awake', (_e, on) => {
  if (on && awakeId === null) awakeId = powerSaveBlocker.start('prevent-app-suspension');
  if (!on && awakeId !== null) { powerSaveBlocker.stop(awakeId); awakeId = null; }
});
ipcMain.handle('open-creation', async (_e, name) => {
  const st = await api('GET', '/api/status');
  const p = path.join(st.home, 'creations', path.basename(String(name)));
  return fs.existsSync(p) ? shell.showItemInFolder(p) : false;
});
ipcMain.handle('open-external', (_e, url) => /^https:\/\//.test(url) && shell.openExternal(url));
ipcMain.handle('open-data', async () => {
  const st = await api('GET', '/api/status');
  return shell.openPath(st.home);
});
ipcMain.handle('api', (_e, method, route, body) => api(method, route, body));
ipcMain.on('browser-bounds', (_e, b) => view && view.setBounds({
  x: Math.round(b.x), y: Math.round(b.y), width: Math.round(b.width), height: Math.round(b.height) }));
ipcMain.handle('browser', async (_e, cmd, arg) => {
  if (cmd === 'navigate') return handlers.navigate({ url: arg });
  if (cmd === 'back') return handlers.back();
  if (cmd === 'forward') return handlers.forward();
  if (cmd === 'reload') return handlers.reload();
  if (cmd === 'read') return handlers.read();
  if (cmd === 'external') return shell.openExternal(wc().getURL());
});

app.whenReady().then(async () => {
  if (process.platform === 'darwin' && !app.isPackaged && fs.existsSync(ICON)) app.dock.setIcon(ICON);
  await createWindow();
  try {
    await startBrain();
    connectBridge();
    win.webContents.send('ready', { port: PORT, token: TOKEN });
    wc().loadURL('https://en.wikipedia.org/wiki/Main_Page');
    if (process.env.MNEMO_SCREENSHOT) selfTest(process.env.MNEMO_SCREENSHOT);
  } catch (e) {
    win.webContents.send('brain-exit', String(e));
  }
});

// Developer self-test: drives the browser through the brain, then saves a screenshot and quits.
async function selfTest(file) {
  win.webContents.on('console-message', (e) => { if (e.level === 'error') console.log('[renderer error]', e.message); });
  await wait(6000);
  const steps = ['go to en.wikipedia.org/wiki/Alan_Turing', 'learn this page', 'show page', 'click Enigma', 'scroll down'];
  const sock = new WebSocket(`ws://127.0.0.1:${PORT}/ws/ui?token=${TOKEN}`);
  await new Promise((r) => sock.on('open', r));
  const log = [];
  sock.on('message', (m) => { const d = JSON.parse(m); if (d.type === 'tool') log.push(d.text.slice(0, 200)); });
  for (const text of steps) { sock.send(JSON.stringify({ type: 'chat', text, history: [] })); await wait(6000); }
  await wait(1500);
  const check = await win.webContents.executeJavaScript(`(() => { showView('learn'); const t = document.querySelector('#view-learn');
    t.scrollTop = 400; return 'learn scrollHeight=' + t.scrollHeight + ' clientHeight=' + t.clientHeight + ' scrollTop=' + t.scrollTop; })()`);
  log.push(check);
  await wait(800);
  fs.writeFileSync(file.replace(/\.png$/, '-learn.png'), (await win.webContents.capturePage()).toPNG());
  await win.webContents.executeJavaScript(`showView('chat')`);
  fs.writeFileSync(file.replace(/\.png$/, '.log'), log.join('\n---\n'));
  fs.writeFileSync(file, (await win.webContents.capturePage()).toPNG());
  fs.writeFileSync(file.replace(/\.png$/, '-browser.png'), (await wc().capturePage()).toPNG());
  app.quit();
}

app.on('before-quit', () => {
  if (py && py.exitCode === null) py.kill('SIGINT');
});
app.on('window-all-closed', () => app.quit());

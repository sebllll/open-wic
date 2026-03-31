import { app, BrowserWindow } from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import { spawn, ChildProcess } from 'child_process';

const isDev = !app.isPackaged;

let mainWindow: BrowserWindow | null = null;
let serverProcess: ChildProcess | null = null;

function startBackendServer() {
  const serverExe = path.join(process.resourcesPath, 'backend', 'open-wic-server.exe');
  if (!fs.existsSync(serverExe)) {
    console.log('[Backend] No bundled server found – assuming external dev server on :8000');
    return;
  }

  console.log(`[Backend] Starting: ${serverExe}`);
  serverProcess = spawn(serverExe, [], {
    cwd: path.dirname(serverExe),
    stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, PATH: path.dirname(serverExe) + ';' + (process.env.PATH || '') },
  });

  serverProcess.stdout?.on('data', (d: Buffer) => console.log(`[Backend] ${d.toString().trim()}`));
  serverProcess.stderr?.on('data', (d: Buffer) => console.error(`[Backend] ${d.toString().trim()}`));
  serverProcess.on('error', (err) => console.error(`[Backend] ${err.message}`));
  serverProcess.on('exit', (code) => { console.log(`[Backend] exited (${code})`); serverProcess = null; });
}

function stopBackendServer() {
  if (serverProcess && !serverProcess.killed) {
    serverProcess.kill();
    serverProcess = null;
  }
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1024,
    height: 768,
    minWidth: 800,
    minHeight: 600,
    titleBarStyle: 'hiddenInset', // Mac Style
    backgroundColor: '#0f172a',
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false, // For MVP only. Em prod real usar preload.js
      webSecurity: false, // Allow file:// to load module scripts
    },
  });

  if (isDev) {
    // In dev mode, wait for Vite dev server then load it
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    // In production mode, load the Vite static build
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

// Inicia o app do Electron
app.whenReady().then(() => {
  startBackendServer();
  createWindow();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    stopBackendServer();
    app.quit();
  }
});

app.on('before-quit', () => {
  stopBackendServer();
});

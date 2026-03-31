import { app, BrowserWindow } from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import { spawn, ChildProcess } from 'child_process';

const isDev = !app.isPackaged;

let mainWindow: BrowserWindow | null = null;
let serverProcess: ChildProcess | null = null;

/**
 * Start the Python backend server (open-wic-server.exe).
 * In dev mode: assumes server is already running externally.
 * In production: spawns the bundled exe from extraResources/backend/.
 */
function startBackendServer() {
  // Check if the bundled backend exe exists (works for both packaged and unpacked builds)
  const serverExe = path.join(process.resourcesPath, 'backend', 'open-wic-server.exe');

  if (!fs.existsSync(serverExe)) {
    console.log('[Backend] No bundled server found – expecting server already running on :8000');
    return;
  }

  const libusb = path.join(process.resourcesPath, 'backend', 'libusb-1.0.dll');

  console.log(`[Backend] Starting server: ${serverExe}`);
  console.log(`[Backend] libusb DLL: ${libusb}`);

  serverProcess = spawn(serverExe, [], {
    cwd: path.dirname(serverExe),
    stdio: ['ignore', 'pipe', 'pipe'],
    env: {
      ...process.env,
      // Ensure libusb can be found in the same directory
      PATH: path.dirname(serverExe) + ';' + (process.env.PATH || ''),
    },
  });

  serverProcess.stdout?.on('data', (data: Buffer) => {
    console.log(`[Backend] ${data.toString().trim()}`);
  });

  serverProcess.stderr?.on('data', (data: Buffer) => {
    console.error(`[Backend] ${data.toString().trim()}`);
  });

  serverProcess.on('error', (err) => {
    console.error(`[Backend] Failed to start server: ${err.message}`);
  });

  serverProcess.on('exit', (code) => {
    console.log(`[Backend] Server exited with code ${code}`);
    serverProcess = null;
  });
}

/**
 * Kill the backend server process.
 */
function stopBackendServer() {
  if (serverProcess && !serverProcess.killed) {
    console.log('[Backend] Stopping server...');
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
      webSecurity: false, // Allow file:// protocol to load module scripts
    },
  });

  if (isDev) {
    // In dev mode, wait for Vite dev server then load it
    mainWindow.loadURL('http://localhost:5173');
  } else {
    // In production mode, load the Vite static build
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
  }

  // Always open DevTools for debugging (remove later)
  mainWindow.webContents.openDevTools();

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

const { app, BrowserWindow } = require("electron");
const { spawn } = require("child_process");
const http = require("http");
const path = require("path");

let backendProcess = null;
let mainWindow = null;

function startBackend() {
  const isDev = !app.isPackaged;
  const backendDir = isDev
    ? path.resolve(__dirname, "..", "backend")
    : path.join(process.resourcesPath, "backend");

  const pythonBin = process.platform === "win32"
    ? path.join(backendDir, ".venv", "Scripts", "python.exe")
    : path.join(backendDir, ".venv", "bin", "python");

  backendProcess = spawn(
    pythonBin,
    ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"],
    { cwd: backendDir, stdio: "inherit" }
  );
}

function waitForBackend(retries = 30) {
  return new Promise((resolve, reject) => {
    const attempt = (n) => {
      http
        .get("http://127.0.0.1:8000/api/v1/health", (res) => {
          if (res.statusCode === 200) resolve();
          else retry(n);
        })
        .on("error", () => retry(n));
    };
    const retry = (n) => {
      if (n <= 0) return reject(new Error("Backend failed to start"));
      setTimeout(() => attempt(n - 1), 300);
    };
    attempt(retries);
  });
}

async function createWindow() {
  startBackend();
  try {
    await waitForBackend();
  } catch (err) {
    console.error(err);
  }

  mainWindow = new BrowserWindow({
    width: 1360,
    height: 860,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  const devUrl = process.env.VITE_DEV_SERVER_URL;
  if (devUrl) {
    mainWindow.loadURL(devUrl);
  } else {
    mainWindow.loadFile(path.resolve(__dirname, "..", "frontend", "dist", "index.html"));
  }
}

app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
  if (backendProcess) {
    backendProcess.kill();
    backendProcess = null;
  }
  if (process.platform !== "darwin") app.quit();
});

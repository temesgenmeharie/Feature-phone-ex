const { contextBridge } = require("electron");

contextBridge.exposeInMainWorld("forensicsDesktop", {
  platform: process.platform,
  offlineMode: true,
});


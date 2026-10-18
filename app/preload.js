const { contextBridge, ipcRenderer, webUtils } = require('electron');

contextBridge.exposeInMainWorld('mnemo', {
  config: () => ipcRenderer.invoke('config'),
  api: (method, route, body) => ipcRenderer.invoke('api', method, route, body),
  browser: (cmd, arg) => ipcRenderer.invoke('browser', cmd, arg),
  setBrowserBounds: (b) => ipcRenderer.send('browser-bounds', b),
  pick: (kind) => ipcRenderer.invoke('pick', kind),
  pathForFile: (file) => webUtils.getPathForFile(file),
  keepAwake: (on) => ipcRenderer.send('keep-awake', on),
  openData: () => ipcRenderer.invoke('open-data'),
  openExternal: (url) => ipcRenderer.invoke('open-external', url),
  openCreation: (name) => ipcRenderer.invoke('open-creation', name),
  on: (channel, fn) => {
    if (['ready', 'nav', 'brain-exit', 'agent-action'].includes(channel)) {
      ipcRenderer.on(channel, (_e, data) => fn(data));
    }
  },
});

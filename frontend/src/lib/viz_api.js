// API-Helper für das LADS-Visualize-Modul — alle Routen unter /api/viz.
const BASE = '/api/viz'

async function j(method, url, body) {
  const opts = { method, headers: {} }
  if (body !== undefined) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  }
  const r = await fetch(BASE + url, opts)
  if (!r.ok) {
    const text = await r.text()
    throw new Error(`${r.status}: ${text}`)
  }
  return r.json()
}

export const api = {
  config: () => j('GET', '/config'),
  servers: () => j('GET', '/servers'),
  addServer: (s) => j('POST', '/servers', s),
  deleteServer: (id) => j('DELETE', `/servers/${id}`),
  discover: (id) => j('POST', `/servers/${id}/discover`),
  devices: (id) => j('GET', `/servers/${id}/devices`),
  signals: (id) => j('GET', `/devices/${id}/signals`),
  monitored: (serverId) => j('GET', serverId ? `/sensors?server_id=${serverId}` : '/sensors'),
  allSignals: (serverId) => j('GET', serverId ? `/signals?server_id=${serverId}` : '/signals'),
  storage: () => j('GET', '/system/storage'),
  monitor: (id) => j('POST', `/sensors/${id}/monitor`),
  unmonitor: (id) => j('POST', `/sensors/${id}/unmonitor`),
  history: (signalId, start, end, points = 1500) =>
    j('GET', `/signals/${signalId}/history?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&points=${points}`),
  dashboards: () => j('GET', '/dashboards'),
  createDashboard: (name, description = '') => j('POST', '/dashboards', { name, description }),
  getDashboard: (id) => j('GET', `/dashboards/${id}`),
  renameDashboard: (id, name) => j('PATCH', `/dashboards/${id}`, { name }),
  deleteDashboard: (id) => j('DELETE', `/dashboards/${id}`),
  addWidget: (dashId, w) => j('POST', `/dashboards/${dashId}/widgets`, w),
  updateWidget: (id, w) => j('PUT', `/widgets/${id}`, w),
  deleteWidget: (id) => j('DELETE', `/widgets/${id}`),
  consumption: (signals, start, end, bucket = 'auto', eurKwh) =>
    j('GET', `/stats/consumption?signals=${signals.join(',')}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&bucket=${encodeURIComponent(bucket)}${eurKwh != null && !Number.isNaN(eurKwh) ? `&eur_kwh=${eurKwh}` : ''}`),
  usage: (signals, start, end, startThreshold = 10, stopThreshold = 5) =>
    j('GET', `/usage?signal_ids=${signals.join(',')}&start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&start_threshold=${startThreshold}&stop_threshold=${stopThreshold}`),
  settings: () => j('GET', '/settings'),
  updateSettings: (s) => j('PUT', '/settings', s),
}
const BASE = '/api'

async function request(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { 'Content-Type': 'application/json', ...options.headers },
    ...options,
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: res.statusText }))
    const msg = err.error || err.message || err.detail?.error || JSON.stringify(err)
    throw new Error(typeof msg === 'string' ? msg : `HTTP ${res.status}`)
  }
  if (res.status === 204) return null
  return res.json()
}

export const api = {
  rooms: {
    list: () => request('/rooms'),
    get: (id) => request(`/rooms/detail?roomId=${encodeURIComponent(id)}`),
    create: (data) => request('/rooms', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id) => request(`/rooms/detail?roomId=${encodeURIComponent(id)}`, { method: 'DELETE' }),
    patchMeta: (id, data) => request(`/rooms/detail?roomId=${encodeURIComponent(id)}`, { method: 'PATCH', body: JSON.stringify(data) }),
  },
  servers: {
    list: () => request('/discovery/servers'),
    create: (data) => request('/discovery/servers', { method: 'POST', body: JSON.stringify(data) }),
    delete: (id) => request(`/discovery/servers/${encodeURIComponent(id)}`, { method: 'DELETE' }),
    getCredentials: (id) => request(`/discovery/servers/${encodeURIComponent(id)}/credentials`),
    putCredentials: (id, data) => request(`/discovery/servers/${encodeURIComponent(id)}/credentials`, { method: 'PUT', body: JSON.stringify(data) }),
    deleteCredentials: (id) => request(`/discovery/servers/${encodeURIComponent(id)}/credentials`, { method: 'DELETE' }),
  },
}

export function unwrap(resp) {
  if (resp && Array.isArray(resp.data)) return resp.data
  if (resp && Array.isArray(resp)) return resp
  return []
}

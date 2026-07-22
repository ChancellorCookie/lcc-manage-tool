<script>
  import { api, unwrap } from '../api.js'
  import { onMount } from 'svelte'

  let { showToast } = $props()

  let servers = $state([])
  let loading = $state(true)
  let error = $state('')
  let showAdd = $state(false)
  let showDelete = $state(null)
  let showCreds = $state(null)

  onMount(() => loadServers())

  async function loadServers() {
    loading = true
    error = ''
    try {
      const resp = await api.servers.list()
      servers = unwrap(resp)
    } catch (e) {
      error = e.message
    } finally {
      loading = false
    }
  }

  async function doDelete(id) {
    try {
      await api.servers.delete(id)
      servers = servers.filter(s => s.id !== id)
      showDelete = null
      showToast?.('Server deleted', 'success')
    } catch (e) {
      error = e.message
    }
  }

  async function doAdd(e) {
    e.preventDefault()
    const fd = new FormData(e.target)
    try {
      await api.servers.create({
        endpointUrl: fd.get('endpointUrl'),
        name: fd.get('name') || undefined,
      })
      showAdd = false
      showToast?.('Server added', 'success')
      await loadServers()
    } catch (err) {
      error = err.message
    }
  }

  async function saveCredentials(e) {
    e.preventDefault()
    const fd = new FormData(e.target)
    try {
      await api.servers.putCredentials(showCreds.id, {
        authType: fd.get('authType'),
        username: fd.get('username') || undefined,
        password: fd.get('password') || undefined,
      })
      showCreds = null
      showToast?.('Credentials saved', 'success')
      await loadServers()
    } catch (err) {
      error = err.message
    }
  }

  async function loadAndShowCreds(server) {
    try {
      const creds = await api.servers.getCredentials(server.id)
      showCreds = { ...server, creds }
    } catch {
      showCreds = { ...server, creds: null }
    }
  }

  function displayName(s) {
    return s.description || s.name || s.endpointUrl
  }
</script>

<div>
  <div class="flex items-center justify-between mb-6">
    <div>
      <h2 class="text-2xl font-bold">OPC UA Servers</h2>
      <p class="text-slate-500 text-sm mt-1">Discovered and manual servers with credential management</p>
    </div>
    <button class="btn btn-primary" onclick={() => showAdd = true}>
      + Add Server
    </button>
  </div>

  {#if error}
    <div class="card border-red-500/30 mb-4 text-red-400 text-sm">
      {error}
      <button class="ml-4 underline" onclick={() => error = ''}>✕</button>
    </div>
  {/if}

  {#if loading}
    <div class="text-slate-500 text-center py-20 animate-pulse">Loading servers...</div>
  {:else if servers.length === 0}
    <div class="card text-center py-16 text-slate-500">
      <div class="text-4xl mb-3">⬡</div>
      <p>No OPC UA servers found.</p>
      <button class="btn btn-primary mt-4" onclick={() => showAdd = true}>Add Server</button>
    </div>
  {:else}
    <div class="grid gap-4">
      {#each servers as server (server.id)}
        <div class="card flex items-center justify-between">
          <div class="flex-1">
            <div class="flex items-center gap-3 mb-1">
              <span class="font-medium">{displayName(server)}</span>
              {#if server.isManual}
                <span class="badge badge-manual">manual</span>
              {:else}
                <span class="badge badge-online">discovered</span>
              {/if}
              {#if server.hasCredentials}
                <span class="badge badge-online">🔐 auth</span>
              {/if}
              {#if !server.isOnline}
                <span class="badge" style="background:rgba(248,113,113,0.2);color:#f87171">offline</span>
              {/if}
            </div>
            <div class="text-xs text-slate-500 font-mono">{server.endpointUrl}</div>
            <div class="text-xs text-slate-600 mt-0.5">{server.name || ''}{server.applicationUri ? ' · ' + server.applicationUri : ''}</div>
          </div>
          <div class="flex gap-2 ml-4">
            <button class="btn btn-ghost text-xs" onclick={() => loadAndShowCreds(server)}>
              Credentials
            </button>
            {#if server.isManual}
              <button class="btn btn-ghost text-xs text-red-400" onclick={() => showDelete = server}>
                Delete
              </button>
            {/if}
          </div>
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- Add server modal -->
{#if showAdd}
  <div class="modal-overlay" onclick={() => showAdd = false}>
    <div class="card max-w-md w-full" onclick={(e) => e.stopPropagation()}>
      <h3 class="text-lg font-semibold mb-4">Add Manual Server</h3>
      <form onsubmit={doAdd}>
        <div class="space-y-4">
          <div>
            <label>Endpoint URL</label>
            <input name="endpointUrl" required placeholder="opc.tcp://192.168.1.10:4840" />
          </div>
          <div>
            <label>Name (optional)</label>
            <input name="name" placeholder="LabController EG" />
          </div>
        </div>
        <div class="flex gap-3 justify-end mt-6">
          <button type="button" class="btn btn-ghost" onclick={() => showAdd = false}>Cancel</button>
          <button type="submit" class="btn btn-primary">Add Server</button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Delete confirmation -->
{#if showDelete}
  <div class="modal-overlay" onclick={() => showDelete = null}>
    <div class="card max-w-sm w-full" onclick={(e) => e.stopPropagation()}>
      <h3 class="text-lg font-semibold mb-2">Remove Server</h3>
      <p class="text-slate-400 text-sm mb-4">
        Remove <strong>{displayName(showDelete)}</strong>?
      </p>
      <div class="flex gap-3 justify-end">
        <button class="btn btn-ghost" onclick={() => showDelete = null}>Cancel</button>
        <button class="btn btn-danger" onclick={() => doDelete(showDelete.id)}>Remove</button>
      </div>
    </div>
  </div>
{/if}

<!-- Credentials modal -->
{#if showCreds}
  <div class="modal-overlay" onclick={() => showCreds = null}>
    <div class="card max-w-md w-full" onclick={(e) => e.stopPropagation()}>
      <h3 class="text-lg font-semibold mb-4">Credentials: {displayName(showCreds)}</h3>
      <form onsubmit={saveCredentials}>
        <div class="space-y-4">
          <div>
            <label>Auth Type</label>
            <select name="authType">
              <option value="anonymous" selected={showCreds.creds?.authType === 'anonymous'}>Anonymous</option>
              <option value="username" selected={showCreds.creds?.authType === 'username'}>Username / Password</option>
              <option value="certificate" selected={showCreds.creds?.authType === 'certificate'}>Certificate</option>
            </select>
          </div>
          <div>
            <label>Username</label>
            <input name="username" value={showCreds.creds?.username || ''} placeholder="operator" />
          </div>
          <div>
            <label>Password</label>
            <input name="password" type="password" placeholder="••••••••" />
          </div>
        </div>
        <div class="flex gap-3 justify-end mt-6">
          <button type="button" class="btn btn-ghost" onclick={() => showCreds = null}>Cancel</button>
          <button type="submit" class="btn btn-primary">Save Credentials</button>
        </div>
      </form>
    </div>
  </div>
{/if}

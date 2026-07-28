<script>
  import { api, unwrap } from '../api.js'
  import { onMount, onDestroy } from 'svelte'

  let { showToast } = $props()

  let servers = $state([])
  let loading = $state(true)
  let error = $state('')
  let showAdd = $state(false)
  let showDelete = $state(null)
  let showCreds = $state(null)

  // ── MQTT Filter per server ──────────────────────────────────────
  let filterServer = $state(null)
  let filterConnecting = $state(false)
  let filterConnected = $state(false)
  let filterBlacklist = $state('')
  let filterWhitelist = $state('')
  let filterPollTimer = null

  onMount(() => loadServers())
  onDestroy(() => { if (filterPollTimer) clearInterval(filterPollTimer) })

  async function loadServers() {
    loading = true; error = ''
    try { servers = unwrap(await api.servers.list()) }
    catch (e) { error = e.message }
    finally { loading = false }
  }

  async function doDelete(id) {
    try { await api.servers.delete(id); servers = servers.filter(s => s.id !== id); showDelete = null; showToast?.('Server deleted', 'success') }
    catch (e) { error = e.message }
  }

  async function doAdd(e) {
    e.preventDefault()
    const fd = new FormData(e.target)
    try { await api.servers.create({ endpointUrl: fd.get('endpointUrl'), name: fd.get('name') || undefined }); showAdd = false; showToast?.('Server added', 'success'); await loadServers() }
    catch (err) { error = err.message }
  }

  async function saveCredentials(e) {
    e.preventDefault()
    const fd = new FormData(e.target)
    try { await api.servers.putCredentials(showCreds.id, { authType: fd.get('authType'), username: fd.get('username') || undefined, password: fd.get('password') || undefined }); showCreds = null; showToast?.('Credentials saved', 'success'); await loadServers() }
    catch (err) { error = err.message }
  }

  async function loadAndShowCreds(server) {
    try { showCreds = { ...server, creds: await api.servers.getCredentials(server.id) } }
    catch { showCreds = { ...server, creds: null } }
  }

  function displayName(s) { return s.description || s.name || s.endpointUrl }

  // ── MQTT ────────────────────────────────────────────────────────

  function extractIp(url) {
    // opc.tcp://10.93.0.178:4840 → 10.93.0.178
    const m = url?.match(/\/\/([^:]+)/)
    return m ? m[1] : null
  }

  async function connectFilters(server) {
    const ip = extractIp(server.endpointUrl)
    if (!ip) { showToast?.('No IP found', 'error'); return }
    filterConnecting = true; filterServer = server
    try {
      const r = await fetch('/api/mqtt/connect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: ip, port: 8883 })
      })
      const data = await r.json()
      if (data.connected) {
        filterConnected = true; startFilterPoll()
      } else {
        showToast?.(data.error || 'MQTT connect failed', 'error'); closeFilters()
      }
    } catch(e) { showToast?.(e.message, 'error'); closeFilters() }
    filterConnecting = false
  }

  function closeFilters() {
    if (filterPollTimer) { clearInterval(filterPollTimer); filterPollTimer = null }
    filterConnected = false; filterServer = null
    filterBlacklist = ''; filterWhitelist = ''
  }

  async function disconnectFilters() {
    await fetch('/api/mqtt/disconnect', { method: 'POST' }); closeFilters()
  }

  function startFilterPoll() {
    if (filterPollTimer) clearInterval(filterPollTimer)
    filterPollTimer = setInterval(refreshFilters, 1000); refreshFilters()
  }

  async function refreshFilters() {
    try {
      const r = await fetch('/api/mqtt/messages?limit=50')
      const md = await r.json()
      for (const msg of md.messages || []) {
        if (msg.topic.includes('/filters/blacklist')) filterBlacklist = msg.payload
        if (msg.topic.includes('/filters/whitelist')) filterWhitelist = msg.payload
      }
    } catch(e) {}
  }

  async function saveFilter(topic, value) {
    try {
      await fetch('/api/mqtt/publish', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic, payload: value })
      })
      showToast?.('Filter saved', 'success')
    } catch(e) { showToast?.(e.message, 'error') }
  }

  function fmtTime(ts) {
    const d = new Date(ts * 1000)
    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
  }

  // ── Mac address helpers ───────────────────────────────────────
  function parseMacs(str) {
    return (str || '').split(',').map(s => s.trim().replace(/"/g, '')).filter(Boolean)
  }
  function macsToStr(macs) {
    return macs.map(m => `"${m}"`).join(',')
  }
</script>

<div>
  <div class="flex items-center justify-between mb-6">
    <div>
      <h2 class="text-2xl font-bold">OPC UA Servers</h2>
      <p class="text-slate-500 text-sm mt-1">Discovered and manual servers with credential management</p>
    </div>
    <button class="btn btn-primary" onclick={() => showAdd = true}>+ Add Server</button>
  </div>

  {#if error}
    <div class="card border-red-500/30 mb-4 text-red-400 text-sm">{error}<button class="ml-4 underline" onclick={() => error = ''}>✕</button></div>
  {/if}

  {#if loading}
    <div class="text-slate-500 text-center py-20 animate-pulse">Loading servers...</div>
  {:else if servers.length === 0}
    <div class="card text-center py-16 text-slate-500"><div class="text-4xl mb-3">⬡</div><p>No OPC UA servers found.</p><button class="btn btn-primary mt-4" onclick={() => showAdd = true}>Add Server</button></div>
  {:else}
    <div class="grid gap-4">
      {#each servers as server (server.id)}
        <div class="card">
          <div class="flex items-center justify-between">
            <div class="flex-1">
              <div class="flex items-center gap-3 mb-1">
                <span class="font-medium">{displayName(server)}</span>
                {#if server.isManual}<span class="badge badge-manual">manual</span>{:else}<span class="badge badge-online">discovered</span>{/if}
                {#if server.hasCredentials}<span class="badge badge-online">🔐 auth</span>{/if}
                {#if !server.isOnline}<span class="badge" style="background:rgba(248,113,113,0.2);color:#f87171">offline</span>{/if}
              </div>
              <div class="text-xs text-slate-500 font-mono">{server.endpointUrl}</div>
            </div>
            <div class="flex gap-2 ml-4">
              <button class="btn btn-ghost text-xs" onclick={() => loadAndShowCreds(server)}>Credentials</button>
              <!-- Filter Button -->
              {#if filterServer?.id === server.id && filterConnected}
                <button class="btn btn-ghost text-xs text-green-400" onclick={disconnectFilters}>Filters ✓</button>
              {:else}
                <button class="btn btn-ghost text-xs" onclick={() => connectFilters(server)} disabled={filterConnecting}>
                  {filterConnecting && filterServer?.id === server.id ? '⋯' : 'Filters'}
                </button>
              {/if}
              {#if server.isManual}
                <button class="btn btn-ghost text-xs text-red-400" onclick={() => showDelete = server}>Delete</button>
              {/if}
            </div>
          </div>

          <!-- Inline Filter Panel -->
          {#if filterServer?.id === server.id && filterConnected}
            <div class="mt-4 pt-4 border-t border-slate-800 grid grid-cols-2 gap-4">
              <!-- Blacklist -->
              <div>
                <div class="flex items-center justify-between mb-2">
                  <span class="text-xs text-slate-500 uppercase">Blacklist</span>
                  <button class="btn btn-primary !text-xs !py-0.5 !px-2" onclick={() => saveFilter('com/essentim/gateway/filters/blacklist', filterBlacklist)}>Save</button>
                </div>
                <textarea
                  class="font-mono text-xs h-32 w-full"
                  bind:value={filterBlacklist}
                  placeholder="&quot;AA:BB:CC:DD:EE:FF&quot;,&quot;11:22:33:44:55:66&quot;"
                ></textarea>
                <div class="text-[0.6rem] text-slate-600 mt-1">{parseMacs(filterBlacklist).length} MACs</div>
              </div>
              <!-- Whitelist -->
              <div>
                <div class="flex items-center justify-between mb-2">
                  <span class="text-xs text-slate-500 uppercase">Whitelist</span>
                  <button class="btn btn-primary !text-xs !py-0.5 !px-2" onclick={() => saveFilter('com/essentim/gateway/filters/whitelist', filterWhitelist)}>Save</button>
                </div>
                <textarea
                  class="font-mono text-xs h-32 w-full"
                  bind:value={filterWhitelist}
                  placeholder="&quot;AA:BB:CC:DD:EE:FF&quot;"
                ></textarea>
                <div class="text-[0.6rem] text-slate-600 mt-1">{parseMacs(filterWhitelist).length} MACs</div>
              </div>
            </div>
          {/if}
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
          <div><label>Endpoint URL</label><input name="endpointUrl" required placeholder="opc.tcp://192.168.1.10:4840" /></div>
          <div><label>Name (optional)</label><input name="name" placeholder="LabController EG" /></div>
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
      <p class="text-slate-400 text-sm mb-4">Remove <strong>{displayName(showDelete)}</strong>?</p>
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
          <div><label>Auth Type</label><select name="authType">
            <option value="anonymous" selected={showCreds.creds?.authType === 'anonymous'}>Anonymous</option>
            <option value="username" selected={showCreds.creds?.authType === 'username'}>Username / Password</option>
            <option value="certificate" selected={showCreds.creds?.authType === 'certificate'}>Certificate</option>
          </select></div>
          <div><label>Username</label><input name="username" value={showCreds.creds?.username || ''} placeholder="operator" /></div>
          <div><label>Password</label><input name="password" type="password" placeholder="••••••••" /></div>
        </div>
        <div class="flex gap-3 justify-end mt-6">
          <button type="button" class="btn btn-ghost" onclick={() => showCreds = null}>Cancel</button>
          <button type="submit" class="btn btn-primary">Save Credentials</button>
        </div>
      </form>
    </div>
  </div>
{/if}

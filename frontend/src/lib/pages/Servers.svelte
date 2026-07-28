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

  // ── MQTT per server ─────────────────────────────────────────────
  let mqttServer = $state(null)        // which server is in MQTT mode
  let mqttConnecting = $state(false)
  let mqttConnected = $state(false)
  let mqttTopics = $state([])
  let mqttMessages = $state([])
  let mqttSelectedTopic = $state('')
  let mqttExpanded = $state(new Set())
  let mqttPollTimer = null
  let mqttPublishTopic = $state('')
  let mqttPublishPayload = $state('')
  let mqttPublishStatus = $state('')

  onMount(() => loadServers())
  onDestroy(() => { if (mqttPollTimer) clearInterval(mqttPollTimer) })

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

  async function connectMqtt(server) {
    const ip = extractIp(server.endpointUrl)
    if (!ip) { showToast?.('No IP found in endpoint URL', 'error'); return }

    mqttConnecting = true; mqttServer = server
    try {
      const r = await fetch('/api/mqtt/connect', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host: ip, port: 8883 })
      })
      const data = await r.json()
      if (data.connected) {
        mqttConnected = true
        startMqttPoll()
      } else {
        showToast?.(data.error || 'MQTT connect failed', 'error')
        closeMqtt()
      }
    } catch(e) { showToast?.(e.message, 'error'); closeMqtt() }
    mqttConnecting = false
  }

  function closeMqtt() {
    if (mqttPollTimer) { clearInterval(mqttPollTimer); mqttPollTimer = null }
    mqttConnected = false; mqttServer = null; mqttTopics = []; mqttMessages = []
    mqttSelectedTopic = ''; mqttExpanded = new Set()
  }

  async function disconnectMqtt() {
    await fetch('/api/mqtt/disconnect', { method: 'POST' })
    closeMqtt()
  }

  function startMqttPoll() {
    if (mqttPollTimer) clearInterval(mqttPollTimer)
    mqttPollTimer = setInterval(refreshMqtt, 1000)
    refreshMqtt()
  }

  async function refreshMqtt() {
    try {
      const [tr, mr] = await Promise.all([
        fetch('/api/mqtt/topics'),
        fetch('/api/mqtt/messages?limit=200')
      ])
      const td = await tr.json(); mqttTopics = td.topics || []
      const md = await mr.json(); mqttMessages = md.messages || []
    } catch(e) {}
  }

  function toggleMqttTopic(path) {
    if (mqttExpanded.has(path)) mqttExpanded.delete(path)
    else mqttExpanded.add(path)
    mqttExpanded = mqttExpanded
  }

  function selectMqttTopic(path) { mqttSelectedTopic = path }

  function buildTree(list) {
    const root = {}
    for (const t of list) {
      const parts = t.path.split('/')
      let node = root
      for (let i = 0; i < parts.length; i++) {
        const key = parts.slice(0, i + 1).join('/')
        if (!node[key]) node[key] = { children: {}, info: null, path: key }
        node = node[key].children
      }
      let cur = root
      for (let i = 0; i < parts.length; i++) {
        const key = parts.slice(0, i + 1).join('/')
        if (i === parts.length - 1) cur[key].info = t
        cur = cur[key].children
      }
    }
    return root
  }

  function getTreeNodes(root, depth = 0) {
    const result = []
    for (const key of Object.keys(root).sort()) {
      const n = root[key]
      result.push({ path: n.path, info: n.info, depth, hasChildren: Object.keys(n.children).length > 0, key })
      if (mqttExpanded.has(n.path)) result.push(...getTreeNodes(n.children, depth + 1))
    }
    return result
  }

  async function doMqttPublish() {
    if (!mqttPublishTopic) return
    mqttPublishStatus = ''
    try {
      const r = await fetch('/api/mqtt/publish', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: mqttPublishTopic, payload: mqttPublishPayload })
      })
      const data = await r.json()
      mqttPublishStatus = data.published ? '✅ Published' : '❌ ' + (data.error || 'Failed')
    } catch(e) { mqttPublishStatus = '❌ ' + e.message }
  }

  let filteredMqttMessages = $derived(
    mqttSelectedTopic ? mqttMessages.filter(m => m.topic === mqttSelectedTopic) : mqttMessages
  )

  function fmtTime(ts) {
    const d = new Date(ts * 1000)
    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
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
              <!-- MQTT Button -->
              {#if mqttServer?.id === server.id && mqttConnected}
                <button class="btn btn-ghost text-xs text-green-400" onclick={disconnectMqtt}>MQTT ✓</button>
              {:else}
                <button class="btn btn-ghost text-xs" onclick={() => connectMqtt(server)} disabled={mqttConnecting}>
                  {mqttConnecting && mqttServer?.id === server.id ? '⋯' : 'MQTT'}
                </button>
              {/if}
              {#if server.isManual}
                <button class="btn btn-ghost text-xs text-red-400" onclick={() => showDelete = server}>Delete</button>
              {/if}
            </div>
          </div>

          <!-- Inline MQTT Explorer -->
          {#if mqttServer?.id === server.id && mqttConnected}
            <div class="mt-4 pt-4 border-t border-slate-800 flex gap-4" style="height:340px">
              <!-- Topic Tree -->
              <div class="card flex-1 overflow-y-auto !p-3" style="max-width:300px">
                <div class="text-xs text-slate-500 uppercase mb-2">Topics ({mqttTopics.length})</div>
                {#each getTreeNodes(buildTree(mqttTopics)) as node}
                  <button
                    class="w-full text-left text-xs py-0.5 px-1 rounded hover:bg-slate-700/50 flex items-center gap-1 {mqttSelectedTopic === node.path ? 'bg-blue-500/10 text-blue-400' : 'text-slate-300'}"
                    style="padding-left:{node.depth * 12 + 4}px"
                    onclick={() => {
                      if (node.hasChildren) toggleMqttTopic(node.path)
                      selectMqttTopic(node.path)
                    }}
                  >
                    {#if node.hasChildren}
                      <span class="text-[0.6rem] w-3">{mqttExpanded.has(node.path) ? '▼' : '▶'}</span>
                    {:else}
                      <span class="w-3"></span>
                    {/if}
                    <span class="truncate">{node.path.split('/').pop()}</span>
                    {#if node.info}<span class="text-[0.6rem] text-slate-500 ml-auto">{node.info.count}</span>{/if}
                  </button>
                {/each}
              </div>

              <!-- Messages + Publish -->
              <div class="flex flex-col flex-1 gap-2 overflow-hidden">
                <div class="card flex-1 flex flex-col overflow-hidden !p-3">
                  <div class="text-xs text-slate-500 uppercase mb-1">
                    Messages {mqttSelectedTopic ? '· ' + mqttSelectedTopic : ''} ({filteredMqttMessages.length})
                  </div>
                  <div class="flex-1 overflow-y-auto font-mono text-[0.65rem] space-y-0.5">
                    {#each filteredMqttMessages as msg}
                      <div class="flex gap-2 py-0.5 border-b border-slate-800/20">
                        <span class="text-slate-600 flex-shrink-0">{fmtTime(msg.time)}</span>
                        <span class="text-blue-400 flex-shrink-0 truncate max-w-[35%] cursor-pointer" onclick={() => selectMqttTopic(msg.topic)}>{msg.topic}</span>
                        <span class="text-slate-300 break-all">{msg.payload}</span>
                      </div>
                    {/each}
                  </div>
                </div>

                <div class="card !p-3">
                  <div class="flex gap-2">
                    <input type="text" bind:value={mqttPublishTopic} placeholder="topic" class="flex-1 !text-xs !py-1" />
                    <input type="text" bind:value={mqttPublishPayload} placeholder="payload" class="flex-[2] !text-xs !py-1" />
                    <button class="btn btn-primary !text-xs !py-1" onclick={doMqttPublish}>Send</button>
                  </div>
                  {#if mqttPublishStatus}
                    <div class="mt-1 text-xs {mqttPublishStatus.startsWith('✅') ? 'text-green-400' : 'text-red-400'}">{mqttPublishStatus}</div>
                  {/if}
                </div>
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

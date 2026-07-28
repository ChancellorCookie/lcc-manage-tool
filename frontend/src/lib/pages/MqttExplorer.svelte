<script>
  import { onMount, onDestroy } from 'svelte'
  import Icon from '../Icon.svelte'

  // ── Connection ──────────────────────────────────────────────────
  let host = $state('10.93.0.178')
  let port = $state(8883)
  let connecting = $state(false)
  let connected = $state(false)
  let connError = $state('')

  // ── State ───────────────────────────────────────────────────────
  let state = $state({ connected: false, topic_count: 0, message_count: 0, uptime: 0 })
  let topics = $state([])
  let messages = $state([])
  let selectedTopic = $state('')
  let filterTopic = $state('')
  let publishTopic = $state('')
  let publishPayload = $state('')
  let publishStatus = $state('')
  let expandedTopics = $state(new Set())

  let pollTimer = null
  let autoScroll = $state(true)

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer)
  })

  async function doConnect() {
    connecting = true
    connError = ''
    try {
      const r = await fetch('/api/mqtt/connect', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ host, port: Number(port) })
      })
      const data = await r.json()
      if (data.connected) {
        connected = true
        startPolling()
      } else {
        connError = data.error || 'Connection failed'
      }
    } catch(e) { connError = e.message }
    connecting = false
  }

  async function doDisconnect() {
    await fetch('/api/mqtt/disconnect', { method: 'POST' })
    connected = false
    state = { connected: false, topic_count: 0, message_count: 0, uptime: 0 }
    topics = []
    messages = []
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null }
  }

  function startPolling() {
    if (pollTimer) clearInterval(pollTimer)
    pollTimer = setInterval(refresh, 1000)
    refresh()
  }

  async function refresh() {
    try {
      const [sr, tr, mr] = await Promise.all([
        fetch('/api/mqtt/state'),
        fetch('/api/mqtt/topics'),
        fetch('/api/mqtt/messages?limit=200')
      ])
      state = await sr.json()
      const td = await tr.json()
      topics = td.topics || []
      const md = await mr.json()
      messages = md.messages || []
    } catch(e) {}
  }

  function toggleTopic(path) {
    if (expandedTopics.has(path)) {
      expandedTopics.delete(path)
    } else {
      expandedTopics.add(path)
    }
    expandedTopics = expandedTopics  // trigger reactivity
  }

  function selectTopic(path) {
    selectedTopic = path
  }

  async function doPublish() {
    if (!publishTopic) return
    publishStatus = ''
    try {
      const r = await fetch('/api/mqtt/publish', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ topic: publishTopic, payload: publishPayload })
      })
      const data = await r.json()
      publishStatus = data.published ? '✅ Published' : '❌ ' + (data.error || 'Failed')
    } catch(e) { publishStatus = '❌ ' + e.message }
  }

  // ── Topic tree helpers ──────────────────────────────────────────
  function buildTree(topicList) {
    const root = {}
    for (const t of topicList) {
      const parts = t.path.split('/')
      let node = root
      for (let i = 0; i < parts.length; i++) {
        const key = parts.slice(0, i + 1).join('/')
        if (!node[key]) node[key] = { children: {}, info: null, path: key }
        node = node[key].children
      }
      // Attach info to leaf
      const leafKey = t.path
      findAndSet(root, leafKey, t)
    }
    return root
  }

  function findAndSet(node, path, info) {
    for (const key of Object.keys(node)) {
      if (key === path) {
        node[key].info = info
        return true
      }
      if (findAndSet(node[key].children, path, info)) return true
    }
    return false
  }

  function getTreeNodes(root, depth = 0) {
    const result = []
    for (const key of Object.keys(root).sort()) {
      const n = root[key]
      result.push({ path: n.path, info: n.info, depth, hasChildren: Object.keys(n.children).length > 0, key })
      if (expandedTopics.has(n.path)) {
        result.push(...getTreeNodes(n.children, depth + 1))
      }
    }
    return result
  }

  let filteredMessages = $derived(
    selectedTopic ? messages.filter(m => m.topic === selectedTopic) : messages
  )

  function formatTime(ts) {
    const d = new Date(ts * 1000)
    return `${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
  }

  function formatUptime(s) {
    if (s < 60) return `${s}s`
    if (s < 3600) return `${Math.floor(s/60)}m`
    return `${Math.floor(s/3600)}h ${Math.floor(s%3600/60)}m`
  }
</script>

<div>
  <h2 class="text-xl font-bold mb-1 flex items-center gap-2">🔌 MQTT Explorer</h2>
  <p class="text-sm text-slate-500 mb-6">Mit MQTT-Brokern verbinden, Topics browsen und Nachrichten anzeigen</p>

  {#if !connected}
    <!-- Connect Form -->
    <div class="card max-w-md">
      <div class="flex gap-3 items-end">
        <div class="flex-1">
          <label class="text-xs text-slate-500 mb-1">Broker Host</label>
          <input type="text" bind:value={host} placeholder="10.93.0.178" />
        </div>
        <div style="width:100px">
          <label class="text-xs text-slate-500 mb-1">Port</label>
          <input type="number" bind:value={port} placeholder="8883" />
        </div>
        <button class="btn btn-primary" onclick={doConnect} disabled={connecting}>
          {connecting ? 'Verbinde…' : 'Verbinden'}
        </button>
      </div>
      {#if connError}
        <div class="mt-3 text-red-400 text-xs">{connError}</div>
      {/if}
    </div>
  {:else}
    <!-- Connected state -->
    <div class="flex gap-2 items-center mb-4">
      <span class="w-2.5 h-2.5 rounded-full bg-green-400"></span>
      <span class="text-sm text-slate-300">{host}:{port}</span>
      <span class="text-xs text-slate-500">{formatUptime(state.uptime)} · {state.topic_count} Topics · {state.message_count} Msg</span>
      <button class="btn btn-ghost text-xs ml-auto" onclick={doDisconnect}>Trennen</button>
    </div>

    <div class="flex gap-4" style="height:calc(100vh - 280px)">
      <!-- LEFT: Topic Tree -->
      <div class="card flex-1 overflow-y-auto" style="max-width:350px">
        <div class="text-xs text-slate-500 uppercase mb-2">Topics</div>
        {#each getTreeNodes(buildTree(topics)) as node}
          <button
            class="w-full text-left text-xs py-0.5 px-1 rounded hover:bg-slate-700/50 flex items-center gap-1 {selectedTopic === node.path ? 'bg-blue-500/10 text-blue-400' : 'text-slate-300'}"
            style="padding-left:{node.depth * 12 + 4}px"
            onclick={() => {
              if (node.hasChildren) toggleTopic(node.path)
              selectTopic(node.path)
            }}
          >
            {#if node.hasChildren}
              <span class="text-[0.6rem] w-3">{expandedTopics.has(node.path) ? '▼' : '▶'}</span>
            {:else}
              <span class="w-3"></span>
            {/if}
            <span class="truncate">{node.path.split('/').pop()}</span>
            {#if node.info}
              <span class="text-[0.6rem] text-slate-500 ml-auto">{node.info.count}</span>
            {/if}
          </button>
        {/each}
      </div>

      <!-- RIGHT: Messages + Publish -->
      <div class="flex flex-col flex-1 gap-4 overflow-hidden">
        <!-- Messages -->
        <div class="card flex-1 flex flex-col overflow-hidden">
          <div class="flex items-center justify-between mb-2">
            <div class="text-xs text-slate-500 uppercase">
              Messages {selectedTopic ? `· ${selectedTopic}` : ''}
              <span class="text-slate-600 ml-1">({filteredMessages.length})</span>
            </div>
            <label class="flex items-center gap-1 text-[0.6rem] text-slate-500">
              <input type="checkbox" bind:checked={autoScroll} class="w-3 h-3" />
              Auto-Scroll
            </label>
          </div>
          <div class="flex-1 overflow-y-auto font-mono text-xs space-y-0.5" id="msg-log">
            {#each filteredMessages as msg}
              <div class="flex gap-2 py-0.5 border-b border-slate-800/30">
                <span class="text-[0.6rem] text-slate-600 flex-shrink-0">{formatTime(msg.time)}</span>
                <span class="text-blue-400 flex-shrink-0 truncate max-w-[40%]" onclick={() => selectTopic(msg.topic)}>{msg.topic}</span>
                <span class="text-slate-300 break-all">{msg.payload}</span>
              </div>
            {/each}
            {#if filteredMessages.length === 0}
              <div class="text-slate-600 text-center py-8">Keine Nachrichten</div>
            {/if}
          </div>
        </div>

        <!-- Publish -->
        <div class="card">
          <div class="text-xs text-slate-500 uppercase mb-2">Publish</div>
          <div class="flex gap-2 items-start">
            <input type="text" bind:value={publishTopic} placeholder="topic/path" class="flex-1 !text-xs !py-1" />
            <input type="text" bind:value={publishPayload} placeholder="payload" class="flex-[2] !text-xs !py-1" />
            <button class="btn btn-primary !text-xs !py-1" onclick={doPublish}>Senden</button>
          </div>
          {#if publishStatus}
            <div class="mt-1 text-xs {publishStatus.startsWith('✅') ? 'text-green-400' : 'text-red-400'}">{publishStatus}</div>
          {/if}
        </div>
      </div>
    </div>
  {/if}
</div>

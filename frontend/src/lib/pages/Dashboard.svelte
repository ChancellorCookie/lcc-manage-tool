<script>
  import { api, unwrap } from '../api.js'
  import { onMount, onDestroy } from 'svelte'
  import Icon from '../Icon.svelte'

  let { navigate, navTab } = $props()

  // Manager stats
  let roomCount = $state(0)
  let serverCount = $state(0)
  let opcuaConnected = $state(null)  // null=checking, true/false
  let deviceOnline = $state(0)
  let deviceTotal = $state(0)
  let managerLoading = $state(true)

  // Notifier stats
  let notifierStats = $state(null)
  let notifierLoading = $state(true)
  let notifierError = $state('')

  let pollTimer = $state(null)

  async function loadManager() {
    try {
      const [roomsResp, serversResp] = await Promise.all([
        api.rooms.list(),
        api.servers.list(),
      ])
      roomCount = unwrap(roomsResp).length
      serverCount = unwrap(serversResp).length
    } catch { /* ignore */ }
    try {
      const res = await fetch('/api/opcua/status')
      const data = await res.json()
      opcuaConnected = data.connected
    } catch { opcuaConnected = false }
    try {
      const res = await fetch('/api/opcua/devices/cached')
      const data = await res.json()
      const devs = data.devices || []
      deviceTotal = devs.length
      deviceOnline = devs.filter(d => d.online === 1).length
    } catch { /* ignore */ }
    managerLoading = false
  }

  async function loadNotifier() {
    try {
      notifierStats = await api.notifier.status()
      notifierError = ''
    } catch (e) {
      notifierError = e.message
    }
    notifierLoading = false
  }

  onMount(() => {
    loadManager()
    loadNotifier()
    pollTimer = setInterval(loadNotifier, 30_000)
  })

  onDestroy(() => {
    if (pollTimer) clearInterval(pollTimer)
  })

  let statCards = $derived([
    { label: 'Aktive Incidents', value: notifierStats?.active_incidents ?? '…', icon: 'incidents', color: 'rgba(239,68,68,0.15)', click: () => navigate('incidents') },
    { label: 'Digest pending', value: notifierStats?.digest_pending ?? '…', icon: 'notifier', color: 'rgba(251,191,36,0.15)', click: () => navigate('incidents') },
    { label: 'Kanäle aktiv', value: notifierStats?.channels ?? '…', icon: 'gateways', color: 'rgba(96,165,250,0.15)', click: () => navTab?.('incidents', 'settings') },
    { label: 'Gesendet', value: notifierStats?.total_sent ?? '…', icon: 'notifier', color: 'rgba(5,150,105,0.15)', click: () => navTab?.('incidents', 'history') },
    { label: 'Templates', value: '✏', icon: 'sensors', color: 'rgba(34,211,238,0.15)', click: () => navTab?.('incidents', 'templates') },
    { label: 'Einstellungen', value: '⚙', icon: 'dashboard', color: 'rgba(139,92,246,0.15)', click: () => navTab?.('incidents', 'settings') },
  ])
</script>

<div>
  <!-- Hero Card -->
  <div class="relative overflow-hidden rounded-2xl mb-6 p-8" style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 50%, #1a1040 100%)">
    <div class="absolute top-0 right-0 w-64 h-64 opacity-20" style="background: radial-gradient(circle, #3b82f6 0%, transparent 70%)"></div>
    <div class="relative z-10">
      <h1 class="text-3xl font-bold mb-2">
        <span class="text-blue-400">LCC</span> Tools
      </h1>
      <p class="text-slate-400 max-w-lg">
        Zentrale Verwaltung für das Waldner Lab Control Center: Räume, Gateways, OPC-UA-Sensoren und Incident-Monitoring mit Benachrichtigungen.
      </p>
    </div>
  </div>

  <!-- Split Layout -->
  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
    <!-- LEFT: Notifier -->
    <div>
      <div class="flex items-center gap-2 mb-4">
        <Icon name="incidents" size={20} />
        <h2 class="text-lg font-bold">Notifier</h2>
        {#if notifierStats?.last_time && notifierStats.last_time !== '-'}
          <span class="text-xs text-slate-600 ml-auto">
            Letzte: {notifierStats.last_date} {notifierStats.last_time}
          </span>
        {/if}
      </div>

      {#if notifierLoading}
        <div class="grid grid-cols-2 gap-3">
          {#each [1,2,3,4,5,6] as _}
            <div class="card animate-pulse h-24"></div>
          {/each}
        </div>
      {:else if notifierError}
        <div class="card border-red-500/20 text-red-400 text-sm">
          ⚠ Notifier nicht erreichbar
        </div>
      {:else}
        <div class="grid grid-cols-2 gap-3">
          {#each statCards as card}
            <button
              class="card flex items-center gap-3 text-left hover:border-blue-500/40 transition-colors cursor-pointer"
              onclick={card.click}
            >
              <div class="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style="background: {card.color}">
                <Icon name={card.icon} size={20} />
              </div>
              <div class="min-w-0">
                <div class="text-xl font-bold">{card.value}</div>
                <div class="text-xs text-slate-500 truncate">{card.label}</div>
              </div>
            </button>
          {/each}
        </div>
      {/if}
    </div>

    <!-- RIGHT: Manager -->
    <div class="flex flex-col">
      <div class="flex items-center gap-2 mb-4">
        <Icon name="dashboard" size={20} />
        <h2 class="text-lg font-bold">Manager</h2>
      </div>

      {#if managerLoading}
        <div class="flex flex-col gap-4 flex-1">
          <div class="card animate-pulse flex-1"></div>
          <div class="card animate-pulse flex-1"></div>
        </div>
      {:else}
        <div class="flex flex-col gap-4 flex-1">
          <!-- Rooms & Gateways -->
          <button class="card w-full text-left hover:border-blue-500/40 transition-colors cursor-pointer flex-1 flex flex-col" onclick={() => navigate('infrastructure')}>
            <div class="flex items-center gap-4">
              <div class="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style="background: rgba(59,130,246,0.15)">
                <Icon name="rooms" size={20} />
              </div>
              <div>
                <h3 class="text-lg font-bold">Manage Rooms &amp; Gateways</h3>
                <p class="text-xs text-slate-500">REST API &middot; Räume und OPC UA Server verwalten</p>
              </div>
              <span class="ml-auto text-slate-600 text-sm">→</span>
            </div>
            <div class="flex gap-6 text-sm mt-auto pb-1">
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-blue-400"></span>
                <span class="text-slate-400">{roomCount} Rooms</span>
              </div>
              <div class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full bg-purple-400"></span>
                <span class="text-slate-400">{serverCount} Gateways</span>
              </div>
              <div class="flex items-center gap-2 ml-auto">
                <span class="w-2 h-2 rounded-full bg-green-400"></span>
                <span class="text-green-400 text-xs">Verbunden</span>
              </div>
            </div>
          </button>

          <!-- Manage Devices -->
          <button class="card w-full text-left hover:border-blue-500/40 transition-colors cursor-pointer flex-1 flex flex-col" onclick={() => navigate('sensors')}>
            <div class="flex items-center gap-4">
              <div class="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style="background: rgba(34,211,238,0.15)">
                <Icon name="sensors" size={20} />
              </div>
              <div>
                <h3 class="text-lg font-bold">Manage Devices</h3>
                <p class="text-xs text-slate-500">OPC UA Browser &middot; Sensoren und Werte durchsuchen</p>
              </div>
              <span class="ml-auto text-slate-600 text-sm">→</span>
            </div>
            <div class="flex items-center gap-2 text-sm mt-auto pb-1">
              <span class="text-slate-400">{deviceOnline}/{deviceTotal} Online</span>
              {#if opcuaConnected === null}
                <span class="w-2 h-2 rounded-full bg-yellow-400 animate-pulse ml-auto"></span>
                <span class="text-slate-400">Prüfe Verbindung…</span>
              {:else if opcuaConnected}
                <span class="w-2 h-2 rounded-full bg-green-400 ml-auto"></span>
                <span class="text-green-400">Verbunden</span>
              {:else}
                <span class="w-2 h-2 rounded-full bg-red-400 ml-auto"></span>
                <span class="text-red-400">Nicht verbunden</span>
              {/if}
            </div>
          </button>
        </div>
      {/if}
    </div>
  </div>

  <!-- Full-width history -->
  {#if !notifierLoading && notifierStats?.recent?.length}
    <div class="mt-6 card">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-sm font-semibold text-slate-400 flex items-center gap-2">
          <Icon name="gateways" size={16} /> Letzte Benachrichtigungen
        </h3>
        <button class="text-xs text-blue-400 hover:text-blue-300" onclick={() => navTab?.('incidents', 'history')}>Vollständiger Verlauf →</button>
      </div>
      <div class="overflow-x-auto">
        <table class="table-glass">
          <thead><tr><th>Zeit</th><th>Incident</th><th>Severity</th><th>Kanal</th><th>Typ</th></tr></thead>
          <tbody>
            {#each notifierStats.recent.slice(0, 10) as item}
              <tr>
                <td class="text-xs text-slate-400 whitespace-nowrap">{item.time}</td>
                <td class="text-xs text-slate-300 max-w-xs truncate" title={item.incident}>{item.incident}</td>
                <td><span class="badge {item.severity === 'error' ? 'bg-red-500/20 text-red-400' : item.severity === 'alert' ? 'bg-orange-500/20 text-orange-400' : item.severity === 'warning' ? 'bg-yellow-500/20 text-yellow-400' : 'bg-slate-500/20 text-slate-400'} text-xs">{item.severity||'-'}</span></td>
                <td class="text-xs text-slate-400">{item.channel}</td>
                <td class="text-xs text-slate-500">{item.kind}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </div>
  {/if}
</div>

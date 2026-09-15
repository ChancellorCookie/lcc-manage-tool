<script>
  import { api, unwrap } from '../api.js'
  import { api as vizApi } from '../viz_api.js'
  import { onMount, onDestroy } from 'svelte'
  import Icon from '../Icon.svelte'

  let { navigate, navTab, openDashboard } = $props()

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
  let offlineStats = $state(null)
  let dashboardList = $state([])
  let addError = $state('')

  // Kachel-Quickinfo je Dashboard (localStorage, rein frontend-seitig)
  const TILE_KEY = 'lcc-tile-quickinfo'
  let tileMetrics = $state({})
  function loadTileMetrics() {
    try { tileMetrics = JSON.parse(localStorage.getItem(TILE_KEY) || '{}') } catch { tileMetrics = {} }
  }
  function saveTileMetric(id, metric) {
    tileMetrics = { ...tileMetrics, [id]: metric }
    try { localStorage.setItem(TILE_KEY, JSON.stringify(tileMetrics)) } catch { /* ignore */ }
  }
  function tileMetric(id) { return tileMetrics[id] || 'all' }

  // Strompreis (€/kWh, global) — Backend: Settings-API (/api/viz/settings)
  let eurPerKwh = $state(0.32)
  let settingsOpen = $state(false)
  let settingsSaving = $state(false)
  let settingsError = $state('')
  let settingsMsg = $state('')

  async function addDashboard() {
    addError = ''
    try {
      const created = await vizApi.createDashboard('Neues Dashboard')
      openDashboard(created.id)
    } catch (e) {
      addError = e.message
    }
  }

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
      const r = await fetch('/api/opcua/devices/cached')
      const data = await r.json()
      const devs = data.devices || []
      deviceTotal = devs.length
      deviceOnline = devs.filter(d => d.online === 1).length
    } catch { /* ignore */ }
    // Kacheln mit Verbrauchswerten; Fallback: einfache Liste (z.B. alter Backend-Stand)
    try {
      const r = await fetch('/api/viz/dashboards/stats?window_h=24')
      if (!r.ok) throw new Error('stats: ' + r.status)
      const d = await r.json()
      if (!Array.isArray(d)) throw new Error('stats: kein Array')
      dashboardList = d
    } catch {
      try {
        const r = await fetch('/api/viz/dashboards')
        if (!r.ok) throw new Error('list: ' + r.status)
        const d = await r.json()
        dashboardList = Array.isArray(d)
          ? d.map((x) => ({ ...x, kwh: null, cost: null, current_w: null, signal_count: 0, power_signals: 0 }))
          : []
      } catch { /* ignore */ }
    }
    try {
      const s = await vizApi.settings()
      eurPerKwh = s.eur_per_kwh ?? 0.32
    } catch { /* ignore */ }
    managerLoading = false
  }

  async function saveSettings() {
    settingsSaving = true
    settingsError = ''
    settingsMsg = ''
    const v = Number(eurPerKwh)
    if (!Number.isFinite(v) || v < 0) {
      settingsError = 'Bitte einen gültigen Wert ≥ 0 eingeben.'
      settingsSaving = false
      return
    }
    try {
      await vizApi.updateSettings({ eur_per_kwh: v })
      settingsMsg = 'Gespeichert — Kacheln aktualisiert.'
      await loadManager()
      setTimeout(() => {
        settingsOpen = false
        settingsMsg = ''
      }, 700)
    } catch (e) {
      settingsError = e.message
    }
    settingsSaving = false
  }

  async function loadNotifier() {
    try {
      notifierStats = await api.notifier.status()
      notifierError = ''
    } catch (e) {
      notifierError = e.message
    }
    try {
      const r = await fetch('/api/opcua/devices/offline/due')
      offlineStats = await r.json()
    } catch { offlineStats = offlineStats }
    notifierLoading = false
  }

  onMount(() => {
    loadTileMetrics()
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
    { label: 'Offline fällig (fällig/gesamt)', value: offlineStats ? String(offlineStats.due) + '/' + String(offlineStats.offline) : '…', icon: 'sensors', color: 'rgba(239,68,68,0.15)', click: () => navigate('sensors') },
    { label: 'Einstellungen', value: '⚙', icon: 'dashboard', color: 'rgba(139,92,246,0.15)', click: () => navTab?.('incidents', 'settings') },
  ])
</script>

<div>
  <!-- Hero Card -->
  <div class="relative overflow-hidden rounded-2xl mb-6 p-8" style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 50%, #1a1040 100%)">
        <div class="absolute top-0 right-0 w-64 h-64 opacity-20" style="background: radial-gradient(circle, #3b82f6 0%, transparent 70%)"></div>
        <div class="relative z-10">
          <h1 class="text-3xl font-bold mb-2">
            <span class="text-blue-400">IUTA</span> LCC Tools
          </h1>
          <p class="text-slate-400 max-w-lg">
            Zentrale Verwaltung für das Waldner Lab Control Center: Räume, Gateways, OPC-UA-Sensoren und Incident-Monitoring mit Benachrichtigungen.
          </p>
        </div>
      </div>

    <!-- Dashboards: immer oben (Kacheln + Sub-Karten) -->
    <div class="mt-6 card">
      <div class="flex items-center justify-between mb-4">
        <h2 class="text-lg font-bold flex items-center gap-2">
          <Icon name="dashboard" size={20} /> Dashboards
        </h2>
        <div class="flex items-center gap-2">
          {#if addError}
            <span class="text-xs text-red-400">{addError}</span>
          {/if}
          <button class="btn btn-ghost text-xs !px-4 !py-1.5" title="Kacheln & Strompreis" onclick={() => { settingsOpen = true; settingsError = ''; settingsMsg = '' }}>
            ⚙ Kacheln
          </button>
          <button class="btn btn-primary text-xs !px-4 !py-1.5" onclick={addDashboard}>+ Neues Dashboard</button>
        </div>
      </div>

      {#if dashboardList.length === 0}
        <p class="text-slate-500 text-sm">Noch keine Dashboards. Lege eins an, um deine Kanäle zu visualisieren.</p>
      {:else}
        <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
          {#each dashboardList as d}
            {@const metric = tileMetric(d.id)}
            {@const hasKwh = d.kwh != null}
            {@const hasW = d.current_w != null}
            {@const hasCost = d.cost != null}
            <div
              class="card text-left hover:border-blue-500/40 transition-colors cursor-pointer flex flex-col gap-3"
              onclick={() => openDashboard(d.id)}
            >
              <div class="flex items-center gap-3 min-w-0">
                <span class="w-10 h-10 rounded-xl flex items-center justify-center flex-shrink-0" style="background: rgba(96,165,250,0.15)">
                  <Icon name="dashboard" size={20} />
                </span>
                <div class="min-w-0 flex-1">
                  <div class="font-bold truncate">{d.name || 'Dashboard'}</div>
                  <div class="text-xs text-slate-500">
                    {d.widget_count ?? 0} Widget(s){d.signal_count ? ` &middot; ${d.signal_count} Signale` : ''}
                  </div>
                </div>
                <select
                  class="text-xs"
                  style="width:auto; padding:0.25rem 0.4rem; font-size:0.7rem; border-radius:0.375rem; background:rgba(51,65,85,0.4); border-color:rgba(100,116,139,0.5); color:#cbd5e1; flex-shrink:0"
                  value={metric}
                  onclick={(e) => e.stopPropagation()}
                  onchange={(e) => saveTileMetric(d.id, e.currentTarget.value)}
                  title="Quickinfo dieser Kachel wählen"
                >
                  <option value="all">kWh + W + Kosten</option>
                  <option value="kwh">Nur kWh</option>
                  <option value="w">Nur aktuelle W</option>
                  <option value="cost">Nur Kosten €</option>
                </select>
              </div>
              {#if metric === 'all'}
                <div class="flex items-baseline gap-2">
                  <span class="text-2xl font-bold tabular-nums">{hasKwh ? d.kwh.toFixed(1) : '–'}</span>
                  <span class="text-xs text-slate-500">kWh (24h)</span>
                  {#if hasW}
                    <span class="ml-auto text-xs rounded-full bg-cyan-500/10 text-cyan-400 px-2 py-0.5">{Math.round(d.current_w)} W</span>
                  {/if}
                  {#if hasCost}
                    <span class="ml-auto text-xs font-semibold text-emerald-400">{d.cost.toFixed(2)} &euro;</span>
                  {/if}
                </div>
              {:else if metric === 'kwh'}
                <div class="flex items-baseline gap-2">
                  <span class="text-2xl font-bold tabular-nums">{hasKwh ? d.kwh.toFixed(1) : '–'}</span>
                  <span class="text-xs text-slate-500">kWh (24h)</span>
                </div>
              {:else if metric === 'w'}
                <div class="flex items-baseline gap-2">
                  <span class="text-2xl font-bold tabular-nums">{hasW ? Math.round(d.current_w) : '–'}</span>
                  <span class="text-xs text-slate-500">W aktuell</span>
                </div>
              {:else if metric === 'cost'}
                <div class="flex items-baseline gap-2">
                  <span class="text-2xl font-bold tabular-nums">{hasCost ? d.cost.toFixed(2) : '–'}</span>
                  <span class="text-xs text-slate-500">&euro; (24h)</span>
                </div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}
    </div>

  <!-- Split Layout -->
  <div class="mt-6 grid grid-cols-1 lg:grid-cols-2 gap-6 items-stretch">
    <!-- LEFT: Notifier -->
    <div class="flex flex-col">
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
        <div class="card flex-1 flex flex-col">
                  <div class="grid grid-cols-2 sm:grid-cols-3 gap-2">
                    {#each statCards as card}
                      <button
                        class="flex flex-col items-center gap-1.5 rounded-xl p-3 text-center hover:bg-slate-800/30 transition-colors cursor-pointer"
                        onclick={card.click}
                      >
                        <div class="w-9 h-9 rounded-lg flex items-center justify-center flex-shrink-0" style="background: {card.color}">
                          <Icon name={card.icon} size={18} />
                        </div>
                        <div class="text-lg font-bold leading-tight">{card.value}</div>
                        <div class="text-[11px] text-slate-500 leading-tight text-center truncate w-full max-w-full px-1">{card.label}</div>
                      </button>
                    {/each}
                  </div>
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

  <!-- Einstellungen: Strompreis (€/kWh) für Kachel-Kosten -->
  {#if settingsOpen}
    <div class="fixed inset-0 z-50 flex items-center justify-center" style="background: rgba(0,0,0,0.6)" onclick={(e) => e.target === e.currentTarget && (settingsOpen = false)}>
      <div class="card" style="width:min(440px,94vw); max-height:80vh; overflow:auto">
        <h2 class="text-lg font-bold mb-1">Kachel-Einstellungen</h2>
        <p class="text-xs text-slate-500 mb-4">Gilt global: Kosten auf den Startseiten-Kacheln und in den Kosten-Charts (Balken).</p>
        {#if settingsError}
          <p class="text-xs text-red-400 mb-2">{settingsError}</p>
        {/if}
        {#if settingsMsg}
          <p class="text-xs text-emerald-400 mb-2">{settingsMsg}</p>
        {/if}
        <label class="block text-xs text-slate-400 uppercase tracking-wide mb-1">Strompreis (€/kWh)</label>
        <div class="flex gap-2">
          <input type="number" step="0.01" min="0" class="flex-1" bind:value={eurPerKwh} placeholder="z. B. 0,32" />
          <button class="btn btn-primary text-xs !px-4 flex-shrink-0" disabled={settingsSaving} onclick={saveSettings}>
            {settingsSaving ? 'Speichert…' : 'Speichern'}
          </button>
        </div>
        <p class="text-xs text-slate-500 mt-3">Standard bei fehlendem Wert: 0,32 €/kWh.</p>
        <div class="flex justify-end mt-4">
          <button class="btn btn-ghost text-xs" onclick={() => (settingsOpen = false)}>Schließen</button>
        </div>
      </div>
    </div>
  {/if}
</div>

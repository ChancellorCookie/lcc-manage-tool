<script>
  import { onMount } from 'svelte'
  import Icon from '../Icon.svelte'
  import UChart from '../components/UChart.svelte'
  import { api } from '../viz_api.js'

  // ── State ──────────────────────────────────────────────────────
  let serverId = $state(null)
  let devices = $state([])
  let signals = $state([])
  let selectedDevice = $state('')
  let selectedSignal = $state('')
  let loading = $state(false)
  let historyLoading = $state(false)
  let error = $state('')
  let infoMsg = $state('')
  let points = $state([])
  let unit = $state('')
  let label = $state('')
  let stats = $state(null)

  const PRESETS = [
    { label: '1h', hours: 1 },
    { label: '6h', hours: 6 },
    { label: '24h', hours: 24 },
    { label: '3d', hours: 72 },
    { label: '7d', hours: 168 },
    { label: '30d', hours: 720 },
  ]
  let selectedPreset = $state(2) // 24h
  let customStart = $state('')
  let customEnd = $state('')

  onMount(async () => {
    loading = true
    try {
      // OPC-UA-Server sicherstellen (aus /api/viz) und Geräte laden.
      let srvs = await api.servers()
      if (!srvs.length) {
        const cfg = await api.config()
        await api.addServer({ name: 'LADSProxy', url: cfg.default_opcua_url })
        srvs = await api.servers()
      }
      serverId = srvs[0].id
      devices = await api.devices(serverId)
      if (!devices.length) {
        infoMsg = 'Erkenne Geräte über OPC UA…'
        await api.discover(serverId)
        devices = await api.devices(serverId)
        infoMsg = ''
      }
      // Vorauswahl per URL-Hash (?device=…)
      const params = new URLSearchParams((window.location.hash.split('?')[1]) || '')
      const dev = params.get('device')
      if (dev) {
        const m = devices.find((d) => d.serial === dev || d.component_name === dev)
        if (m) await selectDevice(m.id)
      }
    } catch (e) {
      error = e.message
    }
    loading = false
  })

  async function selectDevice(id) {
    selectedDevice = id
    selectedSignal = ''
    signals = []
    points = []
    stats = null
    try {
      signals = await api.signals(id)
    } catch (e) {
      error = e.message
    }
  }

  async function selectSignal(id) {
    selectedSignal = id
    await fetchHistory()
  }

  function getTimeRange() {
    const now = new Date()
    let start, end
    end = customEnd ? new Date(customEnd + 'T23:59:59') : now
    if (customStart) start = new Date(customStart + 'T00:00:00')
    else start = new Date(end.getTime() - PRESETS[selectedPreset].hours * 3600_000)
    return { start: start.toISOString(), end: end.toISOString() }
  }

  async function fetchHistory() {
    if (!selectedSignal) return
    historyLoading = true
    points = []
    stats = null
    error = ''
    try {
      const { start, end } = getTimeRange()
      const r = await api.history(selectedSignal, start, end, 1500)
      points = r.points || []
      unit = r.signal?.engineering_unit || ''
      const dn = r.signal?.display_name || 'SensorValue'
      const dev = r.device?.component_name || ''
      label = dev ? `${dn} — ${dev}` : dn
      stats = r.stats || null
      if (!points.length) error = 'Keine Daten im gewählten Zeitraum'
    } catch (e) {
      error = e.message
    }
    historyLoading = false
  }

  let series = $derived(
    points.length
      ? [{ label, unit, color: '#60a5fa', xs: points.map((p) => p[0]), ys: points.map((p) => p[1]) }]
      : [],
  )
  const fmt = (v) => (v == null || Number.isNaN(v) ? '—' : Number(v).toFixed(2))
</script>

<div>
  <h2 class="text-xl font-bold mb-1 flex items-center gap-2"><Icon name="gateways" size={22} /> Sensor History</h2>
  <p class="text-sm text-slate-500 mb-6">Historische Sensordaten über <span class="text-slate-400">OPC UA</span> (HistoryRead) — Line-Chart und Zeitraum-Auswahl</p>

  {#if error}
    <div class="card border-red-500/30 mb-4 text-red-400 text-sm">{error}</div>
  {/if}
  {#if infoMsg}
    <div class="card border-blue-500/30 mb-4 text-blue-400 text-sm">{infoMsg}</div>
  {/if}

  <!-- Controls -->
  <div class="card mb-6">
    <div class="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
      <div>
        <label class="text-xs text-slate-500 mb-1">Gerät</label>
        <select bind:value={selectedDevice} onchange={(e) => selectDevice(+e.target.value)} disabled={loading}>
          <option value="">-- Gerät wählen --</option>
          {#each devices as d}
            <option value={d.id}>{d.component_name}{d.hierarchical_location ? ` — ${d.hierarchical_location}` : ''}</option>
          {/each}
        </select>
      </div>
      <div>
        <label class="text-xs text-slate-500 mb-1">Sensor</label>
        <select bind:value={selectedSignal} onchange={(e) => selectSignal(+e.target.value)} disabled={!signals.length}>
          <option value="">-- Sensor wählen --</option>
          {#each signals as s}
            <option value={s.id}>{s.browse_name}{s.engineering_unit ? ` (${s.engineering_unit})` : ''}</option>
          {/each}
        </select>
      </div>
    </div>

    <div class="flex flex-wrap items-center gap-2">
      <span class="text-xs text-slate-500 mr-1">Zeitraum:</span>
      {#each PRESETS as p, i}
        <button
          class="px-3 py-1 rounded text-xs border transition-colors {selectedPreset === i && !customStart ? 'border-blue-500 bg-blue-500/10 text-blue-400' : 'border-slate-700 text-slate-400 hover:border-slate-600'}"
          onclick={() => { selectedPreset = i; customStart = ''; customEnd = ''; fetchHistory() }}
        >{p.label}</button>
      {/each}
      <span class="text-xs text-slate-600 mx-1">oder</span>
      <input type="date" class="!w-auto text-xs" bind:value={customStart} onchange={(e) => { customStart = e.target.value; selectedPreset = -1; fetchHistory() }} />
      <span class="text-xs text-slate-500">–</span>
      <input type="date" class="!w-auto text-xs" bind:value={customEnd} onchange={(e) => { customEnd = e.target.value; fetchHistory() }} />
    </div>
  </div>

  <!-- Chart -->
  {#if historyLoading}
    <div class="card text-center py-16 text-slate-500">
      <div class="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-3"></div>
      Lade Sensordaten…
    </div>
  {:else if points.length}
    {#if stats && stats.count}
      <div class="grid grid-cols-2 md:grid-cols-5 gap-3 mb-4">
        <div class="card !p-3"><div class="text-xs text-slate-500">Aktuell</div><div class="text-lg font-semibold">{fmt(stats.last)} <span class="text-xs text-slate-500">{unit}</span></div></div>
        <div class="card !p-3"><div class="text-xs text-slate-500">Min</div><div class="text-lg font-semibold">{fmt(stats.min)}</div></div>
        <div class="card !p-3"><div class="text-xs text-slate-500">Max</div><div class="text-lg font-semibold">{fmt(stats.max)}</div></div>
        <div class="card !p-3"><div class="text-xs text-slate-500">Ø</div><div class="text-lg font-semibold">{fmt(stats.avg)}</div></div>
        {#if stats.energy_wh != null}
          <div class="card !p-3 border-blue-500/40"><div class="text-xs text-slate-500">Energie</div><div class="text-lg font-semibold text-blue-400">{(stats.energy_wh / 1000).toFixed(2)} kWh</div></div>
        {/if}
      </div>
    {/if}
    <div class="card">
      <UChart {series} height={380}></UChart>
    </div>
  {:else}
    <div class="card text-center py-16 text-slate-500">
      <Icon name="gateways" size={40} />
      <p class="mt-3">Gerät und Sensor auswählen, um historische Daten über OPC UA anzuzeigen.</p>
    </div>
  {/if}
</div>
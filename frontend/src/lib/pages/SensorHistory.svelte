<script>
  import { onMount, onDestroy, tick } from 'svelte'
  import Icon from '../Icon.svelte'

  // ── State ──────────────────────────────────────────────────────
  let devices = $state([])
  let units = $state([])
  let functions = $state([])
  let selectedDevice = $state('')
  let selectedUnit = $state('')
  let selectedFunction = $state('')
  let loading = $state(false)
  let historyLoading = $state(false)
  let error = $state('')
  let historyData = $state(null)
  let units_ = $state({})  // engineering units

  // Time presets
  const PRESETS = [
    { label: '1h',  hours: 1 },
    { label: '6h',  hours: 6 },
    { label: '24h', hours: 24 },
    { label: '3d',  hours: 72 },
    { label: '7d',  hours: 168 },
    { label: '30d', hours: 720 },
  ]
  let selectedPreset = $state(5) // 30d
  let customStart = $state('')
  let customEnd = $state('')

  // ── Chart ──────────────────────────────────────────────────────
  let canvasEl = $state(null)
  let chart = $state(null)

  onMount(async () => {
    await loadDevices()
    // Check URL for pre-selected device
    const hash = window.location.hash || ''
    const params = new URLSearchParams(hash.split('?')[1] || '')
    const devFromUrl = params.get('device')
    if (devFromUrl) {
      // Wait for devices to load, then select
      const check = setInterval(() => {
        const match = devices.find(d => d.browseName === devFromUrl || d.displayName === devFromUrl)
        if (match) {
          clearInterval(check)
          selectDevice(match.browseName)
        }
      }, 200)
      // Stop after 5s
      setTimeout(() => clearInterval(check), 5000)
    }
  })

  onDestroy(() => {
    if (chart) chart.destroy()
  })

  async function loadDevices() {
    loading = true
    try {
      const r = await fetch('/api/lads/devices')
      const all = await r.json()
      // Filter to only SensorFunctionType devices and sort by name
      devices = all.sort((a,b) => (a.displayName||a.browseName||'').localeCompare(b.displayName||b.browseName||''))
    } catch(e) { error = e.message }
    loading = false
  }

  async function selectDevice(devId) {
    selectedDevice = devId
    selectedUnit = ''
    selectedFunction = ''
    units = []
    functions = []
    try {
      const r = await fetch(`/api/lads/devices/${encodeURIComponent(devId)}/units`)
      units = await r.json()
      // Auto-select first unit
      if (units.length > 0) {
        const firstUnit = units[0].browseName
        selectedUnit = firstUnit
        await loadFunctions(firstUnit)
      }
    } catch(e) { error = e.message }
  }

  async function loadFunctions(unitId) {
    selectedFunction = ''
    functions = []
    try {
      const r = await fetch(`/api/lads/devices/${encodeURIComponent(selectedDevice)}/units/${encodeURIComponent(unitId)}/functions`)
      const all = await r.json()
      functions = all.filter(f => {
        const t = (f.type || '').toLowerCase()
        return t.includes('sensor') || t.includes('analog')
      })
      // Auto-select Ambient Temperature if available, else first
      const temp = functions.find(f => f.displayName?.toLowerCase().includes('temperature') || f.browseName?.toLowerCase().includes('temperature'))
      if (temp) {
        selectedFunction = temp.browseName
        await fetchHistory()
      } else if (functions.length > 0) {
        selectedFunction = functions[0].browseName
        await fetchHistory()
      }
    } catch(e) { error = e.message }
  }

  async function selectFunction(funcId) {
    selectedFunction = funcId
    await fetchHistory()
  }

  function getTimeRange() {
    const now = new Date()
    let start, end

    if (customEnd) {
      // Date-only input: set end to 23:59:59
      end = new Date(customEnd + 'T23:59:59')
    } else {
      end = now
    }
    if (customStart) {
      // Date-only input: set start to 00:00:00
      start = new Date(customStart + 'T00:00:00')
    } else {
      const preset = PRESETS[selectedPreset]
      start = new Date(end.getTime() - preset.hours * 3600_000)
    }
    return { start: start.toISOString(), end: end.toISOString() }
  }

  async function fetchHistory() {
    if (!selectedDevice || !selectedUnit || !selectedFunction) return
    historyLoading = true
    historyData = null
    error = ''
    try {
      const { start, end } = getTimeRange()
      // No numValuesPerNode limit — get all values in range
      const params = new URLSearchParams({ startTime: start, endTime: end })
      const url = `/api/lads/devices/${encodeURIComponent(selectedDevice)}/units/${encodeURIComponent(selectedUnit)}/functions/${encodeURIComponent(selectedFunction)}/history?${params}`
      const r = await fetch(url)
      if (!r.ok) { error = `Server-Fehler (HTTP ${r.status})`; historyLoading = false; return }
      historyData = await r.json()
      historyLoading = false
      await tick()
      await new Promise(r => setTimeout(r, 50))
      canvasEl = document.querySelector('#sensor-history-canvas')
      renderChart()
    } catch(e) { console.error('ERROR', e); error = e.message; historyLoading = false }
  }

  async function renderChart() {
    if (!canvasEl || !historyData?.data?.values) return

    // Find sensor value
    const sv = historyData.data.values.find(v => v.browsePath?.includes('SensorValue'))
    if (!sv?.historyData?.length) { error = 'Keine Sensordaten gefunden'; return }

    const points = sv.historyData.map(p => ({
      x: new Date(p.serverTimestamp),
      y: Number(p.value)
    }))

    const unit = sv.engineeringUnits || ''
    const label = `${sv.browsePath?.split('/').pop() || 'SensorValue'} ${unit ? `(${unit})` : ''}`

    if (chart) chart.destroy()

    const { default: Chart } = await import('chart.js/auto')
    const ctx = canvasEl.getContext('2d')

    // Manual date formatting (no dependency on tree-shaken date-fns import)
    function fmtDate(ts, pattern) {
      const d = new Date(ts)
      const dd = String(d.getDate()).padStart(2,'0')
      const mm = String(d.getMonth()+1).padStart(2,'0')
      const yyyy = d.getFullYear()
      const HH = String(d.getHours()).padStart(2,'0')
      const Min = String(d.getMinutes()).padStart(2,'0')
      if (pattern === 'day') return `${dd}.${mm}.`
      if (pattern === 'hour') return `${dd}.${mm}. ${HH}:${Min}`
      return `${HH}:${Min}`
    }

    // Determine time unit based on range
    const rangeMs = points.length > 1 ? points[points.length-1].x - points[0].x : 0
    const fmt = rangeMs > 7*86400000 ? 'dd.MM.' : rangeMs > 86400000 ? 'dd.MM. HH:mm' : 'HH:mm'

    // Grid color for dark theme
    Chart.defaults.color = '#64748b'
    Chart.defaults.borderColor = 'rgba(51,65,85,0.5)'

    chart = new Chart(ctx, {
      type: 'line',
      data: {
        datasets: [{
          label,
          data: points,
          borderColor: '#3b82f6',
          backgroundColor: 'rgba(59,130,246,0.1)',
          fill: true,
          pointRadius: 0,
          borderWidth: 1.5,
          tension: 0.1,
        }]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { intersect: false, mode: 'index' },
        plugins: {
          legend: { display: true, labels: { usePointStyle: true, boxWidth: 8 } },
          tooltip: {
            callbacks: {
              label: (ctx) => `${ctx.dataset.label}: ${ctx.parsed.y.toFixed(3)}`,
              title: (ctx) => {
                const d = new Date(ctx[0].parsed.x)
                return `${String(d.getDate()).padStart(2,'0')}.${String(d.getMonth()+1).padStart(2,'0')}.${d.getFullYear()} ${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}:${String(d.getSeconds()).padStart(2,'0')}`
              },
            }
          }
        },
        scales: {
          x: {
            type: 'linear',
            ticks: {
              maxTicksLimit: 12,
              callback: (val) => fmtDate(val, fmt),
            },
            grid: { display: false }
          },
          y: {
            title: { display: !!unit, text: unit },
            ticks: { callback: (v) => Number(v).toFixed(1) },
          }
        }
      }
    })
  }

  let detailIdx = $state(null)
  let detailData = $state(null)
  function showPoint(i) {
    if (!historyData?.data?.values) return
    const sv = historyData.data.values.find(v => v.browsePath?.includes('SensorValue'))
    if (!sv?.historyData?.[i]) return
    detailIdx = i
    detailData = sv.historyData[i]
  }
</script>

<div>
  <h2 class="text-xl font-bold mb-1 flex items-center gap-2"><Icon name="gateways" size={22} /> Sensor History</h2>
  <p class="text-sm text-slate-500 mb-6">Historische Sensordaten aus der LCC-Datenbank — mit Line-Chart und Zeitraum-Auswahl</p>

  {#if error}
    <div class="card border-red-500/30 mb-4 text-red-400 text-sm">{error}</div>
  {/if}

  <!-- Controls -->
  <div class="card mb-6">
    <div class="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
      <!-- Device -->
      <div>
        <label class="text-xs text-slate-500 mb-1">Gerät</label>
        <select bind:value={selectedDevice} onchange={(e) => selectDevice(e.target.value)} disabled={loading}>
          <option value="">-- Gerät wählen --</option>
          {#each devices as d}
            <option value={d.browseName}>{d.displayName || d.browseName}</option>
          {/each}
        </select>
      </div>

      <!-- Function -->
      <div>
        <label class="text-xs text-slate-500 mb-1">Sensor</label>
        <select bind:value={selectedFunction} onchange={(e) => { selectedFunction = e.target.value; fetchHistory() }} disabled={!functions.length}>
          <option value="">-- Sensor wählen --</option>
          {#each functions as f}
            <option value={f.browseName}>{f.displayName || f.browseName}</option>
          {/each}
        </select>
      </div>
    </div>

    <!-- Time presets -->
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-xs text-slate-500 mr-1">Zeitraum:</span>
      {#each PRESETS as p, i}
        <button
          class="px-3 py-1 rounded text-xs border transition-colors {selectedPreset === i && !customStart ? 'border-blue-500 bg-blue-500/10 text-blue-400' : 'border-slate-700 text-slate-400 hover:border-slate-600'}"
          onclick={() => { selectedPreset = i; customStart = ''; customEnd = ''; if(selectedFunction) fetchHistory() }}
        >{p.label}</button>
      {/each}
      <span class="text-xs text-slate-600 mx-1">oder</span>
      <input type="date" class="!w-auto text-xs" bind:value={customStart} onchange={(e) => { customStart = e.target.value; selectedPreset = -1; if(selectedFunction) fetchHistory() }} />
      <span class="text-xs text-slate-500">–</span>
      <input type="date" class="!w-auto text-xs" bind:value={customEnd} onchange={(e) => { customEnd = e.target.value; if(selectedFunction) fetchHistory() }} />
    </div>
  </div>

  <!-- Chart -->
  {#if historyLoading}
    <div class="card text-center py-16 text-slate-500">
      <div class="animate-spin w-8 h-8 border-2 border-blue-500 border-t-transparent rounded-full mx-auto mb-3"></div>
      Lade Sensordaten…
    </div>
  {:else if historyData}
    <div class="card" style="height:420px">
      <canvas id="sensor-history-canvas"></canvas>
    </div>
  {:else}
    <div class="card text-center py-16 text-slate-500">
      <Icon name="gateways" size={40} />
      <p class="mt-3">Gerät, Unit und Sensor auswählen, um historische Daten anzuzeigen.</p>
    </div>
  {/if}
</div>

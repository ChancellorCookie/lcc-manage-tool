<script>
  import { onMount, tick } from 'svelte'
  import { api } from '../viz_api.js'
  import WidgetBody from '../components/WidgetBody.svelte'
  import { GridStack } from 'gridstack'
  import 'gridstack/dist/gridstack.min.css'

  let { openId, onback = () => {} } = $props()

  const PRESETS = [
    { label: '1h', h: 1 },
    { label: '6h', h: 6 },
    { label: '24h', h: 24 },
    { label: '3d', h: 72 },
    { label: '7d', h: 168 },
    { label: '30d', h: 720 },
  ]

  let dash = $state(null)
  let widgets = $state([])
  let mode = $state('view') // 'view' | 'edit'
  let presetIdx = $state(2)
  let data = $state({}) // widgetId -> [history responses]
  let loading = $state(false)
  let error = $state('')
  let sensors = $state([])
  let editingWidgetId = $state(null)
  let editTitle = $state('')
  let editSignals = $state([])
  let editType = $state('')
  let editMode = $state('line')
  let editBarMode = $state('stacked')
  let editBucket = $state('auto')
  let editEurKwh = $state('')
  let eurKwhGlobal = $state(0.32)
  let consults = $state({})
  let gridEl = $state(null)
  let grid = null
  let saveTimer = 0
  let saveMsg = $state('')
  let dataSourceInfo = $state('')
  let sensorQuery = $state('')

  async function reload() {
    try {
      const res = await api.getDashboard(openId)
      dash = res.dashboard
      widgets = res.widgets || []
    } catch (e) {
      error = e.message
    }
    try {
      const s = await api.settings()
      eurKwhGlobal = s.eur_per_kwh ?? 0.32
    } catch (e) {}
    await loadData()
  }

  async function loadData() {
    if (!dash) return
    const end = new Date()
    const start = new Date(end.getTime() - PRESETS[presetIdx].h * 3600_000)
    const sISO = start.toISOString()
    const eISO = end.toISOString()
    loading = true
    const results = {}
    const cons = {}
    const jobs = []
    for (const w of widgets) {
      const ids = w.config?.signals || []
      const isBar = (w.type === 'charttable' || w.type === 'linechart') && w.config?.mode === 'bar'
      if (ids.length && isBar) {
        const eur = w.config?.eurKwh
        jobs.push(
          api.consumption(ids, sISO, eISO, w.config?.bucket || 'auto', eur != null && eur !== '' ? Number(eur) : undefined)
            .then((c) => { cons[w.id] = c })
            .catch((e2) => { error = e2.message }),
        )
        continue
      }
      jobs.push(
        Promise.all(ids.map((id) => api.history(id, sISO, eISO, 1500).catch(() => null)))
          .then((resps) => { results[w.id] = resps.filter(Boolean) }),
      )
    }
    await Promise.all(jobs)
    data = results
    consults = cons
    dataSourceInfo = summarizeSources(results, cons)
    loading = false
  }

  // Woher kamen die angezeigten Verläufe? (lokale DB vs. OPC-UA-Nachladen)
  function summarizeSources(respsById, consumeById) {
    let dbP = 0
    let fillP = 0
    let calls = 0
    const eat = (o) => {
      if (!o || typeof o !== 'object' || o.source === undefined) return
      calls++
      dbP += o.db_points || 0
      fillP += o.filled_points || 0
    }
    for (const arr of Object.values(respsById || {})) for (const r of arr) eat(r)
    for (const c of Object.values(consumeById || {})) eat(c)
    const fmt = (n) => n.toLocaleString('de-DE')
    if (!calls) return ''
    if (fillP === 0) return `Datenquelle: lokale Zeitreihen-DB (${fmt(dbP)} Punkte)`
    if (dbP === 0) return `Datenquelle: OPC UA (${fmt(fillP)} Punkte nachgeladen)`
    return `Datenquelle: lokale DB + ${fmt(fillP)} nachgeladene Punkte (OPC UA, jetzt archiviert)`
  }

  const filteredSensors = $derived(
    sensorQuery.trim()
      ? sensors.filter((s) =>
          `${s.display_name} ${s.component_name || ''} ${s.engineering_unit || ''}`
            .toLowerCase()
            .includes(sensorQuery.trim().toLowerCase()),
        )
      : sensors,
  )

  async function enterEdit() {
    mode = 'edit'
    try {
      sensors = await api.allSignals()
    } catch (e) {
      error = e.message
    }
  }

  // Gridstack nur im Edit-Modus; bei Widget-Änderungen neu adoptieren
  $effect(() => {
    const m = mode
    const n = widgets.length
    if (m === 'edit') {
      tick().then(initGrid)
    } else if (grid) {
      grid.destroy(false)
      grid = null
    }
  })

  function initGrid() {
    if (!gridEl) return
    if (grid) {
      grid.destroy(false)
      grid = null
    }
    grid = GridStack.init(
      { column: 12, cellHeight: 80, margin: 8, float: true, animate: false },
      gridEl,
    )
    grid.on('change', scheduleSave)
    grid.on('dragstop', scheduleSave)
    grid.on('resizestop', scheduleSave)
  }

  async function saveLayouts() {
    if (!grid || !dash || !gridEl) return
    try {
      const els = gridEl.querySelectorAll('.grid-stack-item')
      let changed = 0
      for (const el of els) {
        const id = Number(el.getAttribute('gs-id'))
        const n = el.gridstackNode
        if (!id || !n) continue
        const w = widgets.find((x) => x.id === id)
        if (!w) continue
        const g = { x: n.x, y: n.y, w: n.w, h: n.h }
        if (JSON.stringify(g) !== JSON.stringify(w.grid || {})) {
          await api.updateWidget(w.id, { type: w.type, title: w.title, config: w.config, grid: g })
          w.grid = g
          changed++
        }
      }
      saveMsg = changed ? `Layout gespeichert (${changed} Widgets)` : 'Layout aktuell — nichts zu speichern'
    } catch (e) {
      error = e.message
    }
  }

  function scheduleSave() {
    clearTimeout(saveTimer)
    saveTimer = setTimeout(saveLayouts, 400)
  }

  async function addWidget(type) {
    try {
      await api.addWidget(dash.id, {
        type,
        title: { linechart: 'Neues Linechart', charttable: 'Neue Leistung & Tabelle', stat: 'Neue Statistik', table: 'Neue Tabelle' }[type] || 'Neues Widget',
        config: { signals: [] },
        grid: {},
      })
      await reload()
    } catch (e) {
      error = e.message
    }
  }

  async function removeSignalFromWidget(widgetId, sigId) {
    const w = widgets.find((x) => x.id === widgetId)
    if (!w) return
    const signals = (w.config?.signals || []).filter((id) => id !== sigId)
    try {
      await api.updateWidget(w.id, {
        type: w.type,
        title: w.title,
        config: { ...(w.config || {}), signals },
        grid: w.grid || {},
      })
      await reload()
    } catch (e) {
      error = e.message
    }
  }

  function defaultTitle(w) {
    return w.title || { linechart: 'Linechart', charttable: 'Leistung & Tabelle', stat: 'Statistik', table: 'Tabelle' }[w.type] || 'Widget'
  }

  async function removeWidget(id) {
    if (!confirm('Widget entfernen?')) return
    try {
      await api.deleteWidget(id)
      await reload()
    } catch (e) {
      error = e.message
    }
  }

  function openSettings(w) {
    editingWidgetId = w.id
    editType = w.type
    editTitle = w.title
    editSignals = [...(w.config?.signals || [])]
    editMode = w.config?.mode || 'line'
    editBarMode = w.config?.barMode || 'stacked'
    editBucket = w.config?.bucket || 'auto'
    editEurKwh = w.config?.eurKwh != null ? String(w.config.eurKwh) : ''
  }

  async function saveSettings() {
    const w = widgets.find((x) => x.id === editingWidgetId)
    if (!w) return
    const cfg = { signals: editSignals }
    if (editType === 'charttable' || editType === 'linechart') {
      cfg.mode = editMode
      if (editMode === 'bar') {
        cfg.barMode = editBarMode
        cfg.bucket = editBucket || 'auto'
        if (editEurKwh.trim() !== '') {
          const f = Number(editEurKwh)
          if (!Number.isNaN(f)) cfg.eurKwh = f
        }
      }
    }
    try {
      await api.updateWidget(w.id, {
        type: w.type,
        title: editTitle.trim() || defaultTitle(w),
        config: cfg,
        grid: w.grid || {},
      })
      editingWidgetId = null
      await reload()
    } catch (e) {
      error = e.message
    }
  }

  onMount(reload)
</script>

<div class="stack">
  {#if error}
    <div class="banner error">{error}</div>
  {/if}

  {#if !dash}
    <div class="card empty">Lade Dashboard…</div>
  {:else}
    <div class="card toolbar">
      <button class="ghost" onclick={onback}>← Zurück</button>
      <h2 style="margin:0">{dash.name}</h2>
      <div class="spacer"></div>
      <div class="row">
        {#each PRESETS as p, i}
          <button class="preset" class:active={presetIdx === i} onclick={() => { presetIdx = i; loadData() }}>{p.label}</button>
        {/each}
        <button disabled={loading} onclick={loadData}>{loading ? '…' : '⟳ Aktualisieren'}</button>
        {#if mode === 'edit'}
          <button class="danger" onclick={() => { mode = 'view'; saveMsg = '' }}>Fertig</button>
        {:else}
          <button class="primary" onclick={enterEdit}>Bearbeiten</button>
        {/if}
      </div>
      {#if saveMsg}
        <div class="muted small">{saveMsg}</div>
      {/if}
      {#if dataSourceInfo}
        <div class="muted small">{dataSourceInfo}</div>
      {/if}
    </div>

    {#if mode === 'edit'}
      <div class="card editbar">
        <div class="row">
          <span class="muted small">Widgets:</span>
          <button class="primary" onclick={() => addWidget('linechart')}>+ Linechart</button>
          <button class="primary" onclick={() => addWidget('charttable')}>+ Leistung & Tabelle</button>
          <button class="primary" onclick={() => addWidget('stat')}>+ Statistik</button>
          <button class="primary" onclick={() => addWidget('table')}>+ Tabelle</button>
          <button class="primary" style="margin-left:auto" onclick={saveLayouts}>💾 Layout speichern</button>
        </div>
      </div>

      <div class="grid-stack" bind:this={gridEl}>
        {#each widgets as w (w.id)}
          <div
            class="grid-stack-item"
            gs-x={w.grid?.x ?? 0}
            gs-y={w.grid?.y ?? 0}
            gs-w={w.grid?.w ?? 6}
            gs-h={w.grid?.h ?? 4}
            gs-id={String(w.id)}
          >
            <div class="grid-stack-item-content item">
              <div class="item-head">
                <span class="item-title">{defaultTitle(w)}</span>
                <div class="row">
                  <button class="icon-btn" title="Einstellungen" onclick={() => openSettings(w)}>⚙</button>
                  <button class="icon-btn danger" title="Entfernen" onclick={() => removeWidget(w.id)}>🗑</button>
                </div>
              </div>
              <div class="item-body">
                <WidgetBody
                  widget={w}
                  responses={data[w.id] || []}
                  consumption={consults[w.id] || null}
                  height={0}
                  editable
                  onAddSignal={() => openSettings(w)}
                  onRemoveSignal={(sigId) => removeSignalFromWidget(w.id, sigId)}
                />
              </div>
            </div>
          </div>
        {/each}
      </div>
    {:else}
      <div class="view-grid">
        {#each widgets as w (w.id)}
          <div
            class="widget-card"
            style="grid-column: span {Math.min(12, Math.max(w.grid?.w || 6, 2))}"
          >
            <div class="widget-title">{defaultTitle(w)}</div>
            <WidgetBody widget={w} responses={data[w.id] || []} consumption={consults[w.id] || null} height={260} />
          </div>
        {/each}
        {#if widgets.length === 0}
          <div class="card empty">Noch keine Widgets — klicke „Bearbeiten“, um Charts hinzuzufügen.</div>
        {/if}
      </div>
    {/if}
  {/if}
</div>

<!-- Settings-Modal -->
{#if editingWidgetId !== null}
  <div class="modal-backdrop" onclick={(e) => e.target === e.currentTarget && (editingWidgetId = null)}>
    <div class="modal card">
      <h2>Widget-Einstellungen</h2>
      <label class="lbl">Titel</label>
      <input bind:value={editTitle} placeholder="Titel des Widgets" style="width:100%" />
      <label class="lbl">Signale (alle gespeicherten Kanäle)</label>
      <input
        bind:value={sensorQuery}
        placeholder="Sensoren durchsuchen… (Name, Gerät, Einheit)"
        style="width:100%; margin-bottom:6px"
      />
      <div class="sig-list">
        {#if sensors.length === 0}
          <div class="muted">Keine Kanäle gefunden. Starte unter „Sensors“ eine Discovery, damit Signale gespeichert werden.</div>
        {:else if filteredSensors.length === 0}
          <div class="muted">Keine Kanäle passen zu „{sensorQuery}“.</div>
        {:else}
          {#each filteredSensors as s}
            <label class="sig-opt">
              <input type="checkbox" bind:group={editSignals} value={s.id} />
              <span class="min-w-0">
                <span class="sig-name">{s.component_name} — {s.display_name}</span>
                <span class="muted small"> ({s.engineering_unit || '—'}){#if s.historizing} <span class="badge sig-rec">aufgezeichnet</span>{/if}</span>
              </span>
            </label>
          {/each}
        {/if}
      </div>
      {#if editType === 'charttable' || editType === 'linechart'}
        <label class="lbl">Anzeige</label>
        <div class="row">
          <label class="seg"><input type="radio" bind:group={editMode} value="line" /> Linien (Verlauf + Statistik)</label>
          <label class="seg"><input type="radio" bind:group={editMode} value="bar" /> Balken (kWh + Kosten)</label>
        </div>
        {#if editMode === 'bar'}
          <label class="lbl">Balken-Darstellung</label>
          <div class="row">
            <label class="seg"><input type="radio" bind:group={editBarMode} value="stacked" /> Gestapelt (Anteile)</label>
            <label class="seg"><input type="radio" bind:group={editBarMode} value="grouped" /> Nebeneinander</label>
          </div>
          <label class="lbl">Zeitraum-Auflösung</label>
          <select bind:value={editBucket} style="margin-bottom:4px">
            <option value="auto">Automatisch (je nach Zeitraum)</option>
            <option value="hour">Stunde</option>
            <option value="day">Tag</option>
            <option value="week">Woche</option>
            <option value="month">Monat</option>
          </select>
          <label class="lbl">€/kWh (leer = global: {eurKwhGlobal.toFixed(2)} €)</label>
          <input type="number" bind:value={editEurKwh} step="0.01" min="0" style="width:130px" placeholder="z. B. 0,32" />
        {/if}
      {/if}
      <div class="row" style="margin-top:14px; justify-content:flex-end">
        <button onclick={() => (editingWidgetId = null)}>Abbrechen</button>
        <button class="primary" onclick={saveSettings}>Speichern</button>
      </div>
    </div>
  </div>
{/if}

<style>
  .stack { display: flex; flex-direction: column; gap: 14px; }
  .toolbar { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .spacer { flex: 1; }
  .preset.active { border-color: var(--accent); color: var(--accent); }
  .ghost { background: transparent; }
  .banner { padding: 10px 14px; border-radius: 8px; font-size: 13px; }
  .banner.error { background: rgba(181,83,74,0.15); border: 1px solid var(--red); color: #e0a09a; }
  .editbar { padding: 10px 16px; }
  .grid-stack { min-height: 300px; }
  .item { display: flex; flex-direction: column; overflow: hidden; }
  .item-head {
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 4px 2px 6px;
    border-bottom: 1px solid var(--border);
    margin-bottom: 6px;
  }
  .item-title { font-size: 13px; font-weight: 600; }
  .item-body { flex: 1; min-height: 0; }
  .icon-btn {
    padding: 2px 7px;
    font-size: 13px;
    line-height: 1.4;
  }
  .icon-btn.danger { color: var(--red); }
  .view-grid {
    display: grid;
    grid-template-columns: repeat(12, 1fr);
    gap: 14px;
  }
  .widget-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 12px 14px;
    display: flex;
    flex-direction: column;
    gap: 8px;
    min-width: 0;
  }
  .widget-title { font-size: 13px; font-weight: 600; color: var(--text); }
  .modal-backdrop {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, 0.6);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 50;
  }
  .modal { width: min(560px, 94vw); max-height: 80vh; overflow: auto; }
  .lbl { display: block; margin: 10px 0 4px; font-size: 12px; color: var(--muted); }
  .sig-list { max-height: 300px; overflow-y: auto; border: 1px solid var(--border); border-radius: 8px; padding: 8px; display: flex; flex-direction: column; gap: 4px; }
  .sig-opt {
    display: flex;
    gap: 8px;
    align-items: baseline;
    padding: 4px 6px;
    border-radius: 6px;
    font-size: 13px;
    cursor: pointer;
  }
  .sig-opt:hover { background: var(--surface-2); }
  .seg { display: flex; gap: 6px; align-items: center; font-size: 13px; color: var(--text); padding: 4px 10px 4px 5px; border: 1px solid var(--border); border-radius: 6px; cursor: pointer; }
  .seg:hover { background: var(--surface-2); }
  .sig-name { font-weight: 500; }
  .sig-rec {
    background: rgba(52, 211, 153, 0.12);
    color: var(--success);
    border: 1px solid rgba(52, 211, 153, 0.25);
  }
  .small { font-size: 11px; }
</style>
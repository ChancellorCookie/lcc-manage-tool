<script>
  import { onMount } from 'svelte'
  import Icon from '../Icon.svelte'
  import { api } from '../viz_api.js'

  // ── Server / Discovery (viz) ───────────────────────────────────
  let servers = $state([])
  let cfg = $state({ default_opcua_url: '' })
  let activeServerId = $state(null)
  let devices = $state([])
  let monitoredList = $state([])
  let search = $state('')
  let expandedId = $state(null)
  let expandedSignals = $state([])
  let signalsLoading = $state(false)
  let discovering = $state(false)
  let busy = $state(null)
  let message = $state('')
  let error = $state('')
  let newName = $state('')
  let newUrl = $state('')

  // ── device_cache-Merge (Online-Status + Offline-Überwachung) ──
  let cacheMap = $state({}) // serial -> {online, offlineMonitor, nodeId, componentName}

  // ── Side-Panel (Eigenschaften / Location-Override) ─────────────
  let selected = $state(null)
  let props = $state([])
  let propsLoading = $state(false)
  let editRow = $state(null)
  let editVal = $state('')
  let saving = $state(false)
  let locModalOpen = $state(false)
  let locValue = $state('')
  let locSaving = $state(false)

  let hasLocation = $derived(
    props.some((p) => p.name === 'HierarchicalLocation' && p.value != null && p.value !== '' && String(p.value) !== 'null'),
  )

  const filteredDevices = $derived(
    search
      ? devices.filter((d) => `${d.component_name} ${d.hierarchical_location} ${d.serial}`.toLowerCase().includes(search.toLowerCase()))
      : devices,
  )

  async function loadConfig() {
    try { cfg = await api.config(); if (!newUrl) newUrl = cfg.default_opcua_url } catch (e) { /* ignore */ }
  }

  async function loadServers() {
    try { servers = await api.servers() } catch (e) { error = e.message }
  }

  async function loadCache() {
    try {
      const r = await fetch('/api/opcua/devices/cached')
      const cd = await r.json()
      const m = {}
      for (const d of (cd.devices || [])) m[d.serial] = d
      cacheMap = m
    } catch (e) { /* cache optional */ }
  }

  async function loadDevices(serverId) {
    activeServerId = serverId
    expandedId = null
    try {
      const vd = await api.devices(serverId)
      devices = vd
      monitoredList = await api.monitored(serverId)
      await loadCache()
    } catch (e) { error = e.message }
  }

  async function addServer() {
    if (!newName.trim() || !newUrl.trim()) { error = 'Name und OPC-UA-URL angeben'; return }
    error = ''
    try {
      const s = await api.addServer({ name: newName.trim(), url: newUrl.trim() })
      newName = ''
      await loadServers()
      await loadDevices(s.id)
      message = 'Server hinzugefügt — jetzt „Discover“ klicken'
    } catch (e) { error = e.message }
  }

  async function discover(id) {
    discovering = true
    error = ''
    try {
      const res = await api.discover(id)
      message = `Discovery fertig: ${res.devices_added} neue Geräte (${res.total_devices} gesamt)`
      await loadDevices(id)
    } catch (e) { error = e.message }
    discovering = false
  }

  async function removeServer(id) {
    try {
      await api.deleteServer(id)
      await loadServers()
      if (activeServerId === id) { devices = []; activeServerId = null; expandedId = null }
    } catch (e) { error = e.message }
  }

  // ── Aufklappen → Sensoren ──────────────────────────────────────
  async function toggle(d) {
    if (expandedId === d.id) { expandedId = null; return }
    expandedId = d.id
    signalsLoading = true
    try { expandedSignals = await api.signals(d.id) } catch (e) { error = e.message; expandedSignals = [] }
    signalsLoading = false
  }

  async function monitor(id) {
    busy = id
    try { await api.monitor(id); await refreshAfterChange() } catch (e) { error = e.message }
    busy = null
  }

  async function unmonitor(id) {
    busy = id
    try { await api.unmonitor(id); await refreshAfterChange() } catch (e) { error = e.message }
    busy = null
  }

  async function refreshAfterChange() {
    if (expandedId) expandedSignals = await api.signals(expandedId)
    devices = await api.devices(activeServerId)
    monitoredList = await api.monitored(activeServerId)
    await loadCache()
  }

  // ── Offline-Überwachung (device_cache) ─────────────────────────
  async function toggleMonitor(dev, checked) {
    try {
      const r = await fetch('/api/opcua/devices/monitor', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ serial: dev.serial, enabled: checked }),
      })
      if (!r.ok) throw new Error((await r.json())?.error || 'Fehler')
      await loadCache()
    } catch (e) { error = 'Überwachen-Umschalten fehlgeschlagen: ' + e.message }
  }

  // ── Side-Panel: Eigenschaften lesen (device_cache nodeId) ──────
  async function selectDevice(dev) {
    selected = dev
    propsLoading = true
    props = []
    editRow = null
    const nodeId = cacheMap[dev.serial]?.nodeId || ''
    if (!nodeId) { propsLoading = false; return }
    try {
      const parts = nodeId.split(';')
      const ns = parts[0]
      const sid = parts[1].split('=')[1]
      const locId = ns + ';s=' + sid + '-HierarchicalLocation'
      let r = await fetch('/api/opcua/read?nodeId=' + encodeURIComponent(locId))
      let data = await r.json()
      if (data.value != null) props = [...props, { name: 'HierarchicalLocation', nodeId: locId, value: data.value }]

      const idId = ns + ';s=' + sid + '-Identification'
      r = await fetch('/api/opcua/browse?nodeId=' + encodeURIComponent(idId))
      data = await r.json()
      for (const c of (data.children || [])) {
        if (c.name === 'DeviceClass') {
          r = await fetch('/api/opcua/read?nodeId=' + encodeURIComponent(c.nodeId))
          data = await r.json()
          if (data.value != null) props = [...props, { name: 'Identification/DeviceClass', nodeId: c.nodeId, value: data.value }]
        }
        if (c.name === 'ComponentName') {
          r = await fetch('/api/opcua/read?nodeId=' + encodeURIComponent(c.nodeId))
          data = await r.json()
          if (data.value != null) props = [...props, { name: 'ComponentName', nodeId: c.nodeId, value: data.value }]
        }
      }

      const directCnId = ns + ';s=' + sid + '-ComponentName'
      r = await fetch('/api/opcua/read?nodeId=' + encodeURIComponent(directCnId))
      data = await r.json()
      if (data.value != null && !String(data.value).startsWith('LocalizedText')) {
        props = props.map((p) => (p.name === 'ComponentName' ? { ...p, value: String(data.value), nodeId: directCnId } : p))
      } else {
        const cnProp = props.find((p) => p.name === 'ComponentName')
        if (cnProp) {
          const m = String(cnProp.value).match(/Text='([^']*)'/)
          if (m) cnProp.value = m[1]
        }
      }
    } catch (e) { error = e.message }
    finally { propsLoading = false }
  }

  function cancelEdit() { editRow = null }

  async function doSave() {
    saving = true
    try {
      await fetch('/api/opcua/write', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ nodeId: editRow.nodeId, value: editVal }),
      })
      props = props.map((p) => (p.nodeId === editRow.nodeId ? { ...p, value: editVal } : p))
      editRow = null
    } catch (e) { error = e.message }
    finally { saving = false }
  }

  function openLocationModal() { locValue = ''; locModalOpen = true }

  async function saveLocation() {
    const val = locValue.trim()
    if (!val || !selected) return
    const devId = (selected.component_name || selected.serial || '').trim()
    if (!devId) { error = 'Geräte-Name nicht verfügbar'; return }
    locSaving = true
    try {
      const browsePath = `DeviceSet/${devId}/HierarchicalLocation`
      const r = await fetch('/api/lads/override', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ browsePath, value: val, dataType: 'String', referenceType: 'property' }),
      })
      if (!r.ok) throw new Error((await r.json())?.error || 'Fehler')
      locModalOpen = false
      locValue = ''
      await selectDevice(selected)
    } catch (e) { error = 'Location speichern fehlgeschlagen: ' + e.message }
    finally { locSaving = false }
  }

  onMount(async () => {
    await loadConfig()
    await loadServers()
    if (!servers.length) {
      // Auto-Provision: Server aus OPC_URL anlegen + discover
      try {
        await api.addServer({ name: 'LADSProxy', url: cfg.default_opcua_url })
        await loadServers()
      } catch (e) { /* ignore */ }
    }
    if (servers.length) {
      await discover(servers[0].id)
      await loadDevices(servers[0].id)
    }
  })
</script>

<div>
  <h2 class="text-2xl font-bold mb-1 flex items-center gap-2"><Icon name="sensors" size={22} /> OPC UA Sensors</h2>
  <p class="text-slate-500 text-sm mb-6">Geräte-Discovery, Sensoren überwachen und Eigenschaften — eine Quelle (OPC UA)</p>

  {#if error}
    <div class="card border-red-500/30 mb-4 text-red-400 text-sm">{error}</div>
  {/if}
  {#if message}
    <div class="card border-blue-500/30 mb-4 text-blue-400 text-sm">{message}</div>
  {/if}

  <!-- Server-Leiste -->
  <div class="card mb-4" style="padding:0.75rem 1rem">
    <div class="flex flex-wrap items-center gap-2">
      <span class="text-xs text-slate-500 mr-1">Server:</span>
      {#each servers as s}
        <span class="text-xs {activeServerId === s.id ? 'text-blue-400' : 'text-slate-300'}">{s.name}</span>
      {/each}
      <button class="btn btn-primary" onclick={() => discover(servers[0]?.id)} disabled={discovering || !servers.length}>
        {discovering ? '…' : 'Discover'}
      </button>
      <span class="text-xs text-slate-600 mx-1">·</span>
      <input placeholder="Name" bind:value={newName} class="!w-auto !py-1 text-xs" />
      <input placeholder="OPC-UA-URL" bind:value={newUrl} class="!w-auto !py-1 text-xs" style="min-width:220px" />
      <button class="btn btn-ghost" onclick={addServer}>+ Server</button>
      <span class="ml-auto text-xs text-slate-600">{devices.length} Geräte</span>
    </div>
  </div>

  <div class="flex gap-6 items-start">
    <!-- Gerätetabelle (aufklappbar) -->
    <div class="card flex-1" style="padding:0.75rem">
      <input type="text" placeholder="Filter devices..." bind:value={search} class="!w-auto mb-2 text-xs" />

      {#if devices.length === 0}
        <div class="text-slate-500 text-sm py-8 text-center">Noch keine Geräte — klicke „Discover".</div>
      {:else}
        <div class="max-h-[65vh] overflow-y-auto">
          <table class="table-glass text-xs w-full">
            <thead>
              <tr class="text-[0.65rem] text-slate-500 uppercase tracking-wider">
                <th class="py-2 px-3 text-left font-medium">Gerät</th>
                <th class="py-2 px-3 text-left font-medium">Ort</th>
                <th class="py-2 px-3 text-right font-medium w-10">NS</th>
                <th class="py-2 px-3 text-center font-medium w-16">Überw.</th>
                <th class="py-2 px-3 text-center font-medium w-16">Offline</th>
              </tr>
            </thead>
            <tbody>
              {#each filteredDevices as d (d.id)}
                {@const c = cacheMap[d.serial] || {}}
                {@const ns = (c.nodeId || '').split(';')[0].replace('ns=', '') || '—'}
                <tr class="cursor-pointer hover:bg-slate-800/40" onclick={() => selectDevice(d)}>
                  <td class="py-1.5 px-3">
                    <div class="flex items-center gap-2">
                      <button class="text-blue-400 w-4 h-4 flex items-center justify-center" onclick={(e) => { e.stopPropagation(); toggle(d) }} title="Sensoren aufklappen">
                        {expandedId === d.id ? '▾' : '▸'}
                      </button>
                      <span class="w-2 h-2 rounded-full flex-shrink-0"
                        style="background:{c.online === 1 ? '#34d399' : c.online === 0 ? '#f87171' : '#475569'}"
                        title={c.online === 1 ? 'Online' : c.online === 0 ? 'Offline' : 'Unbekannt'}></span>
                      <span class="truncate max-w-[300px]">{d.component_name || d.serial}</span>
                    </div>
                  </td>
                  <td class="py-1.5 px-3 text-slate-500">{d.hierarchical_location || '—'}</td>
                  <td class="py-1.5 px-3 text-right text-slate-500 text-[0.6rem]">{ns}</td>
                  <td class="py-1.5 px-3 text-center"><span class="badge {d.monitored_count > 0 ? 'badge-online' : 'badge-manual'}">{d.monitored_count}</span></td>
                  <td class="py-1.5 px-3 text-center" onclick={(e) => e.stopPropagation()}>
                    <input type="checkbox" checked={!!c.offlineMonitor} title="Offline überwachen"
                      onchange={(e) => toggleMonitor(d, e.currentTarget.checked)} />
                  </td>
                </tr>
                {#if expandedId === d.id}
                  <tr><td colspan="5" class="!bg-slate-900/50 !py-2">
                    {#if signalsLoading}
                      <div class="text-xs text-slate-500 px-3">Lade Sensoren…</div>
                    {:else if expandedSignals.length === 0}
                      <div class="text-xs text-slate-500 px-3">Keine Sensoren gefunden.</div>
                    {:else}
                      <div class="flex flex-col gap-1 px-2">
                        {#each expandedSignals as s (s.id)}
                          <div class="flex items-center justify-between gap-3 px-2 py-1.5 rounded bg-slate-950/60 border border-slate-800">
                            <div class="text-xs">
                              {s.display_name}
                              <span class="text-slate-500"> · {s.engineering_unit || '—'}{s.historizing ? '' : ' (nicht historisierend)'}</span>
                            </div>
                            {#if s.monitored}
                              <button class="btn btn-danger !py-0.5 !px-2 text-xs" onclick={() => unmonitor(s.id)} disabled={busy === s.id}>{busy === s.id ? '…' : 'Entfernen'}</button>
                            {:else}
                              <button class="btn btn-primary !py-0.5 !px-2 text-xs" onclick={() => monitor(s.id)} disabled={busy === s.id}>{busy === s.id ? '…' : 'Hinzufügen'}</button>
                            {/if}
                          </div>
                        {/each}
                      </div>
                    {/if}
                  </td></tr>
                {/if}
              {/each}
            </tbody>
          </table>
        </div>

        <!-- Überwachte Sensoren -->
        {#if monitoredList.length > 0}
          <div class="mt-3 border-t border-slate-800 pt-2">
            <div class="text-xs font-semibold text-slate-400 mb-1">Überwachte Sensoren ({monitoredList.length})</div>
            {#each monitoredList as m}
              <div class="flex items-center justify-between gap-2 py-1 text-xs">
                <span class="truncate">{m.component_name || m.serial} · {m.display_name}</span>
                <button class="btn btn-danger !py-0.5 !px-2 text-xs" onclick={() => unmonitor(m.id)} disabled={busy === m.id}>Entfernen</button>
              </div>
            {/each}
          </div>
        {/if}
      {/if}
    </div>

    <!-- Eigenschaften-Panel -->
    <div class="card flex-shrink-0" style="width:410px">
      {#if selected}
        <h3 class="text-xs font-semibold mb-0.5 truncate">{selected.component_name || selected.serial}</h3>
        <div class="text-[0.55rem] text-slate-600 font-mono mb-2">{cacheMap[selected.serial]?.nodeId || selected.serial}</div>

        <button class="w-full mb-3 py-1.5 rounded-lg border border-blue-500/30 text-xs text-blue-400 hover:bg-blue-500/10 transition-colors flex items-center justify-center gap-2"
          onclick={() => { window.location.hash = '#/sensorhistory?device=' + encodeURIComponent(selected.serial) }}>
          📊 History
        </button>

        {#if propsLoading}
          <div class="text-slate-500 text-center py-6 text-[0.6rem]">Loading...</div>
        {:else if props.length === 0}
          <p class="text-slate-500 text-[0.6rem]">Keine editierbaren Eigenschaften gefunden.</p>
        {:else}
          <table class="table-glass w-full text-[0.55rem]">
            <thead><tr class="text-[0.5rem] text-slate-500 uppercase tracking-wider"><th class="py-0.5 px-1 text-left font-medium">Property</th><th class="py-0.5 px-1 text-left font-medium">Value</th><th class="w-4"></th></tr></thead>
            <tbody>
              {#each props as p (p.nodeId)}
                <tr class="border-t border-slate-800/50">
                  <td class="py-0.5 px-1 text-slate-400 break-all font-mono" style="font-size:0.65rem">{p.name}</td>
                  <td class="py-0.5 px-1"><code class="text-[0.55rem] text-green-400 break-all">{p.value}</code></td>
                  <td class="py-0.5 px-0">
                    <button class="p-0.5 rounded hover:bg-slate-700 text-slate-500 hover:text-slate-300 transition-colors" onclick={() => { editRow = p; editVal = p.value }} title="Edit">✎</button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}

        {#if !propsLoading && !hasLocation}
          <button class="w-full mt-3 py-1.5 rounded-lg border border-amber-500/30 text-xs text-amber-400 hover:bg-amber-500/10 transition-colors flex items-center justify-center gap-2" onclick={openLocationModal}>
            📍 Location konfigurieren
          </button>
        {/if}
      {:else}
        <div class="text-center py-16 text-slate-500">
          <div class="text-4xl mb-3">◫</div>
          <p class="text-sm">Gerät auswählen, um Eigenschaften zu sehen.</p>
        </div>
      {/if}
    </div>
  </div>
</div>

<!-- Edit Modal -->
{#if editRow}
  <div class="modal-overlay" onclick={cancelEdit}>
    <div class="card max-w-sm w-full" onclick={(e) => e.stopPropagation()}>
      <h3 class="text-lg font-semibold mb-4">Edit: {editRow.name}</h3>
      <div class="space-y-4"><div><label>Value</label><input type="text" bind:value={editVal} placeholder={editRow.value} /></div></div>
      <div class="flex gap-3 justify-end mt-6">
        <button class="btn btn-ghost" onclick={cancelEdit}>Cancel</button>
        <button class="btn btn-success" onclick={doSave} disabled={saving}>{saving ? 'Saving...' : 'Save'}</button>
      </div>
    </div>
  </div>
{/if}

<!-- Location-Override Modal -->
{#if locModalOpen}
  <div class="modal-overlay" onclick={() => locModalOpen = false}>
    <div class="card max-w-sm w-full" onclick={(e) => e.stopPropagation()}>
      <h3 class="text-lg font-semibold mb-1">Location konfigurieren</h3>
      <p class="text-xs text-slate-500 mb-4 break-all font-mono">{selected?.component_name || selected?.serial}</p>
      <div class="space-y-4"><div><label>HierarchicalLocation</label><input type="text" bind:value={locValue} placeholder="z. B. IEU/R404" autofocus /></div></div>
      <div class="flex gap-3 justify-end mt-6">
        <button class="btn btn-ghost" onclick={() => locModalOpen = false}>Abbrechen</button>
        <button class="btn btn-success" onclick={saveLocation} disabled={locSaving || !locValue.trim()}>{locSaving ? 'Speichern…' : 'Speichern'}</button>
      </div>
    </div>
  </div>
{/if}

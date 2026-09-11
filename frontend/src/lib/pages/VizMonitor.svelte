<script>
  import { onMount } from 'svelte'
  import Icon from '../Icon.svelte'
  import { api } from '../viz_api.js'

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

  const filteredDevices = $derived(
    search
      ? devices.filter((d) =>
          `${d.component_name} ${d.hierarchical_location} ${d.serial}`.toLowerCase().includes(search.toLowerCase()),
        )
      : devices,
  )

  async function loadConfig() {
    try {
      cfg = await api.config()
      if (!newUrl) newUrl = cfg.default_opcua_url
    } catch (e) { /* ignore */ }
  }

  async function loadServers() {
    try { servers = await api.servers() } catch (e) { error = e.message }
  }

  async function loadDevices(serverId) {
    activeServerId = serverId
    expandedId = null
    try {
      devices = await api.devices(serverId)
      monitoredList = await api.monitored(serverId)
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

  async function toggle(d) {
    if (expandedId === d.id) { expandedId = null; return }
    expandedId = d.id
    signalsLoading = true
    try { expandedSignals = await api.signals(d.id) } catch (e) { error = e.message; expandedSignals = [] }
    signalsLoading = false
  }

  async function refreshAfterChange() {
    if (expandedId) expandedSignals = await api.signals(expandedId)
    devices = await api.devices(activeServerId)
    monitoredList = await api.monitored(activeServerId)
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

  onMount(() => { loadConfig(); loadServers() })
</script>

<div>
  <h2 class="text-xl font-bold mb-1 flex items-center gap-2"><Icon name="sensors" size={22} /> Monitoring</h2>
  <p class="text-sm text-slate-500 mb-6">OPC-UA-Server, Geräte-Discovery und Auswahl der zu überwachenden Sensoren (für Dashboards &amp; Collector)</p>

  {#if error}
    <div class="card border-red-500/30 mb-4 text-red-400 text-sm">{error}</div>
  {/if}
  {#if message}
    <div class="card border-blue-500/30 mb-4 text-blue-400 text-sm">{message}</div>
  {/if}

  <!-- Server -->
  <div class="card mb-6">
    <h3 class="font-semibold mb-3">LADS-Server (OPC UA)</h3>
    <div class="flex flex-wrap gap-2 mb-3">
      <input placeholder="Name (z. B. LADSProxy)" bind:value={newName} class="!w-auto" />
      <input placeholder="OPC-UA-URL (opc.tcp://…)" bind:value={newUrl} class="!w-auto flex-1 min-w-[260px]" />
      <button class="btn btn-primary" onclick={addServer}>Server hinzufügen</button>
    </div>

    {#if servers.length === 0}
      <div class="text-sm text-slate-500">Noch kein Server. Füge einen OPC-UA-Endpunkt hinzu (URL ist vorbefüllt).</div>
    {:else}
      <table class="table-glass">
        <thead><tr><th>Name</th><th>URL</th><th></th></tr></thead>
        <tbody>
          {#each servers as s}
            <tr>
              <td>{s.name}</td>
              <td class="text-slate-500">{s.url}</td>
              <td class="!text-right">
                <button class="btn btn-primary" onclick={() => discover(s.id)} disabled={discovering}>{discovering ? '…' : 'Discover'}</button>
                <button class="btn btn-ghost ml-1" onclick={() => loadDevices(s.id)}>Geräte</button>
                <button class="btn btn-danger ml-1" onclick={() => removeServer(s.id)}>Löschen</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    {/if}
  </div>

  {#if activeServerId}
    <!-- Geräteliste (aufklappbar) -->
    <div class="card mb-6">
      <h3 class="font-semibold mb-3">Geräte{#if devices.length} ({devices.length}){/if}</h3>
      <input placeholder="Suchen (Name, Ort, Seriennummer)…" bind:value={search} class="!w-auto mb-3" style="max-width:360px" />
      {#if devices.length === 0}
        <div class="text-sm text-slate-500">Noch keine Geräte — klicke „Discover“.</div>
      {:else}
        <table class="table-glass">
          <thead><tr><th>Component Name</th><th>Ort</th><th>Klasse</th><th>Überwacht</th></tr></thead>
          <tbody>
            {#each filteredDevices as d (d.id)}
              <tr class="cursor-pointer" onclick={() => toggle(d)}>
                <td>
                  <span class="text-blue-400 mr-1">{expandedId === d.id ? '▾' : '▸'}</span>
                  {d.component_name || d.serial || d.browse_name}
                </td>
                <td class="text-slate-500">{d.hierarchical_location || '—'}</td>
                <td class="text-slate-500">{d.device_class || '—'}</td>
                <td><span class="badge {d.monitored_count > 0 ? 'badge-online' : 'badge-manual'}">{d.monitored_count}</span></td>
              </tr>
              {#if expandedId === d.id}
                <tr><td colspan="4" class="!bg-slate-900/50">
                  {#if signalsLoading}
                    <div class="text-xs text-slate-500 p-2">Lade Sensoren…</div>
                  {:else if expandedSignals.length === 0}
                    <div class="text-xs text-slate-500 p-2">Keine Sensoren gefunden.</div>
                  {:else}
                    <div class="flex flex-col gap-2 p-1">
                      {#each expandedSignals as s (s.id)}
                        <div class="flex items-center justify-between gap-3 px-3 py-2 rounded bg-slate-950/60 border border-slate-800">
                          <div>
                            <div class="text-sm">{s.display_name}</div>
                            <div class="text-xs text-slate-500">
                              {s.engineering_unit || '—'}{s.historizing ? ' · historisierend' : ''}{s.last_value ? ` · aktuell: ${s.last_value} ${s.engineering_unit || ''}` : ''}
                            </div>
                          </div>
                          {#if s.monitored}
                            <button class="btn btn-danger" onclick={() => unmonitor(s.id)} disabled={busy === s.id}>{busy === s.id ? '…' : 'Entfernen'}</button>
                          {:else}
                            <button class="btn btn-primary" onclick={() => monitor(s.id)} disabled={busy === s.id}>{busy === s.id ? '…' : 'Hinzufügen'}</button>
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
      {/if}
    </div>

    <!-- Überwachte Sensoren -->
    <div class="card mb-6">
      <h3 class="font-semibold mb-3">Überwachte Sensoren ({monitoredList.length})</h3>
      {#if monitoredList.length === 0}
        <div class="text-sm text-slate-500">Keine überwachten Sensoren auf diesem Server.</div>
      {:else}
        <table class="table-glass">
          <thead><tr><th>Gerät</th><th>Ort</th><th>Sensor</th><th>Einheit</th><th></th></tr></thead>
          <tbody>
            {#each monitoredList as m}
              <tr>
                <td>{m.component_name || m.serial}</td>
                <td class="text-slate-500">{m.hierarchical_location || '—'}</td>
                <td>{m.display_name}</td>
                <td>{m.engineering_unit || '—'}</td>
                <td class="!text-right"><button class="btn btn-danger" onclick={() => unmonitor(m.id)} disabled={busy === m.id}>{busy === m.id ? '…' : 'Entfernen'}</button></td>
              </tr>
            {/each}
          </tbody>
        </table>
      {/if}
    </div>
  {/if}
</div>
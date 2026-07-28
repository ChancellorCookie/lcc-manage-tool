<script>
  import { onMount } from 'svelte'

  let devices = $state([])
  let loading = $state(true)
  let error = $state('')
  let selected = $state(null)
  let props = $state([])
  let propsLoading = $state(false)
  let editRow = $state(null)
  let editVal = $state('')
  let saving = $state(false)
  let search = $state('')
  let sortAsc = $state(true)

  let filteredDevices = $derived(
    (() => {
      let list = search
        ? devices.filter(d => d.name.toLowerCase().includes(search.toLowerCase()))
        : [...devices]
      list.sort((a, b) => {
        const na = (a.componentName || a.name).toLowerCase()
        const nb = (b.componentName || b.name).toLowerCase()
        return sortAsc ? na.localeCompare(nb) : nb.localeCompare(na)
      })
      return list
    })()
  )

  let stale = $state(false)

  async function loadComponentNames(list) {
    // Progressively fetch component names directly from device root
    for (const dev of list) {
      if (dev.componentName) continue
      try {
        const parts = dev.nodeId.split(';')
        const ns = parts[0]
        const sid = parts[1].split('=')[1]
        // Direct ComponentName under device root (e.g. SO1DM900129-ComponentName)
        const cnId = ns + ';s=' + sid + '-ComponentName'
        const rr = await fetch('/api/opcua/read?nodeId=' + encodeURIComponent(cnId))
        const dd = await rr.json()
        if (dd.value != null && !String(dd.value).startsWith('LocalizedText')) {
          dev.componentName = String(dd.value)
          devices = [...devices]
        }
      } catch { /* skip */ }
    }
  }

  onMount(async () => {
    // 1. Load from cache instantly
    try {
      const cr = await fetch('/api/opcua/devices/cached')
      const cd = await cr.json()
      if (cd.devices?.length) {
        devices = cd.devices
        loading = false
        stale = true
      }
    } catch { /* no cache yet */ }

    // 2. Refresh in background
    try {
      const rr = await fetch('/api/opcua/devices/refresh', { method: 'POST' })
      const rd = await rr.json()
      if (rd.devices?.length) {
        devices = rd.devices
        stale = false
        // Progressively load component names
        loadComponentNames(devices)
      }
      if (rd.error) error = rd.error
    } catch (e) { error = e.message }
    finally { loading = false }
  })

  async function selectDevice(dev) {
    selected = dev
    propsLoading = true
    props = []
    editRow = null
    try {
      const parts = dev.nodeId.split(';')
      const ns = parts[0]
      const sid = parts[1].split('=')[1]

      // HierarchicalLocation
      const locId = ns + ';s=' + sid + '-HierarchicalLocation'
      let r = await fetch('/api/opcua/read?nodeId=' + encodeURIComponent(locId))
      let data = await r.json()
      if (data.value != null) {
        props = [...props, { name: 'HierarchicalLocation', nodeId: locId, value: data.value }]
      }

      // Identification children: DeviceClass, ComponentName
      const idId = ns + ';s=' + sid + '-Identification'
      r = await fetch('/api/opcua/browse?nodeId=' + encodeURIComponent(idId))
      data = await r.json()
      for (const c of (data.children || [])) {
        if (c.name === 'DeviceClass') {
          r = await fetch('/api/opcua/read?nodeId=' + encodeURIComponent(c.nodeId))
          data = await r.json()
          if (data.value != null) {
            props = [...props, { name: 'Identification/DeviceClass', nodeId: c.nodeId, value: data.value }]
          }
        }
        if (c.name === 'ComponentName') {
          r = await fetch('/api/opcua/read?nodeId=' + encodeURIComponent(c.nodeId))
          data = await r.json()
          if (data.value != null) {
            props = [...props, { name: 'ComponentName', nodeId: c.nodeId, value: data.value }]
          }
        }
      }

      // Direct ComponentName (human-readable, e.g. "Gefrierschrank 1785 - SO1DM900129")
      const directCnId = ns + ';s=' + sid + '-ComponentName'
      r = await fetch('/api/opcua/read?nodeId=' + encodeURIComponent(directCnId))
      data = await r.json()
      if (data.value != null && !String(data.value).startsWith('LocalizedText')) {
        // Replace the Identification ComponentName with the human-readable one
        props = props.map(p => p.name === 'ComponentName' ? { ...p, value: String(data.value), nodeId: directCnId } : p)
      } else {
        // Fallback: parse LocalizedText from Identification ComponentName
        const cnProp = props.find(p => p.name === 'ComponentName')
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
      props = props.map(p => p.nodeId === editRow.nodeId ? { ...p, value: editVal } : p)
      editRow = null
    } catch (e) { error = e.message }
    finally { saving = false }
  }
</script>

<div>
  <h2 class="text-2xl font-bold mb-1">OPC UA Sensors</h2>
  <p class="text-slate-500 text-sm mb-6">
    {search ? `${filteredDevices.length} / ${devices.length}` : devices.length} devices from DeviceSet
    {#if stale}<span class="text-xs text-yellow-500 ml-2">(Cache)</span>{/if}
  </p>

  {#if error}
    <div class="card border-red-500/30 mb-4 text-red-400 text-sm">{error}</div>
  {/if}

  {#if loading}
    <div class="text-slate-500 text-center py-20">Loading devices...</div>
  {:else}
    <div class="flex gap-6">
      <!-- Device list -->
      <div class="card max-h-[70vh] overflow-y-auto flex-1 text-xs" style="padding:0">
        <div class="p-2 border-b border-slate-800">
          <input type="text" placeholder="Filter devices..." bind:value={search}
            class="text-xs py-1.5" />
        </div>
        <table class="table-glass text-xs w-full">
          <thead>
            <tr class="text-[0.65rem] text-slate-500 uppercase tracking-wider">
              <th class="py-2 px-3 text-left font-medium cursor-pointer hover:text-slate-300 select-none" onclick={() => sortAsc = !sortAsc}>
                Device {sortAsc ? '▲' : '▼'}
              </th>
              <th class="py-2 px-3 text-right font-medium w-16">NS</th>
              <th class="py-2 px-3 text-left font-medium hidden md:table-cell">Node ID</th>
            </tr>
          </thead>
          <tbody>
            {#each filteredDevices as dev, i (dev.nodeId)}
              {@const ns = dev.nodeId.split(';')[0].replace('ns=','')}
              {@const hue = (parseInt(ns) * 37) % 360}
              <tr class="cursor-pointer transition-colors {i % 2 === 0 ? 'bg-slate-800/20' : ''} {selected?.nodeId === dev.nodeId ? '!bg-blue-600/20 ring-1 ring-inset ring-blue-500/30' : 'hover:bg-slate-800/40'}"
                  onclick={() => selectDevice(dev)}>
                <td class="py-2 px-3">
                  <div class="text-xs text-slate-200 truncate max-w-[300px]">{dev.componentName || dev.name}</div>
                  {#if !dev.componentName}
                    <div class="text-[0.6rem] text-slate-600 animate-pulse">lade…</div>
                  {/if}
                </td>
                <td class="py-2 px-3 text-right">
                  <span class="inline-flex items-center gap-1 text-[0.6rem] text-slate-500 tabular-nums">
                    <span class="w-1.5 h-1.5 rounded-full flex-shrink-0" style="background:hsl({hue},60%,50%)"></span>
                    {ns}
                  </span>
                </td>
                <td class="py-2 px-3 hidden md:table-cell">
                  <code class="text-[0.6rem] text-slate-600">{dev.nodeId}</code>
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <!-- Properties -->
      <div class="card flex-shrink-0" style="width:410px">
        {#if selected}
          <h3 class="text-xs font-semibold mb-0.5 truncate">{selected.componentName || selected.name}</h3>
          <div class="text-[0.55rem] text-slate-600 font-mono mb-2">{selected.nodeId}</div>

          <!-- History button -->
          <button
            class="w-full mb-3 py-1.5 rounded-lg border border-blue-500/30 text-xs text-blue-400 hover:bg-blue-500/10 hover:border-blue-500/60 transition-colors flex items-center justify-center gap-2"
            onclick={() => {
              const name = selected.name || ''
              window.location.hash = '#/sensorhistory?device=' + encodeURIComponent(name)
            }}
          >
            <svg class="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="m19 9-5 5-4-4-3 3"/></svg>
            📊 History
          </button>

          {#if propsLoading}
            <div class="text-slate-500 text-center py-6 text-[0.6rem]">Loading...</div>
          {:else if props.length === 0}
            <p class="text-slate-500 text-[0.6rem]">No editable properties found.</p>
          {:else}
            <table class="table-glass w-full text-[0.55rem]">
              <thead><tr class="text-[0.5rem] text-slate-500 uppercase tracking-wider"><th class="py-0.5 px-1 text-left font-medium">Property</th><th class="py-0.5 px-1 text-left font-medium">Value</th><th class="w-4"></th></tr></thead>
              <tbody>
                {#each props as p (p.nodeId)}
                  <tr class="border-t border-slate-800/50">
                    <td class="py-0.5 px-1 text-slate-400 break-all font-mono" style="font-size:0.65rem">{p.name}</td>
                    <td class="py-0.5 px-1">
                      <code class="text-[0.55rem] text-green-400 break-all">{p.value}</code>
                    </td>
                    <td class="py-0.5 px-0">
                      <button class="p-0.5 rounded hover:bg-slate-700 text-slate-500 hover:text-slate-300 transition-colors" onclick={() => { editRow = p; editVal = p.value }} title="Edit">
                        <svg class="w-2.5 h-2.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M17 3a3 3 0 0 1 3 3L7 19l-4 1 1-4L17 3z"/></svg>
                      </button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          {/if}
        {:else}
          <div class="text-center py-16 text-slate-500">
            <div class="text-4xl mb-3">◫</div>
            <p class="text-sm">Select a device to view properties.</p>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>

<!-- Edit Modal -->
{#if editRow}
  <div class="modal-overlay" onclick={cancelEdit}>
    <div class="card max-w-sm w-full" onclick={(e) => e.stopPropagation()}>
      <h3 class="text-lg font-semibold mb-4">Edit: {editRow.name}</h3>
      <div class="space-y-4">
        <div>
          <label>Value</label>
          <input type="text" bind:value={editVal} placeholder={editRow.value} />
        </div>
      </div>
      <div class="flex gap-3 justify-end mt-6">
        <button class="btn btn-ghost" onclick={cancelEdit}>Cancel</button>
        <button class="btn btn-success" onclick={doSave} disabled={saving}>
          {saving ? 'Saving...' : 'Save'}
        </button>
      </div>
    </div>
  </div>
{/if}

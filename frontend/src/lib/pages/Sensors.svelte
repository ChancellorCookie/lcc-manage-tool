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

  let filteredDevices = $derived(
    search ? devices.filter(d => d.name.toLowerCase().includes(search.toLowerCase())) : devices
  )

  onMount(async () => {
    try {
      const r = await fetch('/api/opcua/browse?nodeId=ns%3D3%3Bi%3D5001')
      const d = await r.json()
      const seen = new Set()
      const filtered = []
      for (const dev of (d.children || [])) {
        if (dev.name === 'DeviceFeatures' || dev.name === 'HA Configuration') continue
        if (!seen.has(dev.name)) { seen.add(dev.name); filtered.push(dev) }
      }
      devices = filtered
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
        <table class="table-glass text-xs">
          <thead><tr><th class="text-xs">Device</th><th class="text-xs">Node ID</th></tr></thead>
          <tbody>
            {#each filteredDevices as dev (dev.nodeId)}
              <tr class="cursor-pointer hover:bg-slate-800/50"
                  class:bg-slate-800={selected?.nodeId === dev.nodeId}
                  onclick={() => selectDevice(dev)}>
                <td class="font-medium text-xs">{dev.name}</td>
                <td class="text-slate-500 font-mono" style="font-size:0.65rem">{dev.nodeId}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <!-- Properties -->
      <div class="card flex-shrink-0" style="width:380px">
        {#if selected}
          <h3 class="font-semibold mb-1 text-sm">{selected.name}</h3>
          <div class="text-xs text-slate-500 font-mono mb-4">{selected.nodeId}</div>

          {#if propsLoading}
            <div class="text-slate-500 text-center py-10 text-xs">Loading...</div>
          {:else if props.length === 0}
            <p class="text-slate-500 text-xs">No editable properties found.</p>
          {:else}
            <table class="table-glass text-xs">
              <thead><tr><th class="text-xs">Property</th><th class="text-xs">Value</th><th style="width:50px"></th></tr></thead>
              <tbody>
                {#each props as p (p.nodeId)}
                  <tr>
                    <td class="text-xs font-medium">{p.name}</td>
                    <td class="text-xs font-mono text-green-400">{p.value}</td>
                    <td>
                      <button class="btn btn-ghost text-xs py-0.5 px-1.5" onclick={() => { editRow = p; editVal = p.value }}>
                        ✎
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

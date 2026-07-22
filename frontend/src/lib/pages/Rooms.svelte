<script>
  import { api, unwrap } from '../api.js'
  import { onMount } from 'svelte'

  const SENSOR_TYPES = ['Temperature', 'Humidity']
  const PATH_TEMPLATE = 'DeviceSet/{sn}@{sn}/FunctionalUnitSet/SensorUnit/FunctionSet/{type}/SensorValue'

  let rooms = $state([])
  let loading = $state(true)
  let error = $state('')
  let showDelete = $state(null)
  let editing = $state(null)
  let editMonitoring = $state([])

  onMount(async () => { await loadRooms() })

  async function loadRooms() {
    loading = true; error = ''
    try { rooms = unwrap(await api.rooms.list()) }
    catch (e) { error = e.message }
    finally { loading = false }
  }

  async function doDelete(roomId) {
    try {
      await api.rooms.delete(roomId)
      rooms = rooms.filter(r => r.roomId !== roomId)
      showDelete = null
    } catch (e) { error = e.message }
  }

  function parseMonitoring(mon) {
    return (mon || []).map(m => {
      const parts = m.path?.match(/DeviceSet\/([^@]+)@[^/]+\/.*\/FunctionSet\/([^/]+)\/SensorValue/)
      return {
        type: parts?.[2] || m.name || 'Temperature',
        serial: parts?.[1] || '',
        name: m.name || '',
      }
    })
  }

  function startEdit(room) {
    editing = room
    editMonitoring = parseMonitoring(room.monitoring)
  }

  function addMonitoring() {
    editMonitoring = [...editMonitoring, { type: 'Temperature', serial: '', name: '' }]
  }

  function removeMonitoring(idx) {
    editMonitoring = editMonitoring.filter((_, i) => i !== idx)
  }

  function updateMonitoring(idx, field, value) {
    editMonitoring = editMonitoring.map((m, i) =>
      i === idx ? { ...m, [field]: value } : m
    )
  }

  function buildMonitoringPayload() {
    return editMonitoring
      .filter(m => m.serial)
      .map(m => ({
        name: m.name || m.type,
        path: PATH_TEMPLATE.replace(/\{sn\}/g, m.serial).replace('{type}', m.type),
      }))
  }
</script>

<div>
  <div class="flex items-center justify-between mb-6">
    <div>
      <h2 class="text-2xl font-bold">Rooms</h2>
      <p class="text-slate-500 text-sm mt-1">Manage lab rooms, contacts, and monitoring</p>
    </div>
    <button class="btn btn-primary" onclick={() => { editing = {}; editMonitoring = [] }}>
      + New Room
    </button>
  </div>

  {#if error}
    <div class="card border-red-500/30 mb-4 text-red-400 text-sm">{error}<button class="ml-4 underline" onclick={() => error = ''}>✕</button></div>
  {/if}

  {#if loading}
    <div class="text-slate-500 text-center py-20 animate-pulse">Loading rooms...</div>
  {:else if rooms.length === 0}
    <div class="card text-center py-16 text-slate-500">
      <div class="text-4xl mb-3">◫</div>
      <p>No rooms configured yet.</p>
      <button class="btn btn-primary mt-4" onclick={() => { editing = {}; editMonitoring = [] }}>Create First Room</button>
    </div>
  {:else}
    <div class="card overflow-hidden" style="padding:0">
      <table class="table-glass">
        <thead>
          <tr><th>Room</th><th>Number</th><th>Contact</th><th>Airflow</th><th style="width:100px"></th></tr>
        </thead>
        <tbody>
          {#each rooms as room (room.roomId)}
            <tr>
              <td><div class="font-medium">{room.name}</div><div class="text-xs text-slate-500 font-mono">{room.roomId}</div></td>
              <td class="text-slate-400">{room.number || '—'}</td>
              <td>
                {#if room.contact?.name}
                  <div class="text-sm">{room.contact.name}</div><div class="text-xs text-slate-500">{room.contact.email || ''}</div>
                {:else}<span class="text-slate-600">—</span>{/if}
              </td>
              <td>
                {#if room.airflow?.min != null}
                  <span class="text-sm">{room.airflow.min} – {room.airflow.max} m³/h</span>
                {:else}<span class="text-slate-600">—</span>{/if}
              </td>
              <td>
                <div class="flex gap-1">
                  <button class="btn btn-ghost text-xs py-1 px-2" onclick={() => startEdit(room)}>Edit</button>
                  <button class="btn btn-ghost text-xs py-1 px-2 text-red-400" onclick={() => showDelete = room}>✕</button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

{#if showDelete}
  <div class="modal-overlay" onclick={() => showDelete = null}>
    <div class="card max-w-sm w-full" onclick={(e) => e.stopPropagation()}>
      <h3 class="text-lg font-semibold mb-2">Delete Room</h3>
      <p class="text-slate-400 text-sm mb-4">Permanently delete <strong>{showDelete.name}</strong> ({showDelete.roomId})?</p>
      <div class="flex gap-3 justify-end">
        <button class="btn btn-ghost" onclick={() => showDelete = null}>Cancel</button>
        <button class="btn btn-danger" onclick={() => doDelete(showDelete.roomId)}>Delete</button>
      </div>
    </div>
  </div>
{/if}

{#if editing}
  <div class="modal-overlay" onclick={() => editing = null}>
    <div class="card max-w-xl w-full max-h-[90vh] overflow-y-auto" onclick={(e) => e.stopPropagation()}>
      <h3 class="text-lg font-semibold mb-4">{editing.roomId ? `Edit: ${editing.name}` : 'New Room'}</h3>

      <form onsubmit={async (e) => {
        e.preventDefault()
        const fd = new FormData(e.target)
        const data = {
          roomId: fd.get('roomId'),
          name: fd.get('name'),
          number: fd.get('number') || null,
          contact: { name: fd.get('contactName') || '', email: fd.get('contactEmail') || '' },
          monitoring: buildMonitoringPayload(),
        }
        try {
          if (editing.roomId) {
            await api.rooms.patchMeta(editing.roomId, data)
          } else {
            await api.rooms.create(data)
          }
          editing = null
          await loadRooms()
        } catch (err) { error = err.message }
      }}>
        <div class="space-y-4">
          <div><label>Room ID (path)</label><input name="roomId" value={editing.roomId || ''} required disabled={!!editing.roomId} placeholder="IEU/R101" /></div>
          <div><label>Name</label><input name="name" value={editing.name || ''} required placeholder="Labor 101" /></div>
          <div><label>Number</label><input name="number" value={editing.number || ''} placeholder="R 101" /></div>

          <div class="border-t border-slate-800 pt-4">
            <p class="text-xs text-slate-500 uppercase mb-3">Contact</p>
            <div class="grid grid-cols-2 gap-3">
              <div><label>Name</label><input name="contactName" value={editing.contact?.name || ''} placeholder="Max Mustermann" /></div>
              <div><label>Email</label><input name="contactEmail" value={editing.contact?.email || ''} placeholder="max@lab.de" /></div>
            </div>
          </div>

          <div class="border-t border-slate-800 pt-4">
            <div class="flex items-center justify-between mb-3">
              <p class="text-xs text-slate-500 uppercase">Monitoring Sensors</p>
              <button type="button" class="btn btn-ghost text-xs py-1 px-2" onclick={addMonitoring}>+ Add Sensor</button>
            </div>

            {#if editMonitoring.length === 0}
              <p class="text-xs text-slate-600 italic">No sensors configured</p>
            {:else}
              <div class="space-y-2">
                {#each editMonitoring as mon, idx (idx)}
                  <div class="flex gap-2 items-start bg-slate-900/50 rounded-lg p-3 border border-slate-800">
                    <div class="flex-1">
                      <div class="grid grid-cols-2 gap-2">
                        <div>
                          <label>Sensor Type</label>
                          <select value={mon.type} onchange={(e) => updateMonitoring(idx, 'type', e.target.value)}>
                            {#each SENSOR_TYPES as t}
                              <option value={t} selected={mon.type === t}>{t}</option>
                            {/each}
                          </select>
                        </div>
                        <div>
                          <label>Serial Number</label>
                          <input value={mon.serial} placeholder="SP2FC300133"
                            class="text-xs font-mono"
                            oninput={(e) => updateMonitoring(idx, 'serial', e.target.value)} />
                        </div>
                      </div>
                      {#if mon.serial}
                        <div class="mt-2 text-xs text-slate-600 font-mono break-all">
                          → {PATH_TEMPLATE.replace(/\{sn\}/g, mon.serial).replace('{type}', mon.type)}
                        </div>
                      {/if}
                    </div>
                    <button type="button" class="btn btn-ghost text-xs text-red-400 py-1 px-2 mt-5"
                      onclick={() => removeMonitoring(idx)}>✕</button>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        </div>

        <div class="flex gap-3 justify-end mt-6">
          <button type="button" class="btn btn-ghost" onclick={() => editing = null}>Cancel</button>
          <button type="submit" class="btn btn-primary">{editing.roomId ? 'Save Changes' : 'Create Room'}</button>
        </div>
      </form>
    </div>
  </div>
{/if}

<script>
  import { api, unwrap } from '../api.js'
  import { onMount } from 'svelte'

  let roomCount = $state(0)
  let serverCount = $state(0)
  let loading = $state(true)

  onMount(async () => {
    try {
      const [roomsResp, serversResp] = await Promise.all([
        api.rooms.list(),
        api.servers.list(),
      ])
      roomCount = unwrap(roomsResp).length
      serverCount = unwrap(serversResp).length
    } catch (e) {
      // ignore
    } finally {
      loading = false
    }
  })
</script>

<div>
  <!-- Hero -->
  <div class="relative overflow-hidden rounded-2xl mb-8 p-8" style="background: linear-gradient(135deg, #1e293b 0%, #0f172a 50%, #1a1040 100%)">
    <div class="absolute top-0 right-0 w-64 h-64 opacity-20" style="background: radial-gradient(circle, #3b82f6 0%, transparent 70%)"></div>
    <div class="relative z-10">
      <h1 class="text-3xl font-bold mb-2">
        <span class="text-blue-400">LCC</span> Manage Tool
      </h1>
      <p class="text-slate-400 max-w-md">
        Verwaltung von Laboren, OPC UA Servern und Monitoring-Konfiguration für das Waldner Lab Control Center.
      </p>
    </div>
  </div>

  <!-- Stats -->
  {#if loading}
    <div class="grid grid-cols-2 gap-4 mb-8">
      <div class="card animate-pulse h-24"></div>
      <div class="card animate-pulse h-24"></div>
    </div>
  {:else}
    <div class="grid grid-cols-2 gap-4 mb-8">
      <div class="card flex items-center gap-4">
        <div class="w-12 h-12 rounded-xl flex items-center justify-center text-2xl" style="background: rgba(59,130,246,0.15)">
          ◫
        </div>
        <div>
          <div class="text-2xl font-bold">{roomCount}</div>
          <div class="text-xs text-slate-500">Rooms</div>
        </div>
      </div>
      <div class="card flex items-center gap-4">
        <div class="w-12 h-12 rounded-xl flex items-center justify-center text-2xl" style="background: rgba(139,92,246,0.15)">
          ⬡
        </div>
        <div>
          <div class="text-2xl font-bold">{serverCount}</div>
          <div class="text-xs text-slate-500">OPC UA Servers</div>
        </div>
      </div>
    </div>
  {/if}

  <!-- Quick Info -->
  <div class="grid grid-cols-1 gap-4">
    <div class="card">
      <h3 class="font-semibold mb-3">API Status</h3>
      <div class="flex items-center gap-3">
        <span class="w-2 h-2 rounded-full bg-green-400"></span>
        <span class="text-sm text-slate-400">Mock-Backend läuft</span>
      </div>
      <div class="mt-3 text-xs text-slate-600 font-mono">/api/health &#8594; {'{'}status: ok, mode: mock{'}'}</div>
    </div>

    <div class="card">
      <h3 class="font-semibold mb-2">Schnellzugriff</h3>
      <div class="grid grid-cols-3 gap-3 mt-4">
        <a href="#" class="flex flex-col items-center gap-2 p-3 rounded-lg border border-slate-800 hover:border-blue-500/50 transition-colors text-center text-sm text-slate-400 hover:text-blue-400"
          onclick={(e) => { e.preventDefault(); /* navigate handled by parent */ }}>
          <span class="text-xl">◫</span>
          Räume verwalten
        </a>
        <a href="#" class="flex flex-col items-center gap-2 p-3 rounded-lg border border-slate-800 hover:border-blue-500/50 transition-colors text-center text-sm text-slate-400 hover:text-blue-400">
          <span class="text-xl">⬡</span>
          Server Discovery
        </a>
        <a href="#" class="flex flex-col items-center gap-2 p-3 rounded-lg border border-slate-800 hover:border-blue-500/50 transition-colors text-center text-sm text-slate-400 hover:text-blue-400">
          <span class="text-xl">⚙</span>
          Einstellungen
        </a>
      </div>
    </div>
  </div>
</div>

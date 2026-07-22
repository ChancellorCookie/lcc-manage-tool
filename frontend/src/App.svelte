<script>
  import Dashboard from './lib/pages/Dashboard.svelte'
  import Rooms from './lib/pages/Rooms.svelte'
  import Servers from './lib/pages/Servers.svelte'
  import Sensors from './lib/pages/Sensors.svelte'

  let page = $state('dashboard')
  let toastMsg = $state('')
  let toastType = $state('success')
  let toastTimer = $state(null)

  function navigate(p) {
    page = p
  }

  function showToast(msg, type = 'success') {
    toastMsg = msg
    toastType = type
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = setTimeout(() => toastMsg = '', 3000)
  }

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: '◉' },
    { id: 'rooms', label: 'Rooms', icon: '◫' },
    { id: 'servers', label: 'OPC UA Servers', icon: '⬡' },
    { id: 'sensors', label: 'OPC UA Sensors', icon: '⎔' },
  ]
</script>

<div class="flex h-screen overflow-hidden">
  <!-- Sidebar -->
  <nav class="w-56 flex-shrink-0 border-r border-slate-800 bg-slate-950/80 backdrop-blur flex flex-col">
    <div class="p-4 border-b border-slate-800">
      <h1 class="text-lg font-bold tracking-tight">
        <span class="text-blue-400">LCC</span>
        <span class="text-slate-400 ml-1">Manage</span>
      </h1>
      <p class="text-xs text-slate-600 mt-0.5">Lab Control Center</p>
    </div>

    <div class="flex-1 py-4 space-y-1 px-2">
      {#each navItems as item}
        <button
          class="w-full flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all
            {page === item.id
              ? 'bg-blue-600/20 text-blue-400 border border-blue-500/30'
              : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'}"
          onclick={() => navigate(item.id)}
        >
          <span class="text-base">{item.icon}</span>
          {item.label}
        </button>
      {/each}
    </div>

    <div class="p-4 border-t border-slate-800 text-xs text-slate-600">
      Live API · v0.2.0
    </div>
  </nav>

  <!-- Main content -->
  <main class="flex-1 overflow-y-auto">
    <div class="max-w-6xl mx-auto p-6">
      {#if page === 'dashboard'}
        <Dashboard />
      {:else if page === 'rooms'}
        <Rooms {showToast} />
      {:else if page === 'servers'}
        <Servers {showToast} />
      {:else if page === 'sensors'}
        <Sensors />
      {/if}
    </div>
  </main>
</div>

<!-- Toast -->
{#if toastMsg}
  <div class="toast toast-{toastType}">
    {toastMsg}
  </div>
{/if}

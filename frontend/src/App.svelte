<script>
  import Dashboard from './lib/pages/Dashboard.svelte'
  import Infrastructure from './lib/pages/Infrastructure.svelte'
  import Sensors from './lib/pages/Sensors.svelte'
  import SensorHistory from './lib/pages/SensorHistory.svelte'
  import MqttExplorer from './lib/pages/MqttExplorer.svelte'
  import Incidents from './lib/pages/Incidents.svelte'
  import Icon from './lib/Icon.svelte'
  import { onMount } from 'svelte'

  let page = $state('dashboard')
  let collapsed = $state(true)
  let incidentsTab = $state('incidents')
  let toastMsg = $state('')
  let toastType = $state('success')
  let toastTimer = $state(null)
  let dark = $state(true)

  function navigate(p) {
    page = p
    collapsed = true
    history.pushState({ page: p }, '', `#/${p}`)
  }

  function navTab(p, tab) {
    page = p
    incidentsTab = tab
    collapsed = true
    history.pushState({ page: p, tab }, '', `#/${p}/${tab}`)
  }

  onMount(() => {
    // Load theme preference
    const savedTheme = localStorage.getItem('lcc-theme')
    if (savedTheme === 'light') {
      dark = false
      document.documentElement.classList.add('light')
    }

    // Restore state from URL hash on load
    const hash = window.location.hash.replace('#/', '')
    if (hash) {
      const parts = hash.split('/')
      page = parts[0]
      if (parts[1]) incidentsTab = parts[1]
    }
    // Handle browser back/forward AND manual hash changes
    function syncFromHash() {
      const raw = window.location.hash.replace('#/', '')
      const [p, qs] = raw.split('?')
      if (p && p !== 'dashboard') {
        page = p
        if (p === 'incidents' && qs) {
          const params = new URLSearchParams(qs)
          incidentsTab = params.get('tab') || 'incidents'
        }
      } else {
        page = 'dashboard'
      }
    }

    window.addEventListener('popstate', (e) => {
      if (e.state?.page) {
        page = e.state.page
        if (e.state.tab) incidentsTab = e.state.tab
      } else {
        syncFromHash()
      }
    })

    window.addEventListener('hashchange', () => syncFromHash())

    // Push initial state for dashboard so back button always works
    if (!hash) {
      history.replaceState({ page: 'dashboard' }, '', '#/dashboard')
    }
  })

  function showToast(msg, type = 'success') {
    toastMsg = msg
    toastType = type
    if (toastTimer) clearTimeout(toastTimer)
    toastTimer = setTimeout(() => toastMsg = '', 3000)
  }

  function toggleTheme() {
    dark = !dark
    if (dark) {
      document.documentElement.classList.remove('light')
      localStorage.setItem('lcc-theme', 'dark')
    } else {
      document.documentElement.classList.add('light')
      localStorage.setItem('lcc-theme', 'light')
    }
  }

  const navItems = [
    { id: 'dashboard', label: 'Dashboard', icon: 'dashboard' },
    { id: 'infrastructure', label: 'Infrastructure', icon: 'rooms' },
    { id: 'sensors', label: 'Sensors', icon: 'sensors' },
    { id: 'sensorhistory', label: 'History', icon: 'gateways' },
    { id: 'mqtt', label: 'MQTT', icon: 'sensors' },
    { id: 'incidents', label: 'Incidents', icon: 'incidents' },
  ]
</script>

<div class="flex flex-col h-screen overflow-hidden">
  <div class="flex flex-1 overflow-hidden">
  <!-- Sidebar -->
  <nav
    class="flex-shrink-0 border-r border-slate-800 bg-slate-950/80 backdrop-blur flex flex-col transition-all duration-200 {collapsed ? 'w-14' : 'w-56'}"
  >
    <!-- Toggle -->
    <button
      class="p-3 border-b border-slate-800 text-slate-400 hover:text-slate-200 text-center transition-colors"
      onclick={() => collapsed = !collapsed}
      title="Toggle sidebar"
    >
      {#if collapsed}
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12h18"/><path d="M3 6h18"/><path d="M3 18h18"/></svg>
      {:else}
        <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18"/><path d="M6 6l12 12"/></svg>
      {/if}
    </button>

    {#if !collapsed}
      <div class="p-4 border-b border-slate-800">
        <h1 class="text-lg font-bold tracking-tight">
          <span class="text-blue-400">LCC</span>
          <span class="text-slate-400 ml-1">Tools</span>
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
            <span class="w-5 h-5 flex items-center justify-center">
              <Icon name={item.icon} size={18} />
            </span>
            {item.label}
          </button>
        {/each}
      </div>
    {:else}
      <div class="flex-1 py-4 space-y-1 px-1">
        {#each navItems as item}
          <button
            class="w-full flex items-center justify-center py-2.5 rounded-lg transition-all {page === item.id ? 'bg-blue-600/20 text-blue-400' : 'text-slate-400 hover:bg-slate-800/50 hover:text-slate-200'}"
            onclick={() => navigate(item.id)}
            title={item.label}
          >
            <Icon name={item.icon} size={18} />
          </button>
        {/each}
      </div>
    {/if}

    <!-- Theme toggle -->
    <button
      class="flex items-center justify-center py-2.5 rounded-lg transition-all text-slate-400 hover:bg-slate-800/50 hover:text-slate-200 {collapsed ? '' : 'w-full gap-2 px-3'}"
      onclick={toggleTheme}
      title={dark ? 'Light mode' : 'Dark mode'}
    >
      {#if dark}
        <!-- Sun icon -->
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="5"/><path d="M12 1v2M12 21v2M4.2 4.2l1.4 1.4M18.4 18.4l1.4 1.4M1 12h2M21 12h2M4.2 19.8l1.4-1.4M18.4 5.6l1.4-1.4"/>
        </svg>
      {:else}
        <!-- Moon icon -->
        <svg class="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>
        </svg>
      {/if}
      {#if !collapsed}
        <span class="text-sm">{dark ? 'Dark' : 'Light'}</span>
      {/if}
    </button>

    {#if !collapsed}
      <div class="p-4 border-t border-slate-800 text-xs text-slate-600">
        Live API · v0.3.0
      </div>
    {/if}
  </nav>

  <!-- Main content -->
  <main class="flex-1 overflow-y-auto">
    <div class="mx-auto p-6 max-w-7xl">
      {#if page === 'dashboard'}
        <Dashboard {navigate} {navTab} />
      {:else if page === 'infrastructure'}
        <Infrastructure {showToast} />
      {:else if page === 'sensors'}
        <Sensors />
      {:else if page === 'sensorhistory'}
        <SensorHistory />
      {:else if page === 'mqtt'}
        <MqttExplorer />
      {:else if page === 'incidents'}
        <Incidents initialTab={incidentsTab} />
      {/if}
    </div>
  </main>

  </div>

  <!-- Footer -->
  <footer class="border-t border-slate-800 py-3 text-xs text-slate-600 bg-slate-950/90 backdrop-blur flex-shrink-0">
    <div class="max-w-7xl mx-auto px-6 flex flex-wrap items-center gap-x-6 gap-y-1">
      <span>LCC Tools v0.3.0</span>
      <span class="text-slate-700">·</span>
      <span>LADS Client: <span class="text-slate-500">M. Arnold</span></span>
      <span class="text-slate-700">·</span>
      <a href="https://lcc.ieu.local/api/docs" target="_blank" rel="noopener" class="text-blue-500 hover:text-blue-400">LCC API Docs</a>
      <span class="text-slate-700">·</span>
      <a href="https://labnote-lite.example.org/docs" target="_blank" rel="noopener" class="text-blue-500 hover:text-blue-400">ELN API Docs</a>
      <span class="ml-auto text-slate-700">chancellorcookie</span>
    </div>
  </footer>
</div>

<!-- Toast -->
{#if toastMsg}
  <div class="toast toast-{toastType}">
    {toastMsg}
  </div>
{/if}

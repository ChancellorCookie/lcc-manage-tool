<script>
  import Rooms from './Rooms.svelte'
  import Servers from './Servers.svelte'
  import Icon from '../Icon.svelte'

  let { showToast } = $props()
  let tab = $state('rooms')
</script>

<div>
  <h2 class="text-xl font-bold mb-1 flex items-center gap-2"><Icon name="rooms" size={22} /> Infrastructure</h2>
  <p class="text-sm text-slate-500 mb-4">Räume und OPC UA Gateways verwalten</p>

  <div class="flex gap-1 mb-6 border-b border-slate-800">
    {#each [
      { id: 'rooms', label: 'Rooms' },
      { id: 'gateways', label: 'Gateways' },
    ] as t}
      <button
        class="px-4 py-2 text-sm border-b-2 transition-colors {tab === t.id ? 'border-blue-500 text-blue-400' : 'border-transparent text-slate-500 hover:text-slate-300'}"
        onclick={() => tab = t.id}
      >
        {t.label}
      </button>
    {/each}
  </div>

  {#if tab === 'rooms'}
    <Rooms {showToast} />
  {:else}
    <Servers {showToast} />
  {/if}
</div>

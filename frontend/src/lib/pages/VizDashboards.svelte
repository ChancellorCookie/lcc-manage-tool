<script>
  import { onMount } from 'svelte'
  import { api } from '../viz_api.js'
  import Dashboard from './VizDashboard.svelte'

  let { initialOpenId = null } = $props()

  let list = $state([])
  let openId = $state(null)

  // Deep-Link von der Startseite: Prop-Änderung übernimmt das Ziel-Dashboard
  $effect(() => {
    openId = initialOpenId ? Number(initialOpenId) : null
  })
  let newName = $state('')
  let error = $state('')

  async function load() {
    try {
      list = await api.dashboards()
    } catch (e) {
      error = e.message
    }
  }

  async function create() {
    if (!newName.trim()) return
    try {
      await api.createDashboard(newName.trim())
      newName = ''
      await load()
    } catch (e) {
      error = e.message
    }
  }

  async function rename(d) {
    const n = prompt('Neuer Name:', d.name)
    if (n && n.trim() && n.trim() !== d.name) {
      await api.renameDashboard(d.id, n.trim())
      await load()
    }
  }

  async function remove(d) {
    if (confirm(`Dashboard „${d.name}“ wirklich löschen?`)) {
      await api.deleteDashboard(d.id)
      await load()
    }
  }

  onMount(load)
</script>

{#if openId}
  <Dashboard
    openId={openId}
    onback={() => {
      openId = null
      load()
    }}
  />
{:else}
  <section class="card">
    <h2>Dashboards</h2>
    <div class="row" style="margin-bottom:12px">
      <input
        placeholder="Neues Dashboard (z.B. „Stromverbrauch R404“)…"
        bind:value={newName}
        style="flex:1; min-width:280px"
        onkeydown={(e) => e.key === 'Enter' && create()}
      />
      <button class="primary" onclick={create}>Anlegen</button>
    </div>
    {#if error}
      <div class="banner error">{error}</div>
    {/if}
    {#if list.length === 0}
      <div class="empty">Noch keine Dashboards angelegt.</div>
    {:else}
      <div class="dash-list">
        {#each list as d}
          <div class="dash-card">
            <div class="dash-info">
              <div class="dash-name">{d.name}</div>
              <div class="dash-desc muted small">{d.description || 'Keine Beschreibung'}</div>
              <div class="dash-meta">
                <span class="badge">{d.widget_count} Widgets</span>
              </div>
            </div>
            <div class="row dash-actions">
              <button class="primary" onclick={() => (openId = d.id)}>Öffnen</button>
              <button class="icon-btn" title="Umbenennen" onclick={() => rename(d)}>&#9998;</button>
              <button class="icon-btn danger" title="Löschen" onclick={() => remove(d)}>&#128465;</button>
            </div>
          </div>
        {/each}
      </div>
    {/if}
  </section>
{/if}

<style>
  .banner {
    padding: 10px 14px;
    border-radius: 8px;
    font-size: 13px;
    margin-bottom: 10px;
  }
  .banner.error {
    background: rgba(220, 38, 38, 0.15);
    border: 1px solid rgba(220, 38, 38, 0.4);
    color: #f87171;
  }
  .dash-list { display: flex; flex-direction: column; gap: 10px; margin-top: 6px; }
  .dash-card {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 14px;
    padding: 14px 16px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    transition: border-color 0.15s;
  }
  .dash-card:hover { border-color: var(--accent); }
  .dash-info { display: flex; flex-direction: column; gap: 3px; min-width: 0; }
  .dash-name { font-size: 15px; font-weight: 600; color: var(--text); }
  .dash-desc { font-size: 12px; color: var(--text-muted); }
  .dash-meta { margin-top: 4px; }
  .dash-card .badge {
    background: rgba(96, 165, 250, 0.12);
    color: var(--accent);
    border: 1px solid rgba(96, 165, 250, 0.25);
  }
  .dash-actions { flex-shrink: 0; }
</style>
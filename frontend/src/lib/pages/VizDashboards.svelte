<script>
  import { onMount } from 'svelte'
  import { api } from '../viz_api.js'
  import Dashboard from './VizDashboard.svelte'

  let list = $state([])
  let openId = $state(null)
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
      <table>
        <thead>
          <tr><th>Name</th><th>Widgets</th><th></th></tr>
        </thead>
        <tbody>
          {#each list as d}
            <tr>
              <td>{d.name}{#if d.description}<span class="muted small"> — {d.description}</span>{/if}</td>
              <td><span class="badge">{d.widget_count}</span></td>
              <td>
                <div class="row">
                  <button class="primary" onclick={() => (openId = d.id)}>Öffnen</button>
                  <button onclick={() => rename(d)}>Umbenennen</button>
                  <button class="danger" onclick={() => remove(d)}>Löschen</button>
                </div>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
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
</style>
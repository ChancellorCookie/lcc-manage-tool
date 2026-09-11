<script>
  import { COLORS } from '../colors.js'

  let { responses = [], editable = false, onAddSignal = null, onRemoveSignal = null, showColors = false } = $props()

  const fmt = (v) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(1)
  const fmtWh = (v) => {
    if (v === null || v === undefined || Number.isNaN(v)) return '—'
    return v >= 1000 ? `${(v / 1000).toFixed(2)} kWh` : `${v.toFixed(1)} Wh`
  }

  // Gesamt-Zeile: Summen über alle Zeilen
  const totals = $derived.by(() => {
    const t = { last: 0, min: 0, max: 0, avg: 0, energy_wh: 0, hasEnergy: false }
    for (const r of responses) {
      const st = r.stats || {}
      if (st.last != null) t.last += Number(st.last) || 0
      if (st.min != null) t.min += Number(st.min) || 0
      if (st.max != null) t.max += Number(st.max) || 0
      if (st.avg != null) t.avg += Number(st.avg) || 0
      if (st.energy_wh != null) {
        t.energy_wh += Number(st.energy_wh) || 0
        t.hasEnergy = true
      }
    }
    return t
  })
</script>

{#if responses.length || editable}
  <div class="table-wrap compact">
    <table>
      <thead>
        <tr>
          {#if showColors}<th></th>{/if}
          <th>Gerät</th><th>Sensor</th><th>Einheit</th><th>Aktuell</th><th>Min</th><th>Max</th><th>Ø</th>
          <th class="right">Energie (Zeitraum)</th>{#if editable}<th></th>{/if}
        </tr>
      </thead>
      <tbody>
        {#each responses as r, i (r.signal.id)}
          <tr>
            {#if showColors}
              <td class="swatch"><span class="dot" style="background:{COLORS[i % COLORS.length]}"></span></td>
            {/if}
            <td>{r.device?.component_name || r.device?.hierarchical_location || ''}</td>
            <td>{r.signal.display_name}</td>
            <td>{r.signal.engineering_unit || '—'}</td>
            <td>{fmt(r.stats?.last)}</td>
            <td>{fmt(r.stats?.min)}</td>
            <td>{fmt(r.stats?.max)}</td>
            <td>{fmt(r.stats?.avg)}</td>
            <td class="right strong">{fmtWh(r.stats?.energy_wh)}</td>
            {#if editable}
              <td><button class="icon-btn danger" title="Sensor entfernen" onclick={() => onRemoveSignal?.(r.signal.id)}>✕</button></td>
            {/if}
          </tr>
        {/each}
      </tbody>
      {#if responses.length > 1}
        <tfoot>
          <tr class="total-row">
            <td colspan={showColors ? 4 : 3}>Gesamt</td>
            <td>{fmt(totals.last)}</td>
            <td>{fmt(totals.min)}</td>
            <td>{fmt(totals.max)}</td>
            <td>{fmt(totals.avg)}</td>
            <td class="right strong">{fmtWh(totals.hasEnergy ? totals.energy_wh : null)}</td>
            {#if editable}<td></td>{/if}
          </tr>
        </tfoot>
      {/if}
    </table>
  </div>
  {#if editable}
    <div style="margin-top:8px">
      <button class="primary" onclick={() => onAddSignal?.()}>+ Sensor hinzufügen</button>
    </div>
  {/if}
{:else}
  <div class="hint">Keine Signale zugewiesen — im Editor bearbeiten (⚙)</div>
{/if}

<style>
  .hint {
    display: flex;
    align-items: center;
    justify-content: center;
    height: 100%;
    color: var(--text-muted);
    font-size: 13px;
    text-align: center;
    padding: 16px;
  }
  .right {
    text-align: right;
  }
  .strong {
    color: var(--accent);
    font-weight: 600;
  }
  .compact th,
  .compact td {
    padding: 3px 8px;
    font-size: 12px;
    white-space: nowrap;
  }
  .compact tbody tr:hover td {
    background: var(--hover-bg);
  }
  .swatch {
    width: 18px;
    padding-right: 2px !important;
  }
  .dot {
    display: inline-block;
    width: 9px;
    height: 9px;
    border-radius: 50%;
  }
  .total-row td {
    font-weight: 700;
    border-top: 2px solid var(--accent);
    color: var(--text);
    background: rgba(96, 165, 250, 0.08);
  }
  .table-wrap {
    overflow-x: auto;
    width: 100%;
  }
  .table-wrap table {
    width: 100%;
    border-collapse: collapse;
  }
</style>
<script>
  import UChart from './UChart.svelte'
  import SignalTable from './SignalTable.svelte'
  import BarChart from './BarChart.svelte'
  import ConsumptionTable from './ConsumptionTable.svelte'
    import UsageView from './UsageView.svelte'
    import { COLORS } from '../colors.js'

    let { widget, responses = [], consumption = null, usage = null, height = 0, editable = false, onAddSignal = null, onRemoveSignal = null } = $props()

  const fmt = (v) => (v === null || v === undefined || Number.isNaN(v)) ? '—' : Number(v).toFixed(1)
  const fmtWh = (v) => {
    if (v === null || v === undefined || Number.isNaN(v)) return '—'
    return v >= 1000 ? `${(v / 1000).toFixed(2)} kWh` : `${v.toFixed(1)} Wh`
  }

  // Kurzer Gerätename für Legende/Tooltip/Zuordnung: "LCMS 8060 - Oven A - shelly..." -> "Oven A"
  function shortLabel(comp) {
    if (!comp) return ''
    const parts = comp.split(' - ').filter(Boolean)
    if (parts.length >= 3) return parts.slice(1, -1).join(' - ')
    return comp.replace(/\s*-\s*shellyplugmg3.*$/i, '').replace(/\s*-\s*[a-z0-9]{6,}.*$/i, '').trim() || comp
  }

  function seriesFor(r, i) {
    return {
      label: shortLabel(r.device?.component_name) || r.signal.display_name,
      unit: r.signal.engineering_unit || '',
      color: COLORS[i % COLORS.length],
      xs: (r.points || []).map((p) => p[0]),
      ys: (r.points || []).map((p) => p[1]),
    }
  }
</script>

{#if widget.type === 'linechart'}
  {#if widget.config?.mode === 'bar'}
    {#if consumption && consumption.signals?.length}
      <BarChart buckets={consumption.buckets} signals={consumption.signals} mode={widget.config.barMode || 'stacked'} eurKwh={consumption.eur_kwh} {height}></BarChart>
    {:else}
      <div class="hint">Keine Verbrauchsdaten — im Editor Signale zuweisen (⚙)</div>
    {/if}
  {:else if responses.length}
    <UChart series={responses.map(seriesFor)} {height} showTotal></UChart>
  {:else}
    <div class="hint">Keine Signale zugewiesen — im Editor bearbeiten (⚙)</div>
  {/if}
{:else if widget.type === 'charttable'}
  {#if widget.config?.mode === 'bar'}
    <div class="ct">
      {#if consumption && consumption.signals?.length}
        <BarChart buckets={consumption.buckets} signals={consumption.signals} mode={widget.config.barMode || 'stacked'} eurKwh={consumption.eur_kwh} height={height || 180}></BarChart>
        <ConsumptionTable {consumption}></ConsumptionTable>
      {:else}
        <div class="hint">Keine Verbrauchsdaten — im Editor Signale zuweisen (⚙)</div>
      {/if}
    </div>
  {:else}
    <div class="ct">
      <UChart series={responses.map(seriesFor)} height={height || 180} showTotal></UChart>
      <SignalTable {responses} {editable} {onAddSignal} {onRemoveSignal} showColors />
    </div>
  {/if}
{:else if widget.type === 'stat'}
  {#if responses.length}
    {@const r = responses[0]}
    {@const st = r.stats || {}}
    <div class="stat">
      <div class="stat-name">{r.signal.display_name}</div>
      <div class="stat-grid">
        <div class="stat-box">
          <div class="stat-label">Aktuell</div>
          <div class="stat-val">{fmt(st.last)} <span class="unit">{r.signal.engineering_unit}</span></div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Minimum</div>
          <div class="stat-val">{fmt(st.min)} <span class="unit">{r.signal.engineering_unit}</span></div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Maximum</div>
          <div class="stat-val">{fmt(st.max)} <span class="unit">{r.signal.engineering_unit}</span></div>
        </div>
        <div class="stat-box">
          <div class="stat-label">Ø (Zeitraum)</div>
          <div class="stat-val">{fmt(st.avg)} <span class="unit">{r.signal.engineering_unit}</span></div>
        </div>
        {#if st.energy_wh !== null && st.energy_wh !== undefined}
          <div class="stat-box strong">
            <div class="stat-label">Energie (Zeitraum)</div>
            <div class="stat-val">{fmtWh(st.energy_wh)}</div>
          </div>
        {/if}
      </div>
    </div>
  {:else}
    <div class="hint">Keine Signale zugewiesen — im Editor bearbeiten (⚙)</div>
  {/if}
{:else if widget.type === 'usage'}
  <!-- Nutzungsanalyse zeigt nur Kacheln; die Historie lebt im eigenen Widget (usageline) -->
  <UsageView data={usage} variant="stats" thresholds={{ start: widget.config?.startThreshold ?? 10, stop: widget.config?.stopThreshold ?? 5 }}></UsageView>
{:else if widget.type === 'usagestats'}
  <UsageView data={usage} variant="stats" thresholds={{ start: widget.config?.startThreshold ?? 10, stop: widget.config?.stopThreshold ?? 5 }}></UsageView>
{:else if widget.type === 'usageline'}
  <UsageView data={usage} variant="timeline" thresholds={{ start: widget.config?.startThreshold ?? 10, stop: widget.config?.stopThreshold ?? 5 }}></UsageView>
{:else if widget.type === 'table'}
  <SignalTable {responses} {editable} {onAddSignal} {onRemoveSignal} />
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
  .ct {
    display: flex;
    flex-direction: column;
    gap: 10px;
  }
  .stat {
    height: 100%;
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 4px;
  }
  .stat-name {
    color: var(--text-muted);
    font-size: 12px;
  }
  .stat-grid {
    display: flex;
    flex-wrap: wrap;
    gap: 10px;
    flex: 1;
    align-content: flex-start;
  }
  .stat-box {
    background: var(--bg-input);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    min-width: 110px;
  }
  .stat-box.strong {
    border-color: var(--accent);
  }
  .stat-label {
    color: var(--text-muted);
    font-size: 11px;
  }
  .stat-val {
    font-size: 17px;
    font-weight: 600;
    color: var(--text);
  }
  .unit {
    font-size: 12px;
    color: var(--text-muted);
    font-weight: 400;
  }
</style>
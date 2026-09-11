<script>
  import { COLORS } from '../colors.js'

  let { consumption = null } = $props()

  const shortLabel = (comp) => {
    if (!comp) return 'Sensor'
    const parts = comp.split(' - ').filter(Boolean)
    if (parts.length >= 3) return parts.slice(1, -1).join(' - ')
    return comp.replace(/\s*-\s*shellyplugmg3.*$/i, '').replace(/\s*-\s*[a-z0-9]{6,}.*$/i, '').trim() || comp
  }

  // Signale nach Raum gruppiert
  const groups = $derived(() => {
    if (!consumption) return []
    const map = new Map()
    consumption.signals.forEach((s) => {
      const loc = s.location || '(ohne Standort)'
      if (!map.has(loc)) map.set(loc, [])
      map.get(loc).push(s)
    })
    return [...map.entries()].map(([loc, sigs]) => ({
      location: loc,
      kwh: sigs.reduce((a, s) => a + s.kwh, 0),
      cost: sigs.reduce((a, s) => a + s.cost, 0),
      sigs: sigs.slice().sort((a, b) => b.kwh - a.kwh),
    }))
  })
</script>

{#if consumption && consumption.signals?.length}
  {@const totalKwh = consumption.totals?.kwh ?? 0}
  {@const totalCost = consumption.totals?.cost ?? 0}
  <table class="ctbl">
    <thead>
      <tr>
        <th>Verbraucher</th>
        <th class="r">kWh</th>
        <th class="r">Kosten</th>
      </tr>
    </thead>
    <tbody>
      {#each groups() as g}
        <tr class="group">
          <td>🏠 {g.location}</td>
          <td class="r strong">{g.kwh.toFixed(2)}</td>
          <td class="r">{g.cost.toFixed(2)} €</td>
        </tr>
        {#each g.sigs as s, i}
          <tr>
            <td class="sig"><span class="dot" style="background:{COLORS[i % COLORS.length]}"></span>{shortLabel(s.device)}</td>
            <td class="r">{s.kwh.toFixed(2)}</td>
            <td class="r">{s.cost.toFixed(2)} €</td>
          </tr>
        {/each}
      {/each}
      <tr class="total">
        <td>Gesamt</td>
        <td class="r strong">{totalKwh.toFixed(2)}</td>
        <td class="r strong">{totalCost.toFixed(2)} €</td>
      </tr>
    </tbody>
  </table>
  <div class="rate muted small">⌀ {consumption.bucket} · {consumption.eur_kwh.toFixed(3)} €/kWh</div>
{:else}
  <div class="hint">Keine Verbrauchsdaten — im Editor Signale zuweisen (⚙)</div>
{/if}

<style>
  .ctbl { width: 100%; border-collapse: collapse; font-size: 12px; }
  th, td { padding: 4px 8px; text-align: left; color: var(--text); border-bottom: 1px solid var(--border); }
  th { color: var(--text-muted); font-size: 11px; font-weight: 600; }
  .r { text-align: right; }
  .strong { font-weight: 600; color: var(--accent); }
  tr.group td { background: var(--surface-2); font-weight: 600; color: var(--text); border-top: 2px solid var(--border); }
  tr.total td { border-top: 2px solid var(--border); font-weight: 700; color: var(--text); }
  .sig { display: flex; align-items: center; gap: 7px; }
  .dot { width: 8px; height: 8px; border-radius: 2px; flex: none; }
  .hint { color: var(--text-muted); font-size: 13px; padding: 12px 0; }
  .rate { margin-top: 6px; }
</style>
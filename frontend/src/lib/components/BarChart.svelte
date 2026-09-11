<script>
  import { onMount, onDestroy } from 'svelte'
  import { COLORS } from '../colors.js'

  // buckets: [{ t, ts, kwh, cost, partial, by_signal: {id: kWh} }]
  // signals: [{ id, device, location, unit, kwh, cost }] (Meta für Farben/Labels)
  let { buckets = [], signals = [], mode = 'stacked', eurKwh = 0.32, height = 0 } = $props()

  let el = $state(null)
  let W = $state(600)
  let H = $state(220)
  let hoverIdx = $state(-1)
  let ro = null

  const PL = 52, PR = 8, PT = 12, PB = 34

  function shortLabel(comp) {
    if (!comp) return 'Sensor'
    const parts = comp.split(' - ').filter(Boolean)
    if (parts.length >= 3) return parts.slice(1, -1).join(' - ')
    return comp.replace(/\s*-\s*shellyplugmg3.*$/i, '').replace(/\s*-\s*[a-z0-9]{6,}.*$/i, '').trim() || comp
  }

  const series = $derived(signals.map((s, i) => ({
    id: String(s.id),
    label: shortLabel(s.device),
    color: COLORS[i % COLORS.length],
  })))

  const cats = $derived(buckets.map((b) => ({
    label: b.t,
    total: b.kwh,
    cost: b.cost,
    partial: b.partial,
    parts: series.map((s) => ({ kwh: b.by_signal?.[s.id] ?? 0, color: s.color })),
  })))

  const n = $derived(cats.length)
  const plotW = $derived(Math.max(50, W - PL - PR))
  const plotH = $derived(Math.max(30, H - PT - PB))
  const band = $derived(n ? plotW / n : plotW)
  const maxY = $derived(Math.max(0.001, ...cats.map((c) => c.total)) * 1.06)

  // Fertige Balken-Segmente (gestapelt oder nebeneinander)
  const bars = $derived(cats.map((c, i) => {
    if (mode === 'grouped') {
      const m = series.length || 1
      const subW = band / m
      const barW = Math.max(2, subW * 0.7)
      const segs = c.parts.map((p, k) => ({
        x: PL + i * band + k * subW + (subW - barW) / 2,
        y: PT + plotH - (p.kwh / maxY) * plotH,
        w: barW,
        h: (p.kwh / maxY) * plotH,
        kwh: p.kwh,
        color: p.color,
      }))
      return { ...c, x: PL + i * band, barW: Math.max(2, subW * 0.9), segs, cy: PT }
    }
    const barW = band * 0.6
    const x = PL + i * band + (band - barW) / 2
    let yAcc = 0
    const segs = c.parts.map((p) => {
      const segH = (p.kwh / maxY) * plotH
      const seg = { x, y: PT + plotH - yAcc - segH, w: barW, h: segH, kwh: p.kwh, color: p.color }
      yAcc += segH
      return seg
    })
    return { ...c, x, barW, segs, cy: PT + plotH - yAcc }
  }))

  const yTicks = $derived([0, 1, 2, 3, 4].map((t) => ({ v: (maxY * t) / 4, y: PT + plotH - (maxY * t / 4 / maxY) * plotH })))

  function measure() {
    if (!el) return
    const r = el.getBoundingClientRect()
    if (r.width) W = r.width
    if (height > 0) H = height
    else if (r.height) H = r.height
  }

  function onMove(e) {
    if (!el) return
    const rect = el.getBoundingClientRect()
    const mx = e.clientX - rect.left
    const ax = (mx - PL) / band
    hoverIdx = ax >= 0 && ax < n ? Math.min(n - 1, Math.floor(ax)) : -1
  }
  function onLeave() { hoverIdx = -1 }

  onMount(() => {
    measure()
    ro = new ResizeObserver(() => measure())
    if (el) ro.observe(el)
  })
  onDestroy(() => ro?.disconnect())
</script>

<div class="bc" bind:this={el} on:mousemove={onMove} on:mouseleave={onLeave} style="height:{height>0?height+'px':'220px'}">
  {#if n > 0}
    <svg width={W} height={H} style="display:block">
      <!-- Gitter + Y-Achse -->
      {#each yTicks as t}
        <line x1={PL} x2={W - PR} y1={t.y} y2={t.y} stroke="rgba(51,65,85,0.5)" stroke-width="1" />
        <text x={PL - 8} y={t.y + 4} text-anchor="end" fill="#64748b" font-size="10">{t.v.toFixed(t.v < 1 ? 2 : t.v < 10 ? 1 : 0)}</text>
      {/each}
      <!-- Balken -->
      {#each bars as bar, i}
        {#each bar.segs as s}
          <rect x={s.x} y={s.y} width={s.w} height={Math.max(0, s.h)} rx="1" fill={s.color} opacity={hoverIdx === -1 || hoverIdx === i ? 1 : 0.35} />
        {/each}
        <!-- Gesamt-Wert oben (gestapelt) -->
        {#if mode !== 'grouped'}
          <text x={bar.x + bar.barW / 2} y={bar.cy - 5} text-anchor="middle" fill="#cbd5e1" font-size="10">
            {(bar.total > 0) ? bar.total.toFixed(1) : ''}
          </text>
        {/if}
        <!-- Hover-Markierung -->
        {#if hoverIdx === i}
          <rect x={bar.x} y={PT - 6} width={Math.max(bar.barW, 3)} height={plotH + 8} fill="rgba(255,255,255,0.05)" />
        {/if}
      {/each}
      <!-- X-Labels -->
      {#each bars as bar, i}
        {#if n <= 10 || i % 2 === 0}
          <text x={PL + i * band + band / 2} y={H - 10} text-anchor="middle" fill="#64748b" font-size="10"
            transform={n > 7 ? `rotate(-32 ${PL + i * band + band / 2} ${H - 10})` : ''}>
            {bar.label}
          </text>
        {/if}
      {/each}
    </svg>

    {#if hoverIdx >= 0}
      {@const c = cats[hoverIdx]}
      <div class="tt" style="left:{Math.min(PL + hoverIdx * band + band / 2, W - 180)}px; top:6px">
        <div class="tt-head">{c.label}{c.partial ? ' · teilweise' : ''}</div>
        <div class="tt-row strong"><span>Gesamt</span><span>{c.total.toFixed(2)} kWh</span></div>
        <div class="tt-row muted">Kosten</div>
        <div class="tt-row"><span>—</span><span>{c.cost.toFixed(2)} €</span></div>
        {#each c.parts as p, i}
          {#if p.kwh > 0}
            <div class="tt-row">
              <span class="lab"><span class="dot" style="background:{p.color}"></span>{series[i].label}</span>
              <span>{p.kwh.toFixed(2)} kWh</span>
            </div>
          {/if}
        {/each}
      </div>
    {/if}
  {:else}
    <div class="empty">Keine Verbrauchsdaten — im Editor Signale zuweisen (⚙)</div>
  {/if}
</div>

<style>
  .bc { position: relative; width: 100%; overflow: hidden; }
  .tt {
    position: absolute;
    pointer-events: none;
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 8px 10px;
    font-size: 12px;
    min-width: 150px;
    z-index: 5;
  }
  .tt-head { font-weight: 600; color: var(--text); margin-bottom: 4px; }
  .tt-row { display: flex; justify-content: space-between; gap: 18px; color: var(--text); }
  .tt-row.strong { font-weight: 600; color: var(--accent); }
  .tt-row.muted { color: var(--text-muted); justify-content: flex-start; }
  .lab { display: flex; align-items: center; gap: 6px; }
  .dot { width: 8px; height: 8px; border-radius: 2px; }
  .empty { display: flex; align-items: center; justify-content: center; height: 100%; color: var(--text-muted); font-size: 13px; }
</style>
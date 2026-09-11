<script>
  import { onMount, onDestroy } from 'svelte'
  import uPlot from 'uplot'
  import 'uplot/dist/uPlot.min.css'
  import { COLORS } from '../colors.js'

  let { series = [], height = 0, showTotal = false } = $props()
  // series: [{ label, unit, color, xs: [ms], ys: [num] }] — height 0 = automatisch

  let el = $state(null)
  let plot = null
  let observer = null
  let tooltip = null
  let activeSeries = []
  let errorMsg = $state('')

  const AXIS = '#64748b'
  const GRID = 'rgba(51, 65, 85, 0.5)'

  // Lineare Interpolation für die Gesamt-Summe auf gemeinsamer Zeitachse
  function interp(xs, ys, x) {
    let lo = 0
    let hi = xs.length - 1
    if (hi < 0) return null
    if (x <= xs[lo]) return ys[lo]
    if (x >= xs[hi]) return ys[hi]
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1
      if (xs[mid] <= x) lo = mid
      else hi = mid
    }
    const t = (x - xs[lo]) / (xs[hi] - xs[lo] || 1)
    return ys[lo] + (ys[hi] - ys[lo]) * t
  }

  function computeTotal(allX, active) {
    const cols = active.map((s) => allX.map((x) => interp(s.xs, s.ys, x)))
    return allX.map((_, i) => {
      let sum = 0
      let has = false
      for (const c of cols) {
        const v = c[i]
        if (v != null) {
          sum += v
          has = true
        }
      }
      return has ? sum : null
    })
  }

  function build() {
    destroy()
    const active = (series || []).filter((s) => s.xs && s.xs.length)
    if (!el || !active.length) return
    activeSeries = active
    try {
      // Gemeinsame X-Achse = Vereinigung aller Timestamps, null-Lücken, spanGaps
      const tsSet = new Set()
      for (const s of active) for (const x of s.xs) tsSet.add(x)
      const allX = Array.from(tsSet).sort((a, b) => a - b)
      const idx = new Map(allX.map((x, i) => [x, i]))
      const ysCols = active.map((s) => {
        const col = new Array(allX.length).fill(null)
        for (let i = 0; i < s.xs.length; i++) col[idx.get(s.xs[i])] = s.ys[i]
        return col
      })
      const columns = [allX.map((x) => x / 1000), ...ysCols]
      let tooltipSeries = active
      if (showTotal && active.length > 1) {
        const tot = computeTotal(allX, active)
        columns.push(tot)
        tooltipSeries = [
          ...active,
          { label: 'Gesamt', unit: active[0]?.unit || '', color: '#e2e8f0', xs: allX, ys: tot },
        ]
      }
      activeSeries = tooltipSeries
      const w0 = el.clientWidth || 800
      const opts = {
        width: w0,
        height: height > 0 ? height : el.clientHeight || 260,
        legend: { show: false },
        plugins: [{ hooks: { setCursor: onCursor } }],
        cursor: { show: true, x: true, y: true, drag: { x: true, y: false, uni: 50 } },
        scales: { x: { time: true } },
        axes: [
          { stroke: AXIS, grid: { stroke: GRID }, ticks: { stroke: AXIS, size: 4 } },
          { stroke: AXIS, grid: { stroke: GRID }, size: 60, ticks: { stroke: AXIS, size: 4 } },
        ],
        series: [
          { label: 'Zeit' },
          ...tooltipSeries.map((s, i) => ({
            label: s.label,
            stroke: s.color || COLORS[i % COLORS.length],
            width: s.label === 'Gesamt' ? 2.6 : 1.6,
            points: { show: false },
            spanGaps: true,
          })),
        ],
      }
      plot = new uPlot(opts, columns, el)
      errorMsg = ''
      // Layout-Settling abwarten und Größe korrigieren (sonst 0-Breite bei
      // Daten-Wechsel, weil der Browser noch nicht neu geflowt hat)
      requestAnimationFrame(() => {
        requestAnimationFrame(() => {
          if (plot && el) {
            const w = el.clientWidth
            if (w) {
              const h = height > 0 ? height : el.clientHeight || 260
              plot.setSize({ width: w, height: h })
            }
          }
        })
      })
    } catch (e) {
      errorMsg = String(e?.stack || e?.message || e)
      console.error('UChart Fehler:', e)
    }
  }

  function onCursor(u) {
    if (!tooltip) return
    const i = u.cursor?.idx
    if (i == null) {
      tooltip.style.display = 'none'
      return
    }
    const t = u.data[0]?.[i]
    const d = t != null ? new Date(t * 1000) : null
    const time = d
      ? `${d.toLocaleDateString('de-DE')} ${d.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' })}`
      : ''
    let html = ''
    if (time) html += `<div class="tt-time">${time}</div>`
    for (let s = 0; s < activeSeries.length; s++) {
      const v = u.data[s + 1]?.[i]
      if (v == null) continue
      const col = activeSeries[s].color || COLORS[s % COLORS.length]
      const unit = activeSeries[s].unit || ''
      html += `<div class="tt-row"><span class="tt-dot" style="background:${col}"></span><span class="tt-label">${activeSeries[s].label}</span><span class="tt-val">${Number(v).toFixed(1)} ${unit}</span></div>`
    }
    tooltip.innerHTML = html || '<div class="tt-row">—</div>'
    tooltip.style.display = 'block'
    const left = u.cursor?.left ?? 0
    const top = u.cursor?.top ?? 0
    tooltip.style.left = `${Math.min(left + 14, (el?.clientWidth || 300) - 180)}px`
    tooltip.style.top = `${top + 14}px`
  }

  function destroy() {
    if (plot) {
      try {
        plot.destroy()
      } catch (e) {
        /* ignore */
      }
      plot = null
    }
    activeSeries = []
  }

  $effect(() => {
    const s = series
    const h = height
    if (el) build()
  })

  onMount(() => {
    if (el) {
      tooltip = document.createElement('div')
      tooltip.className = 'tt'
      tooltip.style.display = 'none'
      el.appendChild(tooltip)
      el.addEventListener('mouseleave', () => {
        if (tooltip) tooltip.style.display = 'none'
      })
      observer = new ResizeObserver(() => {
        if (plot && el) {
          plot.setSize({ width: el.clientWidth, height: el.clientHeight || 260 })
        }
      })
      observer.observe(el)
    }
  })

  onDestroy(() => {
    if (observer) observer.disconnect()
    destroy()
  })
</script>

<div class="uchart" bind:this={el} style="height:{height > 0 ? height + 'px' : '100%'}">
  {#if errorMsg}
    <div class="err-box">uChart-Fehler: {errorMsg}</div>
  {:else if !(series || []).some((s) => s.xs && s.xs.length)}
    <div class="empty">Keine Daten im gewählten Zeitraum</div>
  {/if}
</div>

<style>
  .uchart {
    width: 100%;
    position: relative;
  }
  .err-box {
    color: #f88;
    font: 11px monospace;
    white-space: pre-wrap;
    background: #111;
    border: 1px solid #f00;
    border-radius: 6px;
    padding: 8px;
  }
  .empty {
    width: 100%;
    height: 100%;
    display: flex;
    align-items: center;
    justify-content: center;
    color: var(--text-muted);
    font-size: 13px;
  }
  :global(.tt) {
    position: absolute;
    z-index: 10;
    pointer-events: none;
    background: rgba(2, 6, 23, 0.95);
    border: 1px solid var(--border-strong);
    border-radius: 8px;
    padding: 6px 9px;
    font-size: 11px;
    color: var(--text);
    box-shadow: 0 4px 14px rgba(0, 0, 0, 0.5);
    max-width: 260px;
  }
  :global(.tt-time) {
    color: var(--text-muted);
    margin-bottom: 4px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 3px;
  }
  :global(.tt-row) {
    display: flex;
    align-items: center;
    gap: 6px;
    white-space: nowrap;
  }
  :global(.tt-dot) {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    flex: none;
  }
  :global(.tt-label) {
    color: var(--text-muted);
  }
  :global(.tt-val) {
    margin-left: auto;
    font-weight: 600;
  }
</style>
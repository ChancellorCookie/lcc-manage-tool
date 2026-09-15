<script>
  // Nutzungsanalyse-Widget: Kacheln (Dauer / Auslastung) + Aktivitäts-Timeline.
  let { data = null, thresholds = null } = $props()

  const fmtDur = (s) => {
    s = Math.max(0, Math.round(s || 0))
    const h = Math.floor(s / 3600)
    const m = Math.floor((s % 3600) / 60)
    if (h >= 1) return `${h} h ${String(m).padStart(2, '0')} min`
    if (m >= 1) return `${m} min`
    return `${s} s`
  }
  const dateDE = (ms) => new Date(ms).toLocaleDateString('de-DE', { day: '2-digit', month: '2-digit' })
  const dowDE = (ms) => new Date(ms).toLocaleDateString('de-DE', { weekday: 'short' })
  const dayStart = (ms) => { const d = new Date(ms); return new Date(d.getFullYear(), d.getMonth(), d.getDate()).getTime() }

  const rows = $derived.by(() => {
    if (!data?.window || !data?.intervals?.length) return []
    const { start, end } = data.window
    const ds = dayStart(start)
    const days = []
    for (let t = ds; t <= dayStart(end); t += 86400000) days.push(t)
    const out = days.map((d) => ({ ds: d, segs: [] }))
    for (const iv of data.intervals) {
      for (let i = 0; i < out.length; i++) {
        const { ds } = out[i]
        const dayEnd = ds + 86400000
        const s = Math.max(iv.start, ds)
        const e = Math.min(iv.end, dayEnd)
        if (e > s) out[i].segs.push({ x: (s - ds) / 86400000, w: (e - s) / 86400000, full: true })
      }
    }
    return out
  })

  const W = 1000
  const ROW = 26
  const LABEL = 40
  const H = rows.length ? rows.length * ROW + LABEL : 120
  const HOURS = [0, 6, 12, 18, 24]
  const ACCENT = '#eab308'
</script>

{#if data && data.stats}
  {@const st = data.stats}
  {@const signals = data.signals || []}
  <div class="uvw">
    <!-- Kacheln -->
    <div class="uv-stats">
      <div class="uv-box strong">
        <div class="uv-label">Nutzungsdauer</div>
        <div class="uv-big">{fmtDur(st.active_s)}</div>
      </div>
      <div class="uv-box">
        <div class="uv-label">Auslastung</div>
        <div class="uv-big">{st.pct.toFixed?.(1) ?? st.pct} % <span class="uv-sub">der Online-Zeit</span></div>
      </div>
      <div class="uv-box">
        <div class="uv-label">Aktuell</div>
        <div class="uv-state {st.current_active ? 'on' : 'off'}">
          <span class="uv-dot"></span>{st.current_active ? 'In Nutzung' : 'Ruhend'}
        </div>
        <div class="uv-sub">{st.current_w} W (Summe)</div>
      </div>
      <div class="uv-box">
        <div class="uv-label">Nutzungen</div>
        <div class="uv-big">{st.count}<span class="uv-sub"> {st.count === 1 ? 'Vorgang' : 'Vorgänge'}</span></div>
        <div class="uv-sub">Ø {fmtDur(st.avg_s)}</div>
      </div>
    </div>

    {#if thresholds}
      <div class="uv-thresh">Schwellen: Start ≥ {thresholds.start} W · Stop ≤ {thresholds.stop} W</div>
    {/if}
    {#if signals.length}
      <div class="uv-sigs">
        {#each signals as s}<span class="uv-chip">{s.device} — {s.browse_name}</span>{/each}
      </div>
    {/if}

    <!-- Timeline -->
    <div class="uv-tl">
      {#if rows.length}
        <svg viewBox="0 0 {W} {H}" width="100%">
          {#each rows as r, ri}
            <!-- Zeilen-Hintergrund -->
            <rect x="0" y={ri * ROW} width={W} height={ROW} fill="var(--surface)" stroke="var(--border)"></rect>
            {#each HOURS as h}
              <line x1={h / 24 * W} y1={ri * ROW} x2={h / 24 * W} y2={ri * ROW + ROW} stroke="var(--border)" stroke-width="1"></line>
            {/each}
            <!-- Datum -->
            <text x="2" y={ri * ROW + ROW - 8} font-size="10" fill="var(--text-muted)">{dowDE(r.ds)} {dateDE(r.ds)}</text>
            <!-- aktive Segmente -->
            {#each r.segs as seg}
              <title>{fmtDur(seg.w * 86400)} genutzt</title>
              <rect x={seg.x * W} y={ri * ROW + 3} width={Math.max(seg.w * W, 2)} height={ROW - 6} rx="3" fill="{ACCENT}" opacity="0.9"></rect>
            {/each}
          {/each}
          <!-- Stundenskala -->
          <line x1="0" y1={rows.length * ROW} x2="0" y2={H} stroke="var(--border)"></line>
          <line x1={W} y1={rows.length * ROW} x2={W} y2={H} stroke="var(--border)"></line>
          {#each HOURS as h}
            <text x={h / 24 * W} y={H - 8} font-size="10" fill="var(--text-muted)" text-anchor="middle">{h} Uhr</text>
          {/each}
        </svg>
      {:else}
        <div class="hint">Keine Nutzungsphasen im Zeitraum — Werte bleiben unter der Startschwelle.</div>
      {/if}
    </div>
  </div>
{:else}
  <div class="hint">Keine Signale zugewiesen — im Editor bearbeiten (⚙)</div>
{/if}

<style>
  .uvw { display: flex; flex-direction: column; gap: 12px; }
  .uv-stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 10px; }
  .uv-box {
    border: 1px solid var(--border); border-radius: 10px; padding: 10px 12px;
    display: flex; flex-direction: column; gap: 2px;
    background: var(--surface);
  }
  .uv-box.strong { border-color: var(--border-strong); }
  .uv-label { font-size: 11px; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em; }
  .uv-big { font-size: 20px; font-weight: 700; line-height: 1.15; }
  .uv-sub { font-size: 11px; font-weight: 400; color: var(--text-muted); }
  .uv-state { display: inline-flex; align-items: center; gap: 6px; font-weight: 600; font-size: 14px; }
  .uv-state.on { color: var(--success); }
  .uv-state.off { color: var(--text-muted); }
  .uv-dot { width: 9px; height: 9px; border-radius: 50%; }
  .uv-state.on .uv-dot { background: var(--success); box-shadow: 0 0 0 3px color-mix(in srgb, var(--success) 25%, transparent); }
  .uv-state.off .uv-dot { background: var(--text-muted); }
  .uv-thresh { font-size: 12px; color: var(--text-muted); }
  .uv-sigs { display: flex; flex-wrap: wrap; gap: 6px; }
  .uv-chip { font-size: 11px; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); color: var(--text-muted); }
  .uv-tl { margin-top: 2px; }
</style>
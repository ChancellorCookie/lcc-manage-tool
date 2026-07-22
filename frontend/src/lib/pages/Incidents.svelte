<script>
  import { api } from '../api.js'
  import { onMount, onDestroy } from 'svelte'
  import Icon from '../Icon.svelte'

  let { initialTab = 'incidents' } = $props()

  // ── Tab state ──────────────────────────────────────────────────
  let tab = $state(initialTab)

  // ── Incidents ──────────────────────────────────────────────────
  let incidents = $state([])
  let incLoading = $state(true)
  let incError = $state('')
  let filterSeverity = $state('')
  let filterRoom = $state('')
  let filterStatus = $state('')
  let selectedIncident = $state(null)
  let pollTimer = $state(null)

  const sevColors = {
    error: 'bg-red-500/20 text-red-400',
    alert: 'bg-orange-500/20 text-orange-400',
    warning: 'bg-yellow-500/20 text-yellow-400',
    info: 'bg-blue-500/20 text-blue-400',
    notice: 'bg-slate-500/20 text-slate-400',
  }
  const sevBadge = (s) => sevColors[s?.toLowerCase()] || 'bg-slate-500/20 text-slate-400'
  const stColors = { NEW:'text-yellow-400', ACKNOWLEDGED:'text-blue-400', CONFIRMED:'text-green-400', REPORTED:'text-purple-400' }

  let filteredIncidents = $derived(
    incidents.filter(inc => {
      if (filterSeverity && inc.severity?.toLowerCase() !== filterSeverity) return false
      if (filterRoom && !(inc.room_name||'').toLowerCase().includes(filterRoom.toLowerCase()) &&
          !(inc.room_number||'').toLowerCase().includes(filterRoom.toLowerCase())) return false
      if (filterStatus && inc.status !== filterStatus) return false
      return true
    })
  )

  async function fetchIncidents() {
    try {
      const data = await api.notifier.incidents()
      incidents = data.incidents || []
      incError = data.error || ''
    } catch (e) { incError = e.message }
    incLoading = false
  }

  function deviceName(src) { const m = src?.match(/DeviceSet\/([^/]+)/); return m ? m[1] : src || '-' }
  function formatTs(ts) { if (!ts) return '-'; try { return new Date(ts).toLocaleString('de-DE') } catch { return ts } }

  // ── Templates ──────────────────────────────────────────────────
  let templates = $state({})
  let defaults = $state({})
  let placeholderGroups = $state([])
  let placeholderHelp = $state({})
  let sampleValues = $state({})
  let tplLoading = $state(true)
  let tplSaved = $state(false)
  let tplError = $state('')
  let previewType = $state('alert')

  let editSubject = $state('')
  let editBody = $state('')
  let editResSubject = $state('')
  let editResBody = $state('')
  let showPlaceholders = $state(false)

  async function loadTemplates() {
    try {
      const d = await api.notifier.templates()
      templates = d.templates || {}
      defaults = d.defaults || {}
      placeholderGroups = d.placeholder_groups || []
      placeholderHelp = d.placeholder_help || {}
      sampleValues = d.sample_values || {}
      // Use templates if set, otherwise pre-fill with defaults as editable text
      editSubject = templates.alert_subject || defaults.alert_subject || ''
      editBody = templates.alert_body || defaults.alert_body || ''
      editResSubject = templates.resolved_subject || defaults.resolved_subject || ''
      editResBody = templates.resolved_body || defaults.resolved_body || ''
    } catch (e) { tplError = e.message }
    tplLoading = false
  }

  async function saveTemplates() {
    tplSaved = false; tplError = ''
    try {
      const r = await api.notifier.saveTemplates({ alert_subject:editSubject, alert_body:editBody, resolved_subject:editResSubject, resolved_body:editResBody })
      templates = r.templates; tplSaved = true
      setTimeout(() => tplSaved = false, 3000)
    } catch (e) { tplError = e.message }
  }

  function insertPH(field, ph) {
    const key = `{${ph}}`
    if (field === 's') editSubject += key
    else if (field === 'b') editBody += key
    else if (field === 'rs') editResSubject += key
    else if (field === 'rb') editResBody += key
  }

  function phLabel(text, def) { return text?.trim() || def }
  let previewAlertSubject = $derived(phLabel(editSubject, defaults.alert_subject).replace(/\{(\w+)\}/g, (_,k) => sampleValues[k] ?? `{${k}}`))
  let previewAlertBody = $derived(phLabel(editBody, defaults.alert_body).replace(/\{(\w+)\}/g, (_,k) => sampleValues[k] ?? `{${k}}`))
  let previewResSubject = $derived(phLabel(editResSubject, defaults.resolved_subject).replace(/\{(\w+)\}/g, (_,k) => sampleValues[k] ?? `{${k}}`))
  let previewResBody = $derived(phLabel(editResBody, defaults.resolved_body).replace(/\{(\w+)\}/g, (_,k) => sampleValues[k] ?? `{${k}}`))

  // ── Settings ───────────────────────────────────────────────────
  let config = $state(null)
  let cfgLoading = $state(true)
  let cfgSaved = $state(false)
  let cfgError = $state('')

  // Editable fields
  let pollUrl = $state('')
  let pollInterval = $state(30)
  let pollTimeout = $state(10)
  let pollVerifyTls = $state(false)
  let pollSeverities = $state('')

  // Auth
  let authType = $state('oauth2')
  let authTokenUrl = $state('')
  let authClientId = $state('')
  let authClientSecret = $state('')
  let authScope = $state('')

  // Escalation
  let digestInterval = $state(60)
  let immediateSeverities = $state('')
  let notifyResolved = $state(false)
  let stateDbPath = $state('')

  // Channel management
  let showAddChannel = $state(false)
  let newChannelName = $state('')
  let newChannelType = $state('email')
  let editingChannel = $state(null)  // name of channel being edited, null = none

  let channelNames = $derived(Object.keys(config?.channels || {}))

  const channelTypes = [
    { value: 'email', label: 'Email', fields: ['smtp_host','smtp_port','use_ssl','use_starttls','username','password','from_addr','to_addrs'] },
    { value: 'eln', label: 'ELN', fields: ['base_url','verify_tls','timeout_seconds','notification_type','recipient_user_id','recipient_user_ids','recipient_role','auth_type','auth_token','auth_self_endpoint'] },
    { value: 'whatsapp_twilio', label: 'WhatsApp (Twilio)', fields: ['account_sid','auth_token','from_number','to_numbers','content_sid'] },
    { value: 'whatsapp_meta', label: 'WhatsApp (Meta)', fields: ['api_version','phone_number_id','access_token','to_numbers','template_name','template_language'] },
  ]

  async function loadConfig() {
    try {
      config = await api.notifier.config()
      pollUrl = config?.poll?.url || ''
      pollInterval = config?.poll?.interval_seconds || 30
      pollTimeout = config?.poll?.timeout_seconds || 10
      pollVerifyTls = config?.poll?.verify_tls === true || config?.poll?.verify_tls === 'true'
      pollSeverities = (config?.poll?.severities || []).join(', ')
      const auth = config?.poll?.auth || {}
      authType = auth.type || 'oauth2'
      authTokenUrl = auth.token_url || ''
      authClientId = auth.client_id || ''
      authClientSecret = auth.client_secret || ''
      authScope = auth.scope || ''
      digestInterval = config?.escalation?.digest_interval_minutes || 60
      immediateSeverities = (config?.escalation?.immediate || []).join(', ')
      notifyResolved = config?.escalation?.notify_on_resolved || false
      stateDbPath = config?.state?.db_path || ''
    } catch (e) { cfgError = e.message }
    cfgLoading = false
  }

  async function saveConfig() {
    cfgSaved = false; cfgError = ''
    const body = JSON.parse(JSON.stringify(config))
    body.poll.url = pollUrl
    body.poll.interval_seconds = pollInterval
    body.poll.timeout_seconds = pollTimeout
    body.poll.verify_tls = pollVerifyTls
    body.poll.severities = pollSeverities.split(',').map(s => s.trim()).filter(Boolean)
    body.poll.auth = body.poll.auth || {}
    body.poll.auth.type = authType
    body.poll.auth.token_url = authTokenUrl
    body.poll.auth.client_id = authClientId
    body.poll.auth.client_secret = authClientSecret
    body.poll.auth.scope = authScope
    body.escalation.digest_interval_minutes = digestInterval
    body.escalation.immediate = immediateSeverities.split(',').map(s => s.trim()).filter(Boolean)
    body.escalation.notify_on_resolved = notifyResolved
    body.state.db_path = stateDbPath
    try {
      await api.notifier.saveConfig(body)
      config = body
      cfgSaved = true
      setTimeout(() => cfgSaved = false, 3000)
    } catch (e) { cfgError = e.message }
  }

  // Channel management
  function addChannel() {
    if (!newChannelName.trim()) return
    const cfg = JSON.parse(JSON.stringify(config))
    cfg.channels = cfg.channels || {}
    const defaults = {
      email: { smtp_host:'',smtp_port:587,use_ssl:false,use_starttls:true,username:'',password:'',from_addr:'',to_addrs:[] },
      eln: { base_url:'',verify_tls:true,timeout_seconds:10,notification_type:'lcc_alarm',auth:{type:'api_key',token:'',self_endpoint:'/v1/health'} },
      whatsapp_twilio: { account_sid:'',auth_token:'',from_number:'',to_numbers:[],content_sid:'' },
      whatsapp_meta: { api_version:'v21.0',phone_number_id:'',access_token:'',to_numbers:[],template_name:'',template_language:'de' },
    }
    cfg.channels[newChannelName.trim()] = { type: newChannelType, ...(defaults[newChannelType] || {}) }
    config = cfg
    newChannelName = ''
    newChannelType = 'email'
    showAddChannel = false
  }

  function deleteChannel(name) {
    const cfg = JSON.parse(JSON.stringify(config))
    delete cfg.channels[name]
    config = cfg
  }

  function updateChannelField(name, field, value) {
    const cfg = JSON.parse(JSON.stringify(config))
    if (!cfg.channels[name]) return
    if (field.includes('.')) {
      const [parent, child] = field.split('.')
      cfg.channels[name][parent] = cfg.channels[name][parent] || {}
      cfg.channels[name][parent][child] = value
    } else if (field === 'to_addrs' || field === 'to_numbers' || field === 'recipient_user_ids') {
      cfg.channels[name][field] = value.split(',').map(s => s.trim()).filter(Boolean)
    } else if (field === 'smtp_port' || field === 'timeout_seconds') {
      cfg.channels[name][field] = parseInt(value) || 0
    } else if (field === 'use_ssl' || field === 'use_starttls' || field === 'verify_tls') {
      cfg.channels[name][field] = value === true || value === 'true'
    } else {
      cfg.channels[name][field] = value
    }
    config = cfg
  }

  // ── Lifecycle ──────────────────────────────────────────────────
  let notifierLoading = $state(true)
  let historyItems = $state([])

  async function loadHistory() {
    try {
      const data = await api.notifier.status()
      historyItems = data.recent || []
    } catch { /* ignore */ }
    notifierLoading = false
  }

  onMount(() => {
    fetchIncidents()
    loadTemplates()
    loadConfig()
    loadHistory()
    pollTimer = setInterval(fetchIncidents, 30_000)
  })
  onDestroy(() => { if (pollTimer) clearInterval(pollTimer) })
</script>

<div>
  <h2 class="text-xl font-bold mb-1 flex items-center gap-2"><Icon name="incidents" size={22} /> Incidents</h2>
  <p class="text-sm text-slate-500 mb-4">Monitoring, Templates und Einstellungen für den Incident-Benachrichtigungsdienst</p>

  <!-- Tabs -->
  <div class="flex gap-1 mb-6 border-b border-slate-800">
    {#each [
      { id: 'incidents', label: 'Incidents', icon: 'incidents' },
      { id: 'templates', label: 'Templates', icon: 'notifier' },
      { id: 'settings', label: 'Einstellungen', icon: 'dashboard' },
      { id: 'history', label: 'Verlauf', icon: 'gateways' },
    ] as t}
      <button
        class="flex items-center gap-2 px-4 py-2.5 text-sm rounded-t-lg transition-colors {tab === t.id ? 'bg-slate-800 text-slate-200' : 'text-slate-500 hover:text-slate-300'}"
        onclick={() => tab = t.id}
      >
        <Icon name={t.icon} size={16} />
        {t.label}
      </button>
    {/each}
  </div>

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- INCIDENTS TAB -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  {#if tab === 'incidents'}
    <!-- Filters -->
    <div class="flex flex-wrap items-end gap-3 mb-4">
      <div><label class="mb-1 text-xs text-slate-500">Severity</label><select bind:value={filterSeverity} class="!w-auto"><option value="">Alle</option><option value="error">Error</option><option value="alert">Alert</option><option value="warning">Warning</option><option value="info">Info</option></select></div>
      <div><label class="mb-1 text-xs text-slate-500">Raum</label><input type="text" placeholder="Filtern…" bind:value={filterRoom} class="!w-40" /></div>
      <div><label class="mb-1 text-xs text-slate-500">Status</label><select bind:value={filterStatus} class="!w-auto"><option value="">Alle</option><option value="NEW">New</option><option value="ACKNOWLEDGED">Acknowledged</option><option value="CONFIRMED">Confirmed</option><option value="REPORTED">Reported</option></select></div>
      <div class="ml-auto text-xs text-slate-500 self-end pb-1">{filteredIncidents.length} von {incidents.length}</div>
    </div>

    {#if incLoading}
      <div class="card animate-pulse h-48"></div>
    {:else if incError}
      <div class="card border-red-500/20 text-red-400 text-sm">⚠ {incError}<button class="btn btn-ghost ml-4 text-xs" onclick={fetchIncidents}>Neu laden</button></div>
    {:else if filteredIncidents.length === 0}
      <div class="card text-center text-slate-500 py-12">{incidents.length === 0 ? '✅ Keine offenen Incidents' : 'Keine Treffer'}</div>
    {:else}
      <div class="card overflow-x-auto p-0">
        <table class="table-glass">
          <thead><tr><th>Severity</th><th>Titel</th><th>Gerät</th><th>Raum</th><th>Status</th><th>Zeit</th><th></th></tr></thead>
          <tbody>
            {#each filteredIncidents as inc}
              <tr class="cursor-pointer" onclick={() => selectedIncident = inc}>
                <td><span class="badge {sevBadge(inc.severity)}">{inc.severity||'?'}</span></td>
                <td class="max-w-xs truncate" title={inc.title}>{inc.title?.slice(0,50)||'-'}</td>
                <td class="font-mono text-xs text-slate-400">{deviceName(inc.source)}</td>
                <td class="text-slate-400 text-sm">{inc.room_name||inc.room_number||'-'}</td>
                <td><span class="text-xs {stColors[inc.status]||'text-slate-400'}">{inc.status}</span></td>
                <td class="text-xs text-slate-500">{formatTs(inc.timestamp)}</td>
                <td><button class="btn btn-ghost text-xs py-1 px-2" onclick={(e)=>{e.stopPropagation();selectedIncident=inc}}>Details</button></td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    {/if}

    <div class="mt-3 text-right"><button class="btn btn-ghost text-xs" onclick={fetchIncidents}>🔄 Aktualisieren</button></div>
  {/if}

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- TEMPLATES TAB -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  {#if tab === 'templates'}
    {#if tplLoading}
      <div class="card animate-pulse h-96"></div>
    {:else}
      <div class="space-y-6">
        <!-- Template Card -->
        <div class="card">
          <div class="flex items-center gap-3 mb-4">
            <h3 class="font-semibold flex items-center gap-2"><Icon name="incidents" size={18} />
              {previewType === 'alert' ? 'Alert (sofort)' : 'Entwarnung (Resolved)'}
            </h3>
            <select bind:value={previewType} class="!w-auto text-xs ml-auto">
              <option value="alert">🚨 Alert</option>
              <option value="resolved">✅ Entwarnung</option>
            </select>
          </div>

          <div class="grid grid-cols-1 lg:grid-cols-5 gap-6">
            <!-- Editor -->
            <div class="lg:col-span-3 space-y-4">
              {#if previewType === 'alert'}
                <div>
                  <label class="text-xs text-slate-500 mb-1">Betreff</label>
                  <textarea rows="2" class="font-mono text-xs" bind:value={editSubject}></textarea>
                </div>
                <div>
                  <label class="text-xs text-slate-500 mb-1">Body</label>
                  <textarea rows="12" class="font-mono text-xs" bind:value={editBody}></textarea>
                </div>
              {:else}
                <div>
                  <label class="text-xs text-slate-500 mb-1">Betreff</label>
                  <textarea rows="2" class="font-mono text-xs" bind:value={editResSubject}></textarea>
                </div>
                <div>
                  <label class="text-xs text-slate-500 mb-1">Body</label>
                  <textarea rows="12" class="font-mono text-xs" bind:value={editResBody}></textarea>
                </div>
              {/if}
            </div>

            <!-- Preview -->
            <div class="lg:col-span-2 space-y-3">
              <div class="text-xs text-slate-500 uppercase tracking-wide">Live-Vorschau</div>
              {#if previewType === 'alert'}
                <div class="p-3 rounded bg-slate-900 border border-slate-800">
                  <div class="text-xs text-slate-500 mb-1">Betreff</div>
                  <div class="text-sm font-semibold text-slate-200">{previewAlertSubject}</div>
                </div>
                <div class="p-3 rounded bg-slate-900 border border-slate-800">
                  <div class="text-xs text-slate-500 mb-1">Body</div>
                  <pre class="text-xs text-slate-300 whitespace-pre-wrap font-sans">{previewAlertBody}</pre>
                </div>
              {:else}
                <div class="p-3 rounded bg-slate-900 border border-slate-800">
                  <div class="text-xs text-slate-500 mb-1">Betreff</div>
                  <div class="text-sm font-semibold text-slate-200">{previewResSubject}</div>
                </div>
                <div class="p-3 rounded bg-slate-900 border border-slate-800">
                  <div class="text-xs text-slate-500 mb-1">Body</div>
                  <pre class="text-xs text-slate-300 whitespace-pre-wrap font-sans">{previewResBody}</pre>
                </div>
              {/if}
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-3 items-center mt-4 pt-4 border-t border-slate-800">
            <button class="btn btn-primary text-sm" onclick={saveTemplates}>💾 Speichern</button>
            <button class="btn btn-ghost text-sm" onclick={()=>{editSubject='';editBody='';editResSubject='';editResBody=''}}>↺ Defaults</button>
            {#if tplSaved}<span class="text-xs text-green-400">✓ Gespeichert!</span>{/if}
            {#if tplError}<span class="text-xs text-red-400">⚠ {tplError}</span>{/if}
          </div>
        </div>

        <!-- Placeholder Picker -->
        <div class="card">
          <button class="w-full text-left text-sm font-semibold flex items-center gap-2" onclick={() => showPlaceholders = !showPlaceholders}>
            📋 Platzhalter {showPlaceholders ? '▲' : '▼'}
          </button>
          {#if showPlaceholders}
            <div class="mt-2 flex flex-wrap gap-1.5">
              {#each placeholderGroups as [group, placeholders]}
                {#each placeholders as ph}
                  <button
                    class="text-xs px-2 py-1 rounded bg-slate-800 hover:bg-blue-500/20 hover:text-blue-300 text-slate-400 border border-slate-700 hover:border-blue-500/50 transition-colors font-mono"
                    title="{placeholderHelp[ph] || ''}"
                    onclick={() => {
                      if (previewType === 'alert') editBody += `{${ph}}`
                      else editResBody += `{${ph}}`
                    }}
                  >
                    {'{' + ph + '}'}
                  </button>
                {/each}
              {/each}
            </div>
          {/if}
        </div>
      </div>
    {/if}
  {/if}

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- SETTINGS TAB -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  {#if tab === 'settings'}
    {#if cfgLoading}
      <div class="card animate-pulse h-96"></div>
    {:else}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Poll Config -->
        <div class="card">
          <h3 class="font-semibold mb-3 flex items-center gap-2"><Icon name="gateways" size={18} /> Poll-Konfiguration</h3>
          <div class="space-y-3">
            <div><label class="text-xs text-slate-500">API URL</label><input class="font-mono text-xs" bind:value={pollUrl} /></div>
            <div class="grid grid-cols-2 gap-3">
              <div><label class="text-xs text-slate-500">Intervall (s)</label><input type="number" bind:value={pollInterval} min="5" /></div>
              <div><label class="text-xs text-slate-500">Timeout (s)</label><input type="number" bind:value={pollTimeout} min="1" /></div>
            </div>
            <div class="flex items-center gap-2">
              <input type="checkbox" bind:checked={pollVerifyTls} class="!w-auto" />
              <label class="!mb-0 text-xs text-slate-400">TLS Verify</label>
            </div>
            <div><label class="text-xs text-slate-500">Severities (kommagetrennt)</label><input bind:value={pollSeverities} placeholder="error, alert, warning" /></div>
          </div>
        </div>

        <!-- Auth -->
        <div class="card">
          <h3 class="font-semibold mb-3 flex items-center gap-2"><Icon name="notifier" size={18} /> LCC API Authentifizierung</h3>
          <div class="space-y-3">
            <div><label class="text-xs text-slate-500">Auth-Typ</label>
              <select bind:value={authType} class="text-xs">
                <option value="oauth2">OAuth2 (Client Credentials)</option>
                <option value="bearer">Bearer Token</option>
                <option value="basic">Basic Auth</option>
                <option value="none">Keine</option>
              </select>
            </div>
            {#if authType === 'oauth2'}
              <div><label class="text-xs text-slate-500">Token URL</label><input class="font-mono text-xs" bind:value={authTokenUrl} placeholder="https://10.89.11.52/oauth/token" /></div>
              <div class="grid grid-cols-2 gap-3">
                <div><label class="text-xs text-slate-500">Client ID</label><input class="font-mono text-xs" bind:value={authClientId} /></div>
                <div><label class="text-xs text-slate-500">Client Secret</label><input class="font-mono text-xs" type="password" bind:value={authClientSecret} /></div>
              </div>
              <div><label class="text-xs text-slate-500">Scope</label><input class="font-mono text-xs" bind:value={authScope} /></div>
            {/if}
          </div>
        </div>

        <!-- Escalation -->
        <div class="card">
          <h3 class="font-semibold mb-3 flex items-center gap-2"><Icon name="incidents" size={18} /> Eskalation</h3>
          <div class="space-y-3">
            <div><label class="text-xs text-slate-500">Digest-Intervall (min)</label><input type="number" bind:value={digestInterval} min="1" /></div>
            <div><label class="text-xs text-slate-500">Sofort-Benachrichtigung (kommagetrennt)</label><input bind:value={immediateSeverities} placeholder="error, alert" /></div>
            <div class="flex items-center gap-2">
              <input type="checkbox" bind:checked={notifyResolved} class="!w-auto" />
              <label class="!mb-0 text-xs text-slate-400">Entwarnung bei Resolved</label>
            </div>
          </div>
        </div>

        <!-- State -->
        <div class="card">
          <h3 class="font-semibold mb-3 flex items-center gap-2"><Icon name="dashboard" size={18} /> State</h3>
          <div><label class="text-xs text-slate-500">State DB Pfad</label><input class="font-mono text-xs" bind:value={stateDbPath} /></div>
        </div>

        <!-- Channels -->
        <div class="card md:col-span-2">
          <div class="flex items-center justify-between mb-3">
            <h3 class="font-semibold flex items-center gap-2"><Icon name="gateways" size={18} /> Kanäle</h3>
            <button class="btn btn-primary text-xs" onclick={() => showAddChannel = !showAddChannel}>
              {showAddChannel ? '✕ Abbrechen' : '+ Neuer Kanal'}
            </button>
          </div>

          <!-- Add Channel Form -->
          {#if showAddChannel}
            <div class="mb-4 p-3 rounded bg-slate-900 border border-slate-700 space-y-3">
              <div class="grid grid-cols-2 gap-3">
                <div><label class="text-xs text-slate-500">Name</label><input class="text-xs" bind:value={newChannelName} placeholder="email_lab" /></div>
                <div><label class="text-xs text-slate-500">Typ</label>
                  <select bind:value={newChannelType} class="text-xs">
                    {#each channelTypes as ct}
                      <option value={ct.value}>{ct.label}</option>
                    {/each}
                  </select>
                </div>
              </div>
              <button class="btn btn-primary text-xs" onclick={addChannel} disabled={!newChannelName.trim()}>Hinzufügen</button>
            </div>
          {/if}

          <!-- Channel List -->
          {#if channelNames.length === 0}
            <p class="text-sm text-slate-500">Keine Kanäle konfiguriert</p>
          {:else}
            <div class="space-y-3">
              {#each channelNames as name}
                {@const ch = config?.channels?.[name] || {}}
                <div class="rounded bg-slate-900/50 border border-slate-800 overflow-hidden">
                  <!-- Channel Header -->
                  <div class="flex items-center gap-3 p-3">
                    <button class="text-sm text-slate-400 hover:text-slate-200 text-left flex-1 font-medium" onclick={() => editingChannel = editingChannel === name ? null : name}>
                      {editingChannel === name ? '▾' : '▸'} {name}
                    </button>
                    <span class="badge text-xs {ch.type === 'email' ? 'bg-green-500/10 text-green-400' : ch.type === 'eln' ? 'bg-purple-500/10 text-purple-400' : 'bg-orange-500/10 text-orange-400'}">{ch.type}</span>
                    <button class="btn btn-ghost text-xs py-0.5 px-2 text-red-400 hover:text-red-300" onclick={() => deleteChannel(name)} title="Löschen">✕</button>
                  </div>

                  <!-- Channel Edit Fields -->
                  {#if editingChannel === name}
                    <div class="p-3 pt-0 border-t border-slate-800 space-y-2">
                      {#each (channelTypes.find(ct => ct.value === ch.type)?.fields || []) as field}
                        <div>
                          <label class="text-xs text-slate-500">{field}</label>
                          {#if field === 'use_ssl' || field === 'use_starttls' || field === 'verify_tls'}
                            <input type="checkbox" checked={ch[field] === true || ch[field] === 'true'} onchange={(e) => updateChannelField(name, field, e.target.checked)} class="!w-auto" />
                          {:else if field === 'to_addrs' || field === 'to_numbers' || field === 'recipient_user_ids'}
                            <input class="font-mono text-xs" value={Array.isArray(ch[field]) ? ch[field].join(', ') : (ch[field] || '')} oninput={(e) => updateChannelField(name, field, e.target.value)} />
                          {:else if field === 'auth_type'}
                            {@const authObj = ch.auth || {}}
                            <select value={authObj.type || 'api_key'} onchange={(e) => updateChannelField(name, 'auth.type', e.target.value)} class="text-xs">
                              <option value="api_key">API Key</option>
                              <option value="personal_token">Personal Token</option>
                              <option value="bearer">Bearer</option>
                              <option value="oauth2">OAuth2</option>
                            </select>
                          {:else if field === 'auth_token' || field === 'auth_self_endpoint'}
                            {@const authObj = ch.auth || {}}
                            <input class="font-mono text-xs" value={authObj[field] || ''} oninput={(e) => updateChannelField(name, 'auth.' + field, e.target.value)} />
                          {:else}
                            <input class="font-mono text-xs" value={ch[field] || ''} oninput={(e) => updateChannelField(name, field, e.target.value)} />
                          {/if}
                        </div>
                      {/each}
                    </div>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
        </div>

        <!-- Save -->
        <div class="card md:col-span-2 flex items-center gap-4">
          <button class="btn btn-primary text-sm" onclick={saveConfig}>💾 Alle Einstellungen speichern</button>
          {#if cfgSaved}<span class="text-xs text-green-400">✓ Gespeichert!</span>{/if}
          {#if cfgError}<span class="text-xs text-red-400">⚠ {cfgError}</span>{/if}
          <span class="text-xs text-slate-600 ml-auto">Änderungen werden erst nach Speichern und Neustart des Pollers aktiv</span>
        </div>
      </div>
    {/if}
  {/if}

  <!-- ═══════════════════════════════════════════════════════════════ -->
  <!-- HISTORY TAB -->
  <!-- ═══════════════════════════════════════════════════════════════ -->
  {#if tab === 'history'}
    {#if notifierLoading}
      <div class="card animate-pulse h-48"></div>
    {:else}
      <div class="card">
        <h3 class="font-semibold mb-3 flex items-center gap-2"><Icon name="gateways" size={18} /> Sendungsverlauf</h3>
        {#if !historyItems?.length}
          <p class="text-sm text-slate-500 py-8 text-center">Keine gesendeten Benachrichtigungen</p>
        {:else}
          <div class="overflow-x-auto">
            <table class="table-glass">
              <thead><tr><th>Zeit</th><th>Incident</th><th>Severity</th><th>Kanal</th><th>Typ</th></tr></thead>
              <tbody>
                {#each historyItems as item}
                  <tr>
                    <td class="text-xs text-slate-400 whitespace-nowrap">{item.time}</td>
                    <td class="text-xs text-slate-300 max-w-xs truncate" title={item.incident}>{item.incident}</td>
                    <td><span class="badge {sevBadge(item.severity)} text-xs">{item.severity||'-'}</span></td>
                    <td class="text-xs text-slate-400">{item.channel}</td>
                    <td class="text-xs text-slate-500">{item.kind}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      </div>
    {/if}
  {/if}
</div>

<!-- Detail Modal -->
{#if selectedIncident}
  {@const inc = selectedIncident}
  <div class="modal-overlay" onclick={() => selectedIncident = null} role="dialog">
    <div class="card max-w-2xl w-full mx-4 max-h-[85vh] overflow-y-auto" onclick={(e) => e.stopPropagation()}>
      <div class="flex items-start justify-between mb-4">
        <h3 class="text-lg font-bold pr-4">{inc.title}</h3>
        <button class="btn btn-ghost text-sm px-2 py-1" onclick={() => selectedIncident = null}>✕</button>
      </div>
      <div class="grid grid-cols-2 gap-3 text-sm mb-4">
        <div><label class="text-xs text-slate-500">Severity</label><span class="badge {sevBadge(inc.severity)}">{inc.severity}</span></div>
        <div><label class="text-xs text-slate-500">Status</label><span class="text-xs {stColors[inc.status]||''}">{inc.status}</span></div>
        <div><label class="text-xs text-slate-500">ID</label><span class="font-mono text-xs text-slate-400">{inc.id}</span></div>
        <div><label class="text-xs text-slate-500">Zeit</label><span class="text-slate-400 text-xs">{formatTs(inc.timestamp)}</span></div>
        <div><label class="text-xs text-slate-500">Gerät</label><span class="font-mono text-xs text-slate-400">{deviceName(inc.source)}</span></div>
        <div><label class="text-xs text-slate-500">Raum</label><span class="text-slate-400 text-xs">{inc.room_name||'-'} {inc.room_number||''}</span></div>
        {#if inc.room_contact_name}<div><label class="text-xs text-slate-500">Kontakt</label><span class="text-slate-400 text-xs">{inc.room_contact_name} {inc.room_contact_email}</span></div>{/if}
      </div>
      {#if inc.high_high_limit != null || inc.high_limit != null || inc.low_limit != null || inc.low_low_limit != null}
        <div class="mb-4"><label class="text-xs text-slate-500">Schwellwerte</label>
          <div class="flex gap-2 text-xs font-mono flex-wrap">
            {#if inc.high_high_limit != null}<span class="px-2 py-0.5 rounded bg-red-500/10 text-red-400">HH&gt;{inc.high_high_limit}</span>{/if}
            {#if inc.high_limit != null}<span class="px-2 py-0.5 rounded bg-orange-500/10 text-orange-400">H&gt;{inc.high_limit}</span>{/if}
            {#if inc.low_limit != null}<span class="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400">L&lt;{inc.low_limit}</span>{/if}
            {#if inc.low_low_limit != null}<span class="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400">LL&lt;{inc.low_low_limit}</span>{/if}
          </div>
        </div>
      {/if}
      <div class="mb-4"><label class="text-xs text-slate-500">Flags</label>
        <div class="flex flex-wrap gap-2 text-xs">
          {#if inc.acknowledged}<span class="px-2 py-0.5 rounded bg-blue-500/10 text-blue-400">Quittiert</span>{/if}
          {#if inc.confirmed}<span class="px-2 py-0.5 rounded bg-green-500/10 text-green-400">Bestätigt</span>{/if}
          {#if inc.reported}<span class="px-2 py-0.5 rounded bg-purple-500/10 text-purple-400">Gemeldet</span>{/if}
          {#if inc.strict_audited}<span class="px-2 py-0.5 rounded bg-yellow-500/10 text-yellow-400">Audit</span>{/if}
          {#if inc.flap_count > 0}<span class="px-2 py-0.5 rounded bg-red-500/10 text-red-400">Flattern {inc.flap_count}x</span>{/if}
        </div>
      </div>
      {#if inc.description}<div class="mb-4"><label class="text-xs text-slate-500">Beschreibung</label><p class="text-sm text-slate-400">{inc.description}</p></div>{/if}
      {#if inc.help}<div class="mb-4 p-3 rounded-lg bg-blue-500/5 border border-blue-500/20"><label class="text-xs text-blue-400">Handlungsempfehlung</label><p class="text-sm text-blue-300">{inc.help}</p></div>{/if}
      {#if inc.comment}<div class="mb-4"><label class="text-xs text-slate-500">Kommentar</label><p class="text-sm text-slate-400 italic">"{inc.comment}"</p></div>{/if}
      {#if inc.url}<a href={inc.url} target="_blank" rel="noopener" class="btn btn-ghost text-sm">🔗 Im LCC öffnen</a>{/if}
    </div>
  </div>
{/if}

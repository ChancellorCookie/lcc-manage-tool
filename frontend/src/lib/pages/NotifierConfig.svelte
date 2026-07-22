<script>
  import { api } from '../api.js'
  import { onMount } from 'svelte'

  let tab = $state('templates')

  // Templates
  let templates = $state({})
  let defaults = $state({})
  let placeholderGroups = $state([])
  let placeholderHelp = $state({})
  let sampleValues = $state({})
  let templatesLoading = $state(true)
  let templatesSaved = $state(false)
  let templatesError = $state('')

  // Local edit state
  let editSubject = $state('')
  let editBody = $state('')
  let editResolvedSubject = $state('')
  let editResolvedBody = $state('')
  let previewIncident = $state(null)

  // Settings
  let config = $state({})
  let configLoading = $state(true)

  onMount(async () => {
    try {
      const data = await api.notifier.templates()
      templates = data.templates || {}
      defaults = data.defaults || {}
      placeholderGroups = data.placeholder_groups || []
      placeholderHelp = data.placeholder_help || {}
      sampleValues = data.sample_values || {}
      editSubject = templates.alert_subject || ''
      editBody = templates.alert_body || ''
      editResolvedSubject = templates.resolved_subject || ''
      editResolvedBody = templates.resolved_body || ''
    } catch (e) {
      templatesError = e.message
    } finally {
      templatesLoading = false
    }

    try {
      config = await api.notifier.config()
    } catch { /* ignore */ }
    configLoading = false
  })

  async function saveTemplates() {
    templatesSaved = false
    templatesError = ''
    try {
      const result = await api.notifier.saveTemplates({
        alert_subject: editSubject,
        alert_body: editBody,
        resolved_subject: editResolvedSubject,
        resolved_body: editResolvedBody,
      })
      templates = result.templates
      templatesSaved = true
      setTimeout(() => (templatesSaved = false), 3000)
    } catch (e) {
      templatesError = e.message
    }
  }

  function previewTemplate(tpl, vals) {
    let result = tpl
    for (const [k, v] of Object.entries(vals)) {
      result = result.replaceAll(`{${k}}`, v)
    }
    return result
  }

  function resetToDefaults() {
    editSubject = defaults.alert_subject || ''
    editBody = defaults.alert_body || ''
    editResolvedSubject = defaults.resolved_subject || ''
    editResolvedBody = defaults.resolved_body || ''
  }

  function insertPlaceholder(field, placeholder) {
    const key = `{${placeholder}}`
    if (field === 'subject') editSubject += key
    else if (field === 'body') editBody += key
    else if (field === 'resolved_subject') editResolvedSubject += key
    else if (field === 'resolved_body') editResolvedBody += key
  }

  function useDefaultIfEmpty(val, def) {
    return val?.trim() || def
  }

  // Compute active preview subject/body
  let previewAlertSubject = $derived(previewTemplate(useDefaultIfEmpty(editSubject, defaults.alert_subject), sampleValues))
  let previewAlertBody = $derived(previewTemplate(useDefaultIfEmpty(editBody, defaults.alert_body), sampleValues))
  let previewResolvedSubject = $derived(previewTemplate(useDefaultIfEmpty(editResolvedSubject, defaults.resolved_subject), sampleValues))
  let previewResolvedBody = $derived(previewTemplate(useDefaultIfEmpty(editResolvedBody, defaults.resolved_body), sampleValues))

  // Settings derived
  let pollInterval = $derived(config?.poll?.interval_seconds || 30)
  let severities = $derived(config?.poll?.severities || [])
  let channelNames = $derived(Object.keys(config?.channels || {}))
  let digestInterval = $derived(config?.escalation?.digest_interval_minutes || 60)
  let immediate = $derived(config?.escalation?.immediate || [])
</script>

<div>
  <h2 class="text-xl font-bold mb-1">⚙ Notifier</h2>
  <p class="text-sm text-slate-500 mb-6">Templates und Einstellungen für den Incident-Benachrichtigungsdienst</p>

  <!-- Tabs -->
  <div class="flex gap-1 mb-6 border-b border-slate-800">
    <button
      class="px-4 py-2 text-sm rounded-t-lg transition-colors {tab === 'templates' ? 'bg-slate-800 text-slate-200' : 'text-slate-500 hover:text-slate-300'}"
      onclick={() => tab = 'templates'}
    >
      📝 Templates
    </button>
    <button
      class="px-4 py-2 text-sm rounded-t-lg transition-colors {tab === 'settings' ? 'bg-slate-800 text-slate-200' : 'text-slate-500 hover:text-slate-300'}"
      onclick={() => tab = 'settings'}
    >
      ⚙ Einstellungen
    </button>
  </div>

  <!-- ================================================================ -->
  <!-- Templates Tab -->
  <!-- ================================================================ -->
  {#if tab === 'templates'}
    {#if templatesLoading}
      <div class="card animate-pulse h-48"></div>
    {:else}

      <div class="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <!-- Left: Editor -->
        <div class="space-y-6">
          <!-- Alert Templates -->
          <div class="card">
            <h3 class="font-semibold mb-1">🚨 Alert (sofort)</h3>
            <p class="text-xs text-slate-500 mb-3">Betreff und Body für ERROR/ALERT-Incidents</p>

            <div class="mb-3">
              <div class="flex items-center justify-between">
                <label>Betreff (Subject)</label>
                <div class="relative group">
                  <button class="text-xs text-blue-400 hover:text-blue-300">+ Platzhalter</button>
                  <div class="absolute right-0 top-6 z-10 hidden group-hover:block bg-slate-900 border border-slate-700 rounded-lg p-2 w-64 shadow-xl max-h-64 overflow-y-auto">
                    {#each placeholderGroups as [group, placeholders]}
                      <div class="text-xs text-slate-500 px-2 py-1 uppercase">{group}</div>
                      {#each placeholders as ph}
                        <button
                          class="block w-full text-left text-xs px-2 py-1 rounded hover:bg-slate-800 text-slate-300"
                          onclick={() => insertPlaceholder('subject', ph)}
                        >
                          {'{' + ph + '}'}
                          <span class="text-slate-600 ml-1">{placeholderHelp[ph] || ''}</span>
                        </button>
                      {/each}
                    {/each}
                  </div>
                </div>
              </div>
              <textarea
                rows="2"
                class="font-mono text-xs"
                bind:value={editSubject}
                placeholder={defaults.alert_subject}
              ></textarea>
            </div>

            <div>
              <div class="flex items-center justify-between">
                <label>Body</label>
                <div class="relative group">
                  <button class="text-xs text-blue-400 hover:text-blue-300">+ Platzhalter</button>
                  <div class="absolute right-0 top-6 z-10 hidden group-hover:block bg-slate-900 border border-slate-700 rounded-lg p-2 w-64 shadow-xl max-h-64 overflow-y-auto">
                    {#each placeholderGroups as [group, placeholders]}
                      <div class="text-xs text-slate-500 px-2 py-1 uppercase">{group}</div>
                      {#each placeholders as ph}
                        <button
                          class="block w-full text-left text-xs px-2 py-1 rounded hover:bg-slate-800 text-slate-300"
                          onclick={() => insertPlaceholder('body', ph)}
                        >
                          {'{' + ph + '}'}
                        </button>
                      {/each}
                    {/each}
                  </div>
                </div>
              </div>
              <textarea
                rows="10"
                class="font-mono text-xs"
                bind:value={editBody}
                placeholder={defaults.alert_body}
              ></textarea>
            </div>
          </div>

          <!-- Resolved Templates -->
          <div class="card">
            <h3 class="font-semibold mb-1">✅ Entwarnung (Resolved)</h3>
            <p class="text-xs text-slate-500 mb-3">Nachricht wenn ein Incident nicht mehr offen ist</p>

            <div class="mb-3">
              <label>Betreff</label>
              <textarea
                rows="2"
                class="font-mono text-xs"
                bind:value={editResolvedSubject}
                placeholder={defaults.resolved_subject}
              ></textarea>
            </div>

            <div>
              <label>Body</label>
              <textarea
                rows="6"
                class="font-mono text-xs"
                bind:value={editResolvedBody}
                placeholder={defaults.resolved_body}
              ></textarea>
            </div>
          </div>

          <!-- Actions -->
          <div class="flex gap-3 items-center">
            <button class="btn btn-primary" onclick={saveTemplates}>
              💾 Speichern
            </button>
            <button class="btn btn-ghost" onclick={resetToDefaults}>
              ↺ Auf Defaults zurücksetzen
            </button>
            {#if templatesSaved}
              <span class="text-xs text-green-400">✓ Gespeichert!</span>
            {/if}
            {#if templatesError}
              <span class="text-xs text-red-400">⚠ {templatesError}</span>
            {/if}
          </div>
        </div>

        <!-- Right: Preview -->
        <div class="space-y-4">
          <div class="card">
            <h3 class="font-semibold mb-3">👁 Live-Vorschau (Alert)</h3>
            <div class="mb-2 p-3 rounded bg-slate-900 border border-slate-800">
              <div class="text-xs text-slate-500 mb-1">Betreff</div>
              <div class="text-sm font-semibold">{previewAlertSubject}</div>
            </div>
            <div class="p-3 rounded bg-slate-900 border border-slate-800">
              <div class="text-xs text-slate-500 mb-1">Body</div>
              <pre class="text-xs text-slate-300 whitespace-pre-wrap font-sans">{previewAlertBody}</pre>
            </div>
          </div>

          <div class="card">
            <h3 class="font-semibold mb-3">👁 Live-Vorschau (Entwarnung)</h3>
            <div class="mb-2 p-3 rounded bg-slate-900 border border-slate-800">
              <div class="text-xs text-slate-500 mb-1">Betreff</div>
              <div class="text-sm font-semibold">{previewResolvedSubject}</div>
            </div>
            <div class="p-3 rounded bg-slate-900 border border-slate-800">
              <div class="text-xs text-slate-500 mb-1">Body</div>
              <pre class="text-xs text-slate-300 whitespace-pre-wrap font-sans">{previewResolvedBody}</pre>
            </div>
          </div>
        </div>
      </div>
    {/if}

  <!-- ================================================================ -->
  <!-- Settings Tab -->
  <!-- ================================================================ -->
  {:else if tab === 'settings'}
    {#if configLoading}
      <div class="card animate-pulse h-48"></div>
    {:else}
      <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
        <!-- Poll -->
        <div class="card">
          <h3 class="font-semibold mb-3">🔄 Poll-Konfiguration</h3>
          <div class="space-y-3 text-sm">
            <div class="flex justify-between">
              <span class="text-slate-400">API URL</span>
              <span class="font-mono text-xs text-slate-300">{config?.poll?.url || '-'}</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">Intervall</span>
              <span>{pollInterval}s</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">Timeout</span>
              <span>{config?.poll?.timeout_seconds || 10}s</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">TLS Verify</span>
              <span class="text-xs font-mono">{config?.poll?.verify_tls ?? true}</span>
            </div>
            <div>
              <span class="text-slate-400 block mb-1">Severities</span>
              <div class="flex flex-wrap gap-1">
                {#each severities as sev}
                  <span class="badge {sev === 'error' ? 'bg-red-500/20 text-red-400' : sev === 'alert' ? 'bg-orange-500/20 text-orange-400' : 'bg-yellow-500/20 text-yellow-400'}">{sev}</span>
                {/each}
              </div>
            </div>
          </div>
        </div>

        <!-- Escalation -->
        <div class="card">
          <h3 class="font-semibold mb-3">⏱ Eskalation</h3>
          <div class="space-y-3 text-sm">
            <div class="flex justify-between">
              <span class="text-slate-400">Sofort-Benachrichtigung</span>
              <div class="flex gap-1">
                {#each immediate as sev}
                  <span class="badge {sev === 'error' ? 'bg-red-500/20 text-red-400' : 'bg-orange-500/20 text-orange-400'}">{sev}</span>
                {/each}
              </div>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">Digest-Intervall</span>
              <span>{digestInterval} min</span>
            </div>
            <div class="flex justify-between">
              <span class="text-slate-400">Entwarnung bei Resolved</span>
              <span>{config?.escalation?.notify_on_resolved ? '✅ Ja' : '❌ Nein'}</span>
            </div>
          </div>
        </div>

        <!-- Channels -->
        <div class="card md:col-span-2">
          <h3 class="font-semibold mb-3">📡 Kanäle</h3>
          {#if channelNames.length === 0}
            <p class="text-sm text-slate-500">Keine Kanäle konfiguriert</p>
          {:else}
            <div class="space-y-2">
              {#each channelNames as name}
                {@const ch = config?.channels?.[name] || {}}
                <div class="flex items-center gap-3 p-2 rounded bg-slate-900/50 border border-slate-800">
                  <span class="text-sm font-medium">{name}</span>
                  <span class="badge bg-blue-500/10 text-blue-400">{ch.type}</span>
                  {#if ch.type === 'email'}
                    <span class="text-xs text-slate-500 font-mono">{ch.from_addr || '?'} → {ch.to_addrs?.join?.(', ') || '?'}</span>
                  {:else if ch.type === 'whatsapp_twilio'}
                    <span class="text-xs text-slate-500">{ch.from_number || '?'} → {ch.to_numbers?.join?.(', ') || '?'}</span>
                  {:else if ch.type === 'eln'}
                    <span class="text-xs text-slate-500">{ch.base_url || '?'}</span>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}
          <p class="text-xs text-slate-600 mt-3">Kanäle werden in der <code class="text-slate-500">config/config.yaml</code> verwaltet (read-only in der UI).</p>
        </div>

        <!-- State -->
        <div class="card">
          <h3 class="font-semibold mb-3">🗄 State</h3>
          <div class="text-sm flex justify-between">
            <span class="text-slate-400">Datenbank</span>
            <span class="font-mono text-xs text-slate-300">{config?.state?.db_path || '-'}</span>
          </div>
        </div>
      </div>
    {/if}
  {/if}
</div>

const __agentCfg = window.QPTM_AGENT_CONFIG || {};
const CHAT_URL = __agentCfg.chatUrl || '/agent-api/chat';
const CONVERSATIONS_URL = CHAT_URL.replace(/\/chat\/?$/, '/conversations');
const CLASSIFY_URL = CHAT_URL.replace(/\/chat\/?$/, '/classify');
const RESET_SESSION_URL = CHAT_URL.replace(/\/chat\/?$/, '/reset-session');
const COLLECTION_URL = CHAT_URL.replace(/\/chat\/?$/, '/collection');
const CONV_STORAGE_KEY = 'qptm_agent_conversation_id';
const DEVICE_STORAGE_KEY = 'qptm_agent_device_id';
const SESSION_STORAGE_PREFIX = 'qptm_agent_session_';
/** Current chat mode: qa (default) or deep_research */
let agentChatMode = 'qa';

function sessionStorageKey(conversationId) {
  return conversationId ? `${SESSION_STORAGE_PREFIX}${conversationId}` : null;
}

function persistSessionForConversation(conversationId, sid) {
  const key = sessionStorageKey(conversationId);
  if (key && sid) sessionStorage.setItem(key, sid);
}

function restoreSessionForConversation(conversationId) {
  const key = sessionStorageKey(conversationId);
  return key ? sessionStorage.getItem(key) : null;
}

const TOOL_DISPLAY = {
  qptm_resolve: { name: 'UniProt', desc: 'Resolve gene → accession', kind: 'database' },
  qptm_search: { name: 'qPTM', desc: 'PTM search', kind: 'database' },
  qptm_kinases: { name: 'qPTM', desc: 'Kinase associations', kind: 'database' },
  qptm_site_conditions: { name: 'qPTM', desc: 'Site conditions', kind: 'database' },
  iptmnet_enzymes: { name: 'iPTMnet', desc: 'Enzyme–substrate', kind: 'database' },
  pubtator_literature_search: { name: 'PubTator3', desc: 'Literature search', kind: 'literature' },
  pubmed_fetch_abstracts: { name: 'PubMed', desc: 'Abstract fetch', kind: 'literature' },
};

function friendlyTool(toolName, kindHint) {
  const meta = TOOL_DISPLAY[toolName];
  if (meta) return { label: meta.name, desc: meta.desc, kind: meta.kind };
  const label = toolName.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
  return { label, desc: toolName, kind: kindHint || 'database' };
}

function showStreamStatus(_text, _roundText) {
  /* Status bar removed — progress shown in message activity timeline only */
}

function renderSourcesDrawer(_citations, _activeTab) {
  /* Sources sidebar removed — citations remain inline in answers as [Sx] */
}

function initSourcesDrawerUi() {
  initClarificationModal();
}

document.addEventListener('DOMContentLoaded', initSourcesDrawerUi);

function getDeviceId() {
  let id = localStorage.getItem(DEVICE_STORAGE_KEY);
  if (id && /^[0-9a-fA-F-]{8,64}$/.test(id)) return id;
  if (window.crypto && typeof window.crypto.randomUUID === 'function') {
    id = window.crypto.randomUUID();
  } else {
    id = 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
      const r = (Math.random() * 16) | 0;
      const v = c === 'x' ? r : (r & 0x3) | 0x8;
      return v.toString(16);
    });
  }
  localStorage.setItem(DEVICE_STORAGE_KEY, id);
  return id;
}

function apiHeaders(extra) {
  const headers = Object.assign({ 'X-Device-Id': getDeviceId() }, extra || {});
  return headers;
}

const COLLECTION_STAGE_DEFS = [
  {
    id: 'stage1',
    num: 1,
    title: 'Abstract screening',
    desc: 'Judge whether the paper reports site-level quantitative PTM proteomics.',
  },
  {
    id: 'stage2',
    num: 2,
    title: 'Full-text retrieval',
    desc: 'Retrieve PDF/XML via Unpaywall or PMC; ask for upload if OA is unavailable.',
  },
  {
    id: 'stage3',
    num: 3,
    title: 'Experimental metadata extraction',
    desc: 'Pull Sample, Condition, PTM types, and related experimental information from the full text.',
  },
  {
    id: 'stage4',
    num: 4,
    title: 'Supplementary table identification',
    desc: 'Locate supplementary files that likely contain site-level quantitative tables.',
  },
  {
    id: 'stage5',
    num: 5,
    title: 'Site-level quantitative table parsing',
    desc: 'Resolve supplementary tables and write site-level ratios to Quantitative_data.csv.',
  },
  {
    id: 'stage6',
    num: 6,
    title: 'Raw MS file resolutions',
    desc: 'Look up ProteomeXChange / CPTAC download links for raw MS data.',
  },
];

let sessionId = null;
let conversationId = localStorage.getItem(CONV_STORAGE_KEY) || null;
let conversationList = [];
let isStreaming = false;
let chatHistory = [];
let pendingFiles = [];
/** @type {Record<string, { status: 'ready'|'uploading'|'done'|'error', progress: number }>} */
let pendingFileStatus = {};
let activeCollectionPanel = null;
let currentAbortController = null;

const chatArea = document.getElementById('chatArea');
const welcome = document.getElementById('welcome');
const inputField = document.getElementById('inputField');
const sendBtn = document.getElementById('sendBtn');
const sidebarHistory = document.getElementById('sidebarHistory');
const fileInput = document.getElementById('fileInput');
const pendingFilesEl = document.getElementById('pendingFiles');

if (fileInput) {
  fileInput.addEventListener('change', onFilesSelected);
}

function setSendButtonToStop() {
  isStreaming = true;
  sendBtn.classList.add('stop');
  sendBtn.innerHTML = '<i class="ri-stop-fill"></i>';
  sendBtn.title = 'Stop generation';
  sendBtn.onclick = stopStreaming;
  sendBtn.disabled = false;
}

function setSendButtonToSend() {
  isStreaming = false;
  sendBtn.classList.remove('stop');
  sendBtn.innerHTML = '<i class="ri-send-plane-fill"></i>';
  sendBtn.title = '';
  sendBtn.onclick = sendMessage;
  sendBtn.disabled = false;
}

function stopStreaming() {
  if (currentAbortController) {
    currentAbortController.abort();
    currentAbortController = null;
  }
  setSendButtonToSend();
}

function classifyUploadKind(filename) {
  const ext = (filename || '').toLowerCase().split('.').pop();
  if (ext === 'pdf' || ext === 'xml') return 'fulltext';
  if (['zip', 'xlsx', 'xls', 'csv', 'tsv'].includes(ext)) return 'supplementary';
  return 'unknown';
}

function fileTypeMeta(filename) {
  const ext = ((filename || '').toLowerCase().split('.').pop() || '');
  if (ext === 'pdf') return { icon: 'ri-file-pdf-2-line', cls: 'file-pdf', label: 'PDF' };
  if (ext === 'xlsx' || ext === 'xls') return { icon: 'ri-file-excel-2-line', cls: 'file-excel', label: 'Excel' };
  if (ext === 'csv' || ext === 'tsv') return { icon: 'ri-table-line', cls: 'file-table', label: 'Table' };
  if (ext === 'zip') return { icon: 'ri-file-zip-line', cls: 'file-zip', label: 'ZIP' };
  if (ext === 'xml') return { icon: 'ri-file-code-line', cls: 'file-xml', label: 'XML' };
  return { icon: 'ri-file-2-line', cls: 'file-generic', label: 'File' };
}

function formatFileSize(bytes) {
  const n = Number(bytes) || 0;
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function pendingFileKey(file) {
  return `${file.name}::${file.size}::${file.lastModified || 0}`;
}

function clearPendingFiles() {
  pendingFiles = [];
  pendingFileStatus = {};
  renderPendingFiles();
}

function setPendingFilesUploadState(files, status, progress) {
  (files || []).forEach((file) => {
    const key = pendingFileKey(file);
    pendingFileStatus[key] = {
      status,
      progress: Math.max(0, Math.min(100, Math.round(progress))),
    };
  });
  renderPendingFiles();
}

function renderPendingFiles() {
  if (!pendingFilesEl) return;
  pendingFilesEl.innerHTML = '';
  pendingFilesEl.classList.toggle('has-files', pendingFiles.length > 0);
  pendingFiles.forEach((file, idx) => {
    const meta = fileTypeMeta(file.name);
    const key = pendingFileKey(file);
    const state = pendingFileStatus[key] || { status: 'ready', progress: 0 };
    const chip = document.createElement('div');
    chip.className = `pending-file-chip ${meta.cls}`;
    if (state.status !== 'ready') chip.classList.add(`is-${state.status}`);
    chip.dataset.fileKey = key;
    chip.title = meta.label;

    const pct = state.status === 'ready' ? 0 : state.progress;
    let subText = formatFileSize(file.size);
    if (state.status === 'uploading') subText = `Uploading ${pct}%`;
    else if (state.status === 'done') subText = 'Upload complete';
    else if (state.status === 'error') subText = 'Upload failed';

    chip.innerHTML = `
      <div class="pending-file-chip-row">
        <i class="${meta.icon}" aria-hidden="true"></i>
        <div class="pending-file-meta">
          <div class="pending-file-name">${escapeHtml(file.name)}</div>
          <div class="pending-file-sub">${escapeHtml(subText)}</div>
        </div>
        <button type="button" title="Remove"><i class="ri-close-line"></i></button>
      </div>
      <div class="pending-file-progress" aria-hidden="true"><span style="width:${pct}%"></span></div>
    `;
    const removeBtn = chip.querySelector('button');
    removeBtn.addEventListener('click', () => {
      if ((pendingFileStatus[key] || {}).status === 'uploading') return;
      pendingFiles.splice(idx, 1);
      delete pendingFileStatus[key];
      renderPendingFiles();
    });
    pendingFilesEl.appendChild(chip);
  });
}

function uploadFormData(url, formData, { onProgress, signal } = {}) {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open('POST', url);
    xhr.responseType = 'json';
    xhr.upload.onprogress = (event) => {
      if (!onProgress) return;
      if (event.lengthComputable && event.total > 0) {
        onProgress(event.loaded / event.total);
      } else if (event.loaded > 0) {
        onProgress(Math.min(0.9, event.loaded / (event.loaded + 256 * 1024)));
      }
    };
    xhr.onload = () => {
      const data = xhr.response && typeof xhr.response === 'object'
        ? xhr.response
        : (() => { try { return JSON.parse(xhr.responseText || '{}'); } catch (_) { return {}; } })();
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(data);
      } else {
        const detail = data.detail || data.message || data.error || `HTTP ${xhr.status}`;
        reject(new Error(typeof detail === 'string' ? detail : `HTTP ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error('Network error during upload'));
    xhr.onabort = () => reject(new DOMException('Upload aborted', 'AbortError'));
    if (signal) {
      if (signal.aborted) {
        xhr.abort();
        return;
      }
      signal.addEventListener('abort', () => xhr.abort(), { once: true });
    }
    xhr.send(formData);
  });
}

function renderUploadedFilesHtml(files) {
  if (!files || !files.length) return '';
  const chips = files.map((file) => {
    const name = typeof file === 'string' ? file : file.name;
    const meta = fileTypeMeta(name);
    return `<span class="msg-file-chip ${meta.cls}" title="${escapeHtml(meta.label)}"><i class="${meta.icon}" aria-hidden="true"></i><span>${escapeHtml(name)}</span></span>`;
  }).join('');
  return `<div class="msg-file-list">${chips}</div>`;
}

function onFilesSelected(event) {
  const selected = Array.from(event.target.files || []);
  selected.forEach((file) => {
    if (!pendingFiles.some((f) => f.name === file.name && f.size === file.size)) {
      pendingFiles.push(file);
      pendingFileStatus[pendingFileKey(file)] = { status: 'ready', progress: 0 };
    }
  });
  event.target.value = '';
  renderPendingFiles();
}

async function classifyIntent(message, filenames) {
  const res = await fetch(CLASSIFY_URL, {
    method: 'POST',
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ message, upload_filenames: filenames || [] }),
  });
  if (!res.ok) throw new Error(`Classify HTTP ${res.status}`);
  return res.json();
}

async function resetRuntimeSession(sid) {
  if (!sid) return;
  try {
    await fetch(RESET_SESSION_URL, {
      method: 'POST',
      headers: apiHeaders({ 'Content-Type': 'application/json' }),
      body: JSON.stringify({ session_id: sid }),
    });
  } catch (err) {
    console.warn('Session reset failed:', err);
  }
}

function createCollectionPanelEl(jobId, seedData) {
  const panel = document.createElement('div');
  panel.className = 'plan-panel collection-panel';
  panel.dataset.jobId = jobId;
  panel.dataset.planMode = 'full';
  panel.innerHTML = `
    <div class="plan-panel-header">
      <i class="ri-list-check"></i>
      <span class="collection-plan-title">Data Collection Pipeline</span>
      <i class="ri-arrow-down-s-line toggle-arrow"></i>
    </div>
    <div class="plan-panel-details">
      <div class="plan-panel-summary collection-pmid"></div>
      <div class="plan-steps"></div>
      <div class="collection-plan-think" hidden></div>
    </div>
  `;
  panel.querySelector('.plan-panel-header').addEventListener('click', () => {
    panel.classList.toggle('collapsed');
  });
  const seed = seedData || { current_stage: 'stage1', status: 'pending', stages: {} };
  const seedStage = seed.current_stage || seed.currentStage || 'stage1';
  if (seedStage && seedStage !== 'stage1') {
    panel.dataset.expectedStage = seedStage;
    panel.dataset.planModeLocked = 'focus';
  }
  renderCollectionPlanSteps(panel, seed);
  return panel;
}

function collectionDisplayStage(data, panel) {
  const stages = data?.stages || {};
  const status = data?.status || '';
  const current = data?.current_stage || data?.currentStage || '';
  const next = data?.next_stage || data?.nextStage || '';
  const expected = panel?.dataset?.expectedStage || '';
  const stageIndex = (id) => COLLECTION_STAGE_DEFS.findIndex((d) => d.id === id);

  let display = current || next || '';

  // Resume gap: current still points at a finished stage while next is queued.
  if (
    (status === 'running' || status === 'pending') &&
    next &&
    current &&
    next !== current &&
    (stages[current] === 'completed' || stages[current] === 'skipped')
  ) {
    display = next;
  }

  // Hard floor for this turn: never flash an earlier step than the Continue target.
  // Applies even when lagging SSE events still carry awaiting_continue + old current_stage.
  if (expected) {
    const dIdx = stageIndex(display);
    const eIdx = stageIndex(expected);
    if (eIdx >= 0 && (dIdx < 0 || dIdx < eIdx)) {
      display = expected;
    }
  }

  return display || expected || 'stage1';
}

function collectionPlanModeFor(data, panel) {
  if (panel?.dataset?.planModeLocked === 'focus') return 'focus';
  const stage = collectionDisplayStage(data, panel);
  // Full 6-step overview only on the first pipeline turn (stage1).
  if (stage === 'stage1' || stage === 'pending' || !stage) return 'full';
  return 'focus';
}

function renderCollectionPlanSteps(panel, data) {
  if (!panel) return;
  const stepsEl = panel.querySelector('.plan-steps');
  const titleEl = panel.querySelector('.collection-plan-title');
  if (!stepsEl) return;

  const stages = data.stages || {};
  const current = collectionDisplayStage(data, panel);
  const mode = collectionPlanModeFor(data, panel);
  const next = data.next_stage || data.nextStage || '';
  panel.dataset.planMode = mode;
  panel.dataset.currentStage = current;
  if (next) panel.dataset.nextStage = next;
  if (mode === 'focus') panel.dataset.planModeLocked = 'focus';

  const defs =
    mode === 'full'
      ? COLLECTION_STAGE_DEFS
      : COLLECTION_STAGE_DEFS.filter((d) => d.id === current);

  if (titleEl) {
    if (mode === 'full') {
      titleEl.textContent = 'Data Collection Pipeline';
    } else {
      const def = COLLECTION_STAGE_DEFS.find((d) => d.id === current);
      titleEl.textContent = def ? `Step ${def.num}: ${def.title}` : 'Collection';
    }
  }

  const isLive =
    data.status === 'running' ||
    (Boolean(panel.dataset.expectedStage) &&
      !['awaiting_continue', 'awaiting_upload', 'completed', 'rejected', 'error'].includes(
        data.status,
      ));

  stepsEl.innerHTML = defs
    .map((s) => {
      const st = stages[s.id] || '';
      let cls = 'plan-step';
      if (st) cls += ` ${st}`;
      if (isLive && current === s.id && st !== 'completed') cls += ' running';
      if (mode === 'focus') cls += ' is-focus';
      return `<div class="${cls}" data-stage="${s.id}">
        <div class="plan-step-num">${s.num}</div>
        <div class="plan-step-body">
          <div class="plan-step-title">${escapeHtml(s.title)}</div>
          <div class="plan-step-desc">${escapeHtml(s.desc || '')}</div>
        </div>
      </div>`;
    })
    .join('');
}

function formatCollectionAnswerHtml(raw) {
  const cleaned = String(raw || '')
    .replace(/<<<[A-Z_]+>>>/g, '')
    .replace(/\n{3,}/g, '\n\n')
    .trim();
  const escaped = escapeHtml(cleaned);
  return escaped
    .split('\n')
    .map((line) => {
      if (!line.trim()) return line;

      const kv = line.match(
        /^(Detected PTM types|Paper|Reason|Note|Quantitative tables parsed|Collection complete):\s*(.+)$/i,
      );
      let out;
      if (kv) {
        out = `<span class="collection-answer-key">${kv[1]}:</span> <strong class="collection-answer-em">${kv[2]}</strong>`;
      } else {
        out = line;
        out = out.replace(
          /\b(Found)\s+(\d[\d,]*)\s+(download URL\(s\)[^.]*\.?)/i,
          '$1 <strong class="collection-answer-em">$2</strong> $3',
        );
        out = out.replace(
          /Supplementary quantitative tables located/i,
          '<strong class="collection-answer-em">Supplementary quantitative tables located</strong>',
        );
        out = out.replace(
          /\b(\d[\d,]*)\s+(site-level record\(s\))/gi,
          '<strong class="collection-answer-em">$1</strong> $2',
        );

        // "Site-level quantitative data extracted from: <file>.xls" → file chips with icons
        const siteFiles = out.match(/^(Site-level quantitative data extracted from:)\s*(.+)$/i);
        if (siteFiles) {
          const files = siteFiles[2]
            .split(',')
            .map((s) => s.trim().replace(/[.]$/, ''))
            .filter(Boolean);
          const fileHtml = files
            .map((f) => {
              const meta = fileTypeMeta(f);
              // Excel icon kept, but blue (file-table) instead of green (file-excel).
              const cls = meta.cls === 'file-excel' ? 'file-table' : meta.cls;
              return `<span class="collection-answer-file ${cls}"><i class="${meta.icon}"></i> ${f}</span>`;
            })
            .join(', ');
          out = `<span class="collection-answer-key">${siteFiles[1]}</span> ${fileHtml}`;
        }

        // Status / action lines: black bold (Continue highlighted blue below).
        const isStrongLine =
          /could not be (downloaded|retrieved) automatically/i.test(out) ||
          /^Please upload\b/i.test(out) ||
          /^Click Continue\b/i.test(out) ||
          /^(This paper appears to contain|After screening, this paper|Screening is uncertain|Full text is ready|Full text is already available|Full text retrieved|User-uploaded supplementary tables detected|MS repository download links have been resolved|The supplementary tables were read|Literature metadata extracted|If something looks wrong|If you are willing|You can also click Continue|A MS repository accession was already found)/i.test(
            out,
          );
        if (isStrongLine) {
          out = `<strong class="collection-answer-strong">${out}</strong>`;
        }
      }

      // Every "Continue" mention → blue bold.
      out = out.replace(/\bContinue\b/g, '<strong class="collection-answer-em">Continue</strong>');

      // Artifact file names in prose → file chips with icons (e.g. Quantitative_data.csv).
      out = out.replace(
        /\b(Quantitative_data\.csv|Experimental_info\.csv|MS_URLs\.csv|urls_all\.csv|qratio\.csv)\b/gi,
        (m) => {
          // Quantitative_data.csv is a downloadable Excel-style artifact → Excel icon (blue).
          const isExcel = /^Quantitative_data\.csv$/i.test(m);
          const meta = isExcel
            ? { icon: 'ri-file-excel-2-line', cls: 'file-table' }
            : fileTypeMeta(m);
          return `<span class="collection-answer-file ${meta.cls}"><i class="${meta.icon}"></i> ${m}</span>`;
        },
      );
      return out;
    })
    .join('\n');
}

/** Split collection prose on <<<MARKER>>> layout segments (order preserved). */
function splitCollectionSegments(message, markers) {
  let rest = String(message || '');
  const parts = [];
  for (const marker of markers) {
    const idx = rest.indexOf(marker);
    if (idx < 0) {
      parts.push(rest);
      rest = '';
    } else {
      parts.push(rest.slice(0, idx));
      rest = rest.slice(idx + marker.length);
    }
  }
  parts.push(rest);
  return parts.map((p) =>
    String(p || '')
      .replace(/<<<[A-Z_]+>>>/g, '')
      .replace(/^\n+|\n+$/g, '')
      .replace(/\n{3,}/g, '\n\n')
      .trim(),
  );
}

function collectionAnswerBlock(text, colorStyle = '') {
  const t = String(text || '')
    .replace(/<<<[A-Z_]+>>>/g, '')
    .replace(/^\n+|\n+$/g, '')
    .trim();
  if (!t) return '';
  return `<p class="collection-answer-text" style="white-space:pre-wrap;${colorStyle}">${formatCollectionAnswerHtml(t)}</p>`;
}

function setCollectionPlanThink(panel, html) {
  if (!panel) return;
  const slot = panel.querySelector('.collection-plan-think');
  if (!slot) return;
  if (html && String(html).trim()) {
    slot.innerHTML = html;
    slot.hidden = false;
  } else {
    slot.innerHTML = '';
    slot.hidden = true;
  }
}

/** Preferred field order for literature_info / stage3Row display. */
const LITERATURE_META_FIELDS = [
  'PMID',
  'Title',
  'Sample',
  'Sample type',
  'Organism',
  'PTMs',
  'Label method',
  'Condition',
  'Detail condition',
  'Enrichment method',
  'Mass spectrometer',
  'MS data source',
  'Identifier',
  'status',
  'notes',
  'error',
];

/** Kept in CSV / pipeline, but not shown in the Stage3 UI table. */
const LITERATURE_META_HIDDEN = new Set(['Condition-Sample map', 'conditionSampleMap']);

function getStage3RowFromData(data) {
  if (!data) return null;
  const summary = data.summary || {};
  return summary.stage3Row || summary.stage3_row || null;
}

function renderLiteratureMetaTable(row, opts = {}) {
  if (!row || typeof row !== 'object') return '';
  const failed =
    Boolean(opts.failed) ||
    String(row.status || '').toLowerCase() === 'error' ||
    Boolean(String(row.error || '').trim());
  // Core experimental fields always render (empty → "-") so failures are visible.
  const alwaysShow = [
    'Sample',
    'Sample type',
    'Organism',
    'PTMs',
    'Condition',
    'Mass spectrometer',
    'MS data source',
    'Identifier',
  ];
  if (failed) {
    alwaysShow.push('status', 'notes', 'error');
  }
  const keys = [
    ...LITERATURE_META_FIELDS.filter((k) => Object.prototype.hasOwnProperty.call(row, k)),
    ...Object.keys(row).filter(
      (k) => !LITERATURE_META_FIELDS.includes(k) && !LITERATURE_META_HIDDEN.has(k),
    ),
  ];
  alwaysShow.forEach((k) => {
    if (!keys.includes(k)) keys.push(k);
  });
  if (!keys.length) return '';
  let html = `<div class="collection-meta-wrap${failed ? ' is-failed' : ''}"><table class="collection-meta-table"><tbody>`;
  keys.forEach((key) => {
    if (LITERATURE_META_HIDDEN.has(key)) return;
    const val = row[key];
    const isEmpty = val == null || String(val).trim() === '';
    if (isEmpty && !alwaysShow.includes(key)) return;
    // Hide internal status/notes/error when extraction succeeded
    if (!failed && (key === 'status' || key === 'notes' || key === 'error')) return;
    html += `<tr><th scope="row">${escapeHtml(key)}</th><td>${escapeHtml(isEmpty ? '-' : String(val))}</td></tr>`;
  });
  html += '</tbody></table></div>';
  return html;
}

async function resolveStage3Row(jobId, data) {
  const fromSummary = getStage3RowFromData(data);
  if (fromSummary) return fromSummary;
  if (!jobId) return null;
  try {
    const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/artifacts/metadata`);
    if (!res.ok) return null;
    const body = await res.json();
    return body.row || null;
  } catch (_) {
    return null;
  }
}

function renderStage4ScoutHtml(scout, previewFiles) {
  const files = Array.isArray(previewFiles) ? previewFiles : [];
  let body = '';
  if (files.length) {
    body = files
      .map((f) => {
        const name = String(f.entryPath || '').split('/').pop() || f.entryPath || 'file';
        if (f.error) {
          return `<div class="collection-preview-file">
            <div class="collection-preview-file-name"><i class="ri-file-excel-2-line"></i> ${escapeHtml(name)}</div>
            <div class="collection-preview-empty">${escapeHtml(String(f.error))}</div>
          </div>`;
        }
        const sheets = Array.isArray(f.sheets) ? f.sheets : [];
        if (!sheets.length) {
          return `<div class="collection-preview-file">
            <div class="collection-preview-file-name"><i class="ri-file-excel-2-line"></i> ${escapeHtml(name)}</div>
            <div class="collection-preview-empty">No tabular sheets previewed.</div>
          </div>`;
        }
        const sheetsHtml = sheets
          .map((sh) => {
            const headers = Array.isArray(sh.headers) ? sh.headers : [];
            const preview = Array.isArray(sh.preview) ? sh.preview : [];
            const cols = headers.length
              ? headers
              : (preview[0] ? preview[0].map((_, i) => `col_${i + 1}`) : []);
            let table = '';
            if (cols.length) {
              const bodyRows = preview.length
                ? preview
                : [cols.map(() => '')];
              table = `<div class="collection-preview-table-wrap"><table class="collection-preview-table"><thead><tr>${cols
                .map((h) => `<th>${escapeHtml(String(h || ''))}</th>`)
                .join('')}</tr></thead><tbody>${bodyRows
                .map(
                  (row) =>
                    `<tr>${cols
                      .map((_, i) => `<td>${escapeHtml(String((row && row[i]) || ''))}</td>`)
                      .join('')}</tr>`,
                )
                .join('')}</tbody></table></div>`;
              if (!preview.length) {
                table += `<div class="collection-preview-empty">Header row only (no data rows in preview).</div>`;
              }
            }
            return `<div class="collection-preview-sheet">
              <div class="collection-preview-sheet-name">Sheet: ${escapeHtml(String(sh.name || 'Sheet1'))}</div>
              ${table}
            </div>`;
          })
          .join('');
        return `<div class="collection-preview-file">
          <div class="collection-preview-file-name"><i class="ri-file-excel-2-line"></i> ${escapeHtml(name)}</div>
          ${sheetsHtml}
        </div>`;
      })
      .join('');
  } else if (scout && (scout.verdict || scout.zipStatus)) {
    body = `<div class="collection-preview-empty">Supplementary tables located. Download the ZIP above to inspect files, then click Continue to parse.</div>`;
  } else {
    return '';
  }

  return `
    <div class="collection-think">
      <div class="collection-think-title"><i class="ri-search-eye-line"></i> Supplementary table preview</div>
      ${body}
    </div>`;
}

async function resolveStage4ScoutHtml(jobId, scout) {
  let files = [];
  if (jobId) {
    try {
      const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/artifacts/supp-preview`);
      if (res.ok) {
        const body = await res.json();
        files = body.files || [];
      }
    } catch (_) {
      /* ignore */
    }
  }
  return renderStage4ScoutHtml(scout, files);
}

function renderStage5ThinkingHtml(steps, { live = false } = {}) {
  if (!Array.isArray(steps) || !steps.length) return '';
  const items = steps
    .map((s) => {
      const cls = s.step === 'parsed' ? 'ok' : s.step === 'skip' ? 'skip' : s.step === 'summary' ? 'summary' : '';
      const detail = [];
      if (s.entryPath) {
        const meta = fileTypeMeta(s.entryPath);
        // Excel icon kept, but blue (file-table) instead of green (file-excel).
        const cls = meta.cls === 'file-excel' ? 'file-table' : meta.cls;
        const fileLabel = s.entryPath + (s.sheet ? `#${s.sheet}` : '');
        detail.push(`<span class="collection-think-file ${cls}"><i class="${meta.icon}"></i> ${escapeHtml(fileLabel)}</span>`);
      }
      if (s.mappingSource) detail.push(escapeHtml(s.mappingSource));
      if (s.confidence != null) detail.push(escapeHtml(`conf ${Number(s.confidence).toFixed(2)}`));
      if (s.rowsAdded != null) detail.push(escapeHtml(`+${s.rowsAdded} rows`));
      return `<li class="${cls}"><span class="collection-think-step">${escapeHtml(String(s.step || ''))}</span>
        <span class="collection-think-msg">${escapeHtml(String(s.message || ''))}</span>
        ${detail.length ? `<span class="collection-think-detail">${detail.join(' · ')}</span>` : ''}
      </li>`;
    })
    .join('');
  return `
    <div class="collection-think ${live ? 'is-live' : ''}">
      <div class="collection-think-title"><i class="ri-brain-line"></i> Quantitative table parsing${live ? ' <span class="collection-live-dot"></span>' : ''}</div>
      <ol class="collection-think-log">${items}</ol>
    </div>`;
}

function renderStage6SummaryHtml(stage6) {
  if (!stage6 || typeof stage6 !== 'object') return '';
  const totalUrls = stage6.totalUrls ?? stage6.total_urls;
  const attempted = stage6.attempted;
  const saved = stage6.saved;
  const err = stage6.error;
  const identifier = stage6.identifier || '';
  const bits = [];
  if (identifier) bits.push(`Identifier: <strong>${escapeHtml(String(identifier))}</strong>`);
  if (totalUrls != null) bits.push(`URLs: <strong>${escapeHtml(String(totalUrls))}</strong>`);
  if (attempted != null) bits.push(`Accessions tried: ${escapeHtml(String(attempted))}`);
  if (saved != null) bits.push(`Saved: ${escapeHtml(String(saved))}`);
  if (err) bits.push(`Note: ${escapeHtml(String(err))}`);
  if (!bits.length) {
    bits.push('MS repository link resolution finished.');
  }
  return `
    <div class="collection-think">
      <div class="collection-think-title"><i class="ri-link"></i> MS repository URLs</div>
      <div class="collection-think-meta">${bits.map((b) => `<span>${b}</span>`).join('')}</div>
    </div>`;
}

function renderStage1ThinkHtml(screen) {
  if (!screen || typeof screen !== 'object') return '';
  const decision = screen.decision || '';
  const confidence = screen.confidence;
  const ptmTypes = Array.isArray(screen.ptmTypes) ? screen.ptmTypes.filter(Boolean) : [];
  const organisms = Array.isArray(screen.organisms) ? screen.organisms.filter(Boolean) : [];
  const reason = screen.reason || '';
  const isQuant = screen.isQuantitativeMs;
  const bits = [];
  if (decision) bits.push(`Decision: <strong>${escapeHtml(String(decision))}</strong>`);
  if (confidence != null) bits.push(`Confidence: ${escapeHtml(String(confidence))}`);
  if (ptmTypes.length) bits.push(`PTM types: ${escapeHtml(ptmTypes.join(', '))}`);
  if (organisms.length) bits.push(`Organisms: ${escapeHtml(organisms.join(', '))}`);
  if (isQuant) bits.push('Quantitative MS: yes');
  if (reason) bits.push(`Reason: ${escapeHtml(reason)}`);
  if (!bits.length) return '';
  return `
    <div class="collection-think">
      <div class="collection-think-title"><i class="ri-file-search-line"></i> Abstract screening</div>
      <div class="collection-think-meta">${bits.map((b) => `<span>${b}</span>`).join('')}</div>
    </div>`;
}

function renderStage3ThinkHtml(row) {
  if (!row || typeof row !== 'object') return '';
  const fields = [
    { key: 'Sample', icon: 'ri-flask-line' },
    { key: 'Sample type', icon: 'ri-stack-line' },
    { key: 'Organism', icon: 'ri-microscope-line' },
    { key: 'PTMs', icon: 'ri-dna-line' },
    { key: 'Label method', icon: 'ri-price-tag-3-line' },
    { key: 'Enrichment method', icon: 'ri-filter-3-line' },
    { key: 'Mass spectrometer', icon: 'ri-hard-drive-3-line' },
    { key: 'MS data source', icon: 'ri-database-2-line' },
    { key: 'Identifier', icon: 'ri-key-2-line' },
  ];
  const items = fields.filter((f) => {
    const v = row[f.key];
    return v != null && String(v).trim() !== '';
  });
  if (!items.length) return '';
  const html = items.map(
    (f) => `<div class="collection-think-meta-item"><i class="${f.icon}"></i> <span class="collection-think-label">${escapeHtml(f.key)}:</span> <strong>${escapeHtml(String(row[f.key]))}</strong></div>`,
  ).join('');
  return `
    <div class="collection-think">
      <div class="collection-think-title"><i class="ri-file-text-line"></i> Extracted metadata</div>
      <div class="collection-think-meta">${html}</div>
    </div>`;
}

function renderStage4ThinkHtml(scout) {
  if (!scout || typeof scout !== 'object') return '';
  const verdict = scout.verdict || '';
  const topFiles = scout.topFiles || '';
  const zipStatus = scout.zipStatus || '';
  const bits = [];
  if (verdict) {
    const label = verdict === 'has_tabular_supp' ? 'Quantitative tables found' : 'No quantitative tables found';
    bits.push(`Verdict: <strong>${escapeHtml(label)}</strong>`);
  }
  if (topFiles) bits.push(`Top files: ${escapeHtml(String(topFiles))}`);
  if (zipStatus && zipStatus !== 'not_applicable') bits.push(`Status: ${escapeHtml(String(zipStatus))}`);
  if (!bits.length) return '';
  return `
    <div class="collection-think">
      <div class="collection-think-title"><i class="ri-folder-zip-line"></i> Supplementary scout</div>
      <div class="collection-think-meta">${bits.map((b) => `<span>${b}</span>`).join('')}</div>
    </div>`;
}

function renderCsvPreviewTableHtml(opts) {
  const title = opts.title || 'Preview';
  const icon = opts.icon || 'ri-table-line';
  let headers = Array.isArray(opts.headers) ? opts.headers.slice() : [];
  let preview = Array.isArray(opts.preview)
    ? opts.preview.map((row) => (Array.isArray(row) ? row.slice() : row))
    : [];
  const dropCols = Array.isArray(opts.dropColumns)
    ? opts.dropColumns.map((c) => String(c).toLowerCase())
    : [];
  if (dropCols.length && headers.length) {
    const keepIdx = headers
      .map((h, i) => (dropCols.includes(String(h || '').toLowerCase()) ? -1 : i))
      .filter((i) => i >= 0);
    headers = keepIdx.map((i) => headers[i]);
    preview = preview.map((row) => keepIdx.map((i) => (row && row[i]) || ''));
  }
  const totalRows = opts.totalRows;
  const emptyText = opts.emptyText || 'No rows to preview.';
  if (!headers.length && !preview.length) {
    return `<div class="collection-csv-preview">
      <div class="collection-csv-preview-title"><i class="${icon}"></i> ${escapeHtml(title)}</div>
      <div class="collection-preview-empty">${escapeHtml(emptyText)}</div>
    </div>`;
  }
  const cols = headers.length
    ? headers
    : (preview[0] ? preview[0].map((_, i) => `col_${i + 1}`) : []);
  const shown = preview.length;
  const totalNote =
    totalRows != null && Number(totalRows) > shown
      ? `Showing first ${shown} of ${totalRows} row(s)`
      : `Showing ${shown} row(s)`;
  const table = `<div class="collection-preview-table-wrap"><table class="collection-preview-table"><thead><tr>${cols
    .map((h) => `<th>${escapeHtml(String(h || ''))}</th>`)
    .join('')}</tr></thead><tbody>${preview
    .map(
      (row) =>
        `<tr>${cols
          .map((_, i) => `<td title="${escapeHtml(String((row && row[i]) || ''))}">${escapeHtml(String((row && row[i]) || ''))}</td>`)
          .join('')}</tr>`,
    )
    .join('')}</tbody></table></div>`;
  return `<div class="collection-csv-preview">
    <div class="collection-csv-preview-title"><i class="${icon}"></i> ${escapeHtml(title)}</div>
    <div class="collection-csv-preview-meta">${escapeHtml(totalNote)}</div>
    ${table}
  </div>`;
}

async function fetchCsvArtifactPreview(jobId, kind, maxRows) {
  const path =
    kind === 'ms-urls'
      ? `artifacts/ms-urls-preview?max_rows=${maxRows}`
      : `artifacts/qratio-preview?max_rows=${maxRows}`;
  try {
    const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/${path}`);
    if (!res.ok) return null;
    return await res.json();
  } catch (_) {
    return null;
  }
}

function renderTableHintsFormHtml(candidates, jobId, { mode = 'teach' } = {}) {
  const title =
    mode === 'adjust'
      ? 'Adjust tables / re-parse'
      : 'Teach the agent';
  const body =
    mode === 'adjust'
      ? ''
      : 'Select the file/sheet(s) that contain site-level quantitative PTM ratios, then apply. You can also describe derived contrasts in the note.';
  if (!Array.isArray(candidates) || !candidates.length) {
    return `
      <div class="collection-teach">
        <div class="collection-teach-title">${escapeHtml(title)}</div>
        <div class="collection-teach-body">No inventoried sheets yet. Upload a ZIP/Excel/CSV first, then select sheets here.</div>
      </div>`;
  }
  // Unique per form instance so label[for] does not jump to an older teach box
  // still present in chat history after re-parse.
  const formUid = `hint-${String(jobId || 'job').slice(0, 8)}-${Date.now().toString(36)}-${Math.random()
    .toString(36)
    .slice(2, 7)}`;
  const rows = candidates
    .map((c, i) => {
      const label = c.sheetName
        ? `${c.entryPath} → ${c.sheetName}`
        : c.entryPath;
      const headers = (c.headers || []).slice(0, 8).join(' | ');
      const id = `${formUid}-${i}`;
      const badge = c.notInventoried
        ? '<span class="collection-teach-rows">not auto-scanned</span>'
        : '';
      return `<label class="collection-teach-item" for="${id}">
        <input type="checkbox" id="${id}" data-entry="${escapeHtml(c.entryPath)}" data-sheet="${escapeHtml(c.sheetName || '')}">
        <span class="collection-teach-label">
          <strong>${escapeHtml(label)}</strong>
          ${headers ? `<span class="collection-teach-headers">${escapeHtml(headers)}</span>` : ''}
          ${badge}
        </span>
      </label>`;
    })
    .join('');
  const bodyHtml = body
    ? `<div class="collection-teach-body">${escapeHtml(body)}</div>`
    : '';
  return `
    <div class="collection-teach" data-job-id="${escapeHtml(jobId || '')}">
      <div class="collection-teach-title"><i class="ri-lightbulb-line"></i> ${escapeHtml(title)}</div>
      ${bodyHtml}
      <div class="collection-teach-list">${rows}</div>
      <textarea class="collection-teach-note" rows="2" placeholder="e.g. mod_sites column is UniProt+Amino acid+Position — split this column; or use mmc3.xlsx → Quantified; log2(P5/P1)"></textarea>
      <div class="collection-teach-actions">
        <button type="button" class="collection-btn collection-teach-apply"><i class="ri-check-line"></i> ${mode === 'adjust' ? 'Re-parse with selection' : 'Use selected tables'}</button>
      </div>
    </div>`;
}

async function fetchTableCandidates(jobId) {
  try {
    const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/artifacts/table-candidates`);
    if (!res.ok) return { candidates: [] };
    return await res.json();
  } catch (_) {
    return { candidates: [] };
  }
}

async function submitTableHints(jobId, contentDiv, panel, triggerBtn) {
  const box =
    (triggerBtn && triggerBtn.closest('.collection-teach')) ||
    contentDiv.querySelector('.collection-teach');
  if (!box) return;
  const selections = [];
  box.querySelectorAll('input[type="checkbox"]:checked').forEach((el) => {
    selections.push({
      entryPath: el.getAttribute('data-entry') || '',
      sheetName: el.getAttribute('data-sheet') || undefined,
    });
  });
  const note = box.querySelector('.collection-teach-note')?.value || '';
  if (!selections.length && !note.trim()) {
    alert('Select at least one file/sheet, or describe it in the note.');
    return;
  }
  const btn = triggerBtn || box.querySelector('.collection-teach-apply');
  if (btn) btn.disabled = true;
  // Freeze older teach forms so their note/checkboxes cannot be submitted by mistake.
  document.querySelectorAll('.collection-teach').forEach((el) => {
    if (el === box) return;
    el.querySelectorAll('input, textarea, button').forEach((ctrl) => {
      ctrl.disabled = true;
    });
    el.classList.add('is-stale');
  });

  const pmidText = panel?.querySelector('.collection-pmid')?.textContent || '';
  const pmid = pmidText.replace(/^PMID\s+/i, '').trim() || null;
  // New turn + panel so later chat guidance keeps activeCollectionPanel on stage5.
  const { panel: nextPanel, contentDiv: resultContentDiv } = beginCollectionTurn(jobId, pmid, {
    current_stage: 'stage5',
    next_stage: 'stage5',
    status: 'running',
    stages: {},
  });
  nextPanel.dataset.expectedStage = 'stage5';
  nextPanel.dataset.planModeLocked = 'focus';
  nextPanel.classList.remove('collapsed');
  showContentLoading(resultContentDiv, 'Re-parsing quantitative tables…');
  try {
    const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/table-hints`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ selections, note, resume: true }),
      signal: currentAbortController?.signal,
    });
    if (!res.ok) throw new Error(`Hints HTTP ${res.status}`);
    const body = await res.json();
    if (body.job) {
      updateCollectionPanel(nextPanel, {
        ...body.job,
        current_stage: 'stage5',
        currentStage: 'stage5',
        status: 'running',
      });
    }
    await streamCollectionJob(jobId, nextPanel, resultContentDiv);
  } catch (err) {
    if (err.name === 'AbortError') {
      hideContentLoading(resultContentDiv);
      resultContentDiv.innerHTML = '<p style="color:var(--text-muted);font-style:italic;">Table hints stopped.</p>';
      return;
    }
    hideContentLoading(resultContentDiv);
    resultContentDiv.insertAdjacentHTML(
      'beforeend',
      `<p style="color:#c0392b;">${escapeHtml(err.message || 'Failed to apply table hints')}</p>`,
    );
    if (btn) btn.disabled = false;
  }
}

function bindTableHintsForm(contentDiv, panel, jobId) {
  const btn = contentDiv.querySelector('.collection-teach-apply');
  if (!btn || btn.dataset.bound === '1') return;
  btn.dataset.bound = '1';
  btn.addEventListener('click', () => {
    if (isStreaming) return;
    setSendButtonToStop();
    const abortController = new AbortController();
    currentAbortController = abortController;
    submitTableHints(jobId, contentDiv, panel, btn).finally(() => {
      if (currentAbortController === abortController) currentAbortController = null;
      setSendButtonToSend();
    });
  });
}

async function renderCollectionMessage(contentDiv, data, event, panel) {
  if (!contentDiv || !data) return;
  hideContentLoading(contentDiv);
  let message = data.message || '';
  if (!message) {
    if (event === 'error' || data.status === 'error') message = data.error || 'Collection failed';
    else if (event === 'rejected' || data.status === 'rejected') {
      message = 'This paper did not pass quantitative PTM screening.';
    } else if (event === 'done' || data.status === 'completed') {
      message = 'Collection complete. Download the CSV files below, and optionally contribute to qPTM.';
    } else if (event === 'awaiting_upload' || data.status === 'awaiting_upload') {
      message = 'Please upload a file to continue.';
    } else {
      message = 'Please continue when you are ready.';
    }
  }

  const jobId = data.job_id || data.jobId || panel?.dataset?.jobId;
  const stage = data.current_stage || data.currentStage;
  const summary = data.summary || {};
  const awaitingContinue =
    event === 'awaiting_continue' || data.status === 'awaiting_continue';
  const awaitingUpload =
    event === 'awaiting_upload' || data.status === 'awaiting_upload';
  const completed = event === 'done' || data.status === 'completed';
  const rejected = event === 'rejected' || data.status === 'rejected';

  // ── Plan panel: current step(s) + think / scout ───────────────────────────
  updateCollectionPanel(panel, data);

  let thinkHtml = '';
  let scoutPreviewHtml = '';
  // Stage4 table preview in the answer area (not the plan panel).
  if (stage === 'stage4' && (awaitingContinue || awaitingUpload)) {
    scoutPreviewHtml = await resolveStage4ScoutHtml(jobId, summary.stage4Scout || {});
  }
  // Generic stage thinking steps for plan panel.
  // In "full" mode (stage1) show all available; otherwise only the current stage.
  const isFullMode = (!stage || stage === 'stage1' || stage === 'pending');
  const thinkingStages = [
    { key: 'stage1Thinking', stage: 'stage1', legacy: () => renderStage1ThinkHtml(summary.stage1Screen || summary.stage1) },
    { key: 'stage2Thinking', stage: 'stage2' },
    { key: 'stage3Thinking', stage: 'stage3', legacy: () => renderStage3ThinkHtml(summary.stage3Row) },
    { key: 'stage4Thinking', stage: 'stage4', legacy: () => renderStage4ThinkHtml(summary.stage4Scout) },
  ];
  for (const ts of thinkingStages) {
    if (!isFullMode && ts.stage !== stage) continue;
    const steps = summary[ts.key];
    if (Array.isArray(steps) && steps.length) {
      const meta = STAGE_THINKING_META[ts.stage];
      if (meta) thinkHtml += renderGenericThinkingStepsHtml(steps, { title: meta.title, icon: meta.icon });
    } else if (ts.legacy && (isFullMode || ts.stage === stage)) {
      thinkHtml += ts.legacy();
    }
  }
  // Stage5 parse log only belongs to stage5 (not stage6 / completed).
  if (
    Array.isArray(summary.stage5Thinking) &&
    summary.stage5Thinking.length &&
    (stage === 'stage5' || (awaitingUpload && stage === 'stage5'))
  ) {
    thinkHtml += renderStage5ThinkingHtml(summary.stage5Thinking, { live: false });
  }
  // Stage6: show thinking steps if available.
  if (Array.isArray(summary.stage6Thinking) && summary.stage6Thinking.length && (isFullMode || stage === 'stage6')) {
    thinkHtml += renderGenericThinkingStepsHtml(summary.stage6Thinking, { title: 'MS repository URLs', icon: 'ri-link' });
  } else if ((stage === 'stage6' || completed) && summary.stage6) {
    thinkHtml += renderStage6SummaryHtml(summary.stage6);
  }

  // ── Answer body: prose interleaved with stage widgets ─────────────────────
  const colorStyle =
    event === 'error' || data.status === 'error' ? 'color:#c0392b;' : '';

  let paperHtml = '';
  if (stage === 'stage1' && (awaitingContinue || rejected) && summary.paper) {
    const paper = summary.paper;
    const abs = String(paper.abstract || '').trim();
    paperHtml = `<div class="collection-paper-card">
      <div class="collection-paper-title">${escapeHtml(paper.title || '')}</div>
      ${abs ? `<div class="collection-paper-abs">${escapeHtml(abs)}</div>` : ''}
    </div>`;
  }

  let metaHtml = '';
  const stage3Failed = Boolean(summary.stage3Failed) || data.stages?.stage3 === 'failed';
  if (
    (stage === 'stage3' && awaitingContinue) ||
    (stage3Failed && (awaitingContinue || data.status === 'error'))
  ) {
    const row = await resolveStage3Row(jobId, data);
    metaHtml = renderLiteratureMetaTable(row, { failed: stage3Failed || !row });
  }

  let qratioPreviewHtml = '';
  if (
    jobId &&
    stage === 'stage5' &&
    awaitingContinue &&
    (summary.qratioRowCount || 0) > 0
  ) {
    const qPrev = await fetchCsvArtifactPreview(jobId, 'qratio', 10);
    if (qPrev) {
      qratioPreviewHtml = renderCsvPreviewTableHtml({
        title: 'Quantitative_data.csv preview',
        icon: 'ri-file-excel-2-line',
        headers: qPrev.headers,
        preview: qPrev.preview,
        totalRows: qPrev.totalRows,
        emptyText: 'Quantitative_data.csv has no data rows yet.',
      });
    }
  }

  let msPreviewHtml = '';
  if (jobId && (stage === 'stage6' || completed)) {
    const uPrev = await fetchCsvArtifactPreview(jobId, 'ms-urls', 5);
    if (uPrev) {
      const renameMs = {
        accession: 'Accession',
        repo: 'Repository',
        url: 'URLs',
        pmid: 'PMID',
      };
      const headers = (uPrev.headers || []).map(
        (h) => renameMs[String(h || '').toLowerCase()] || h,
      );
      msPreviewHtml = renderCsvPreviewTableHtml({
        title: 'MS_URLs.csv preview',
        icon: 'ri-link',
        headers,
        preview: uPrev.preview,
        totalRows: uPrev.totalRows,
        dropColumns: ['is_raw'],
        emptyText: 'No MS repository URLs were resolved.',
      });
    }
  }

  // Teach / Adjust tables: after Stage5 failure, or after success when user may intervene.
  // allowSkipToMsUrls: quant empty but Identifier present — still show teach form + Continue.
  const needsHints = Boolean(summary.needsTableHints) && (stage === 'stage5' || awaitingUpload);
  const allowHints =
    Boolean(summary.allowTableHints) &&
    stage === 'stage5' &&
    (awaitingContinue || awaitingUpload) &&
    !needsHints;

  let teachHtml = '';
  if ((needsHints || allowHints) && jobId) {
    const cand = await fetchTableCandidates(jobId);
    if (!scoutPreviewHtml && !thinkHtml && cand.stage4Scout) {
      scoutPreviewHtml = await resolveStage4ScoutHtml(jobId, cand.stage4Scout);
    }
    if (
      !summary.stage5Thinking?.length &&
      cand.stage5Thinking?.length &&
      !/collection-think/.test(thinkHtml)
    ) {
      thinkHtml += renderStage5ThinkingHtml(cand.stage5Thinking);
    }
    teachHtml = renderTableHintsFormHtml(cand.candidates || [], jobId, {
      mode: allowHints ? 'adjust' : 'teach',
    });
  }

  let contributeHtml = '';
  if (completed) {
    contributeHtml = renderContributeOfferHtml(data);
  } else if (
    (data.offer_contribute || data.offerContribute || summary.offerContribute) &&
    (summary.qratioRowCount || 0) > 0
  ) {
    contributeHtml = renderContributeOfferHtml(data);
  }
  // The contribution invitation is shown as a blue line right above the card.
  const contributeIntroHtml = contributeHtml
    ? `<p class="collection-answer-text collection-contribute-intro" style="white-space:pre-wrap;color:var(--primary);">${CONTRIBUTE_INTRO}</p>`
    : '';

  // Downloads first, then Continue / Upload actions at the bottom-left.
  const downloadsHtml = renderCollectionDownloadsHtml(jobId, data);
  const actionsHtml = renderCollectionActionsHtml(data, event);

  setCollectionPlanThink(panel, thinkHtml);

  let bodyHtml = '';
  const hasSeg = (marker) => String(message || '').includes(marker);

  if (stage === 'stage1' && paperHtml && hasSeg('<<<AFTER_PAPER>>>')) {
    const [before, after] = splitCollectionSegments(message, ['<<<AFTER_PAPER>>>']);
    bodyHtml =
      collectionAnswerBlock(before, colorStyle) +
      paperHtml +
      collectionAnswerBlock(after, colorStyle) +
      downloadsHtml +
      actionsHtml;
  } else if (stage === 'stage3' && metaHtml && hasSeg('<<<AFTER_META>>>')) {
    const [before, after] = splitCollectionSegments(message, ['<<<AFTER_META>>>']);
    bodyHtml =
      collectionAnswerBlock(before, colorStyle) +
      metaHtml +
      collectionAnswerBlock(after, colorStyle) +
      downloadsHtml +
      actionsHtml;
  } else if (
    stage === 'stage4' &&
    scoutPreviewHtml &&
    hasSeg('<<<AFTER_SCOUT>>>')
  ) {
    const [before, after] = splitCollectionSegments(message, ['<<<AFTER_SCOUT>>>']);
    bodyHtml =
      collectionAnswerBlock(before, colorStyle) +
      scoutPreviewHtml +
      downloadsHtml +
      collectionAnswerBlock(after, colorStyle) +
      actionsHtml;
  } else if (
    stage === 'stage5' &&
    awaitingContinue &&
    (summary.qratioRowCount || 0) > 0 &&
    hasSeg('<<<AFTER_QRATIO>>>')
  ) {
    const [summaryText, adjustText, contributeText, continueText] = splitCollectionSegments(
      message,
      ['<<<AFTER_QRATIO>>>', '<<<AFTER_ADJUST>>>', '<<<AFTER_CONTRIBUTE>>>'],
    );
    bodyHtml =
      collectionAnswerBlock(summaryText, colorStyle) +
      qratioPreviewHtml +
      scoutPreviewHtml +
      collectionAnswerBlock(adjustText, colorStyle) +
      teachHtml +
      collectionAnswerBlock(contributeText, colorStyle) +
      contributeHtml +
      collectionAnswerBlock(continueText, colorStyle) +
      downloadsHtml +
      actionsHtml;
  } else {
    // Default: full prose, then widgets (stage2/4/6, parse-empty teach, etc.).
    bodyHtml =
      collectionAnswerBlock(message, colorStyle) +
      paperHtml +
      metaHtml +
      qratioPreviewHtml +
      scoutPreviewHtml +
      msPreviewHtml +
      teachHtml +
      contributeIntroHtml +
      contributeHtml +
      downloadsHtml +
      actionsHtml;
  }

  // Expand the plan panel so users can see execution details before it collapses.
  if (panel && thinkHtml) {
    panel.classList.remove('collapsed');
  }

  contentDiv.innerHTML = bodyHtml;

  if ((needsHints || allowHints) && jobId) {
    bindTableHintsForm(contentDiv, panel, jobId);
    if (panel) panel.dataset.acceptGuidance = '1';
  } else if (panel) {
    delete panel.dataset.acceptGuidance;
  }
  refreshCollectionInputPlaceholder();
  if (completed) {
    bindContributeButtons(contentDiv, panel, data);
  } else if (contentDiv.querySelector('.collection-contribute-yes, .collection-contribute-no')) {
    bindContributeButtons(contentDiv, panel, data);
  }
  bindCollectionActions(contentDiv, panel, data);

  // Collapse the plan once this turn's answer is fully shown (same as research plan).
  if (
    panel &&
    (awaitingContinue ||
      awaitingUpload ||
      completed ||
      rejected ||
      event === 'error' ||
      data.status === 'error')
  ) {
    // Brief delay so the user sees the expanded plan with execution details.
    setTimeout(() => {
      panel.classList.add('collapsed');
    }, 800);
  }

  if (contentDiv.dataset.skipPersist !== '1') {
    const persistKey = `${jobId || ''}|${data.status || ''}|${stage || ''}|${message.slice(0, 80)}`;
    if (contentDiv.dataset.persistKey !== persistKey) {
      contentDiv.dataset.persistKey = persistKey;
      persistCollectionAssistantTurn(message, data).catch(() => {});
    }
  }
}

function resolveCollectionUploadKind(data, filename) {
  const explicit = data?.awaiting_upload || data?.awaitingUpload;
  if (explicit === 'fulltext' || explicit === 'supplementary') return explicit;
  const stage = data?.current_stage || data?.currentStage || '';
  if (stage === 'stage2') return 'fulltext';
  if (stage === 'stage4' || stage === 'stage5') return 'supplementary';
  const byName = classifyUploadKind(filename || '');
  if (byName === 'fulltext' || byName === 'supplementary') return byName;
  return 'supplementary';
}

function renderCollectionActionsHtml(data, event) {
  const status = data?.status || event;
  const summary = data?.summary || {};
  const skipToMs = Boolean(summary.allowSkipToMsUrls);
  if (status === 'awaiting_continue') {
    const continueLabel = skipToMs
      ? 'Continue to MS URLs'
      : 'Continue';
    let html = `<div class="collection-actions">
      <button type="button" class="collection-btn collection-continue-btn"><i class="ri-play-line"></i> ${escapeHtml(continueLabel)}</button>`;
    // Stage5 quant-empty but Identifier present: still allow re-upload / teach tables.
    if (skipToMs || Boolean(summary.needsTableHints)) {
      html += `
      <button type="button" class="collection-file-card collection-upload-btn" data-upload-kind="supplementary" data-accept=".zip,.xlsx,.xls,.csv,.tsv"><i class="ri-upload-2-line"></i><span>Upload supplementary tables</span></button>`;
    }
    html += `</div>`;
    return html;
  }
  if (status === 'awaiting_upload') {
    const kind = resolveCollectionUploadKind(data);
    const label = kind === 'fulltext' ? 'Upload PDF/XML' : 'Upload supplementary tables';
    const accept = kind === 'fulltext' ? '.pdf,.xml' : '.zip,.xlsx,.xls,.csv,.tsv';
    return `<div class="collection-actions">
      <button type="button" class="collection-btn collection-continue-btn"><i class="ri-play-line"></i> Continue</button>
      <button type="button" class="collection-file-card collection-upload-btn" data-upload-kind="${escapeHtml(kind)}" data-accept="${escapeHtml(accept)}"><i class="ri-upload-2-line"></i><span>${escapeHtml(label)}</span></button>
    </div>`;
  }
  if (status === 'error') {
    const stage = data?.current_stage || data?.currentStage || data?.next_stage || data?.nextStage || '';
    if (/^stage[1-6]$/.test(stage)) {
      return `<div class="collection-actions">
      <button type="button" class="collection-btn collection-continue-btn"><i class="ri-play-line"></i> Continue</button>
      <button type="button" class="collection-file-card collection-retry-btn"><i class="ri-chat-1-line"></i><span>Try another paper</span></button>
    </div>`;
    }
  }
  if (status === 'rejected') {
    return `<div class="collection-actions">
      <button type="button" class="collection-btn collection-include-btn"><i class="ri-checkbox-circle-line"></i> Include</button>
      <button type="button" class="collection-file-card collection-retry-btn"><i class="ri-chat-1-line"></i><span>Try another paper</span></button>
    </div>`;
  }
  return '';
}

function bindCollectionActions(contentDiv, panel, data) {
  if (!contentDiv) return;
  const jobId = data.job_id || data.jobId || panel?.dataset?.jobId;
  const continueBtn = contentDiv.querySelector('.collection-continue-btn');
  if (continueBtn && continueBtn.dataset.bound !== '1') {
    continueBtn.dataset.bound = '1';
    continueBtn.addEventListener('click', () => {
      if (!jobId || !panel) return;
      resumeCollectionJob(jobId, panel, contentDiv);
    });
  }
  const uploadBtn = contentDiv.querySelector('.collection-upload-btn');
  if (uploadBtn && uploadBtn.dataset.bound !== '1') {
    uploadBtn.dataset.bound = '1';
    const kind =
      uploadBtn.getAttribute('data-upload-kind') ||
      resolveCollectionUploadKind(data);
    const accept =
      uploadBtn.getAttribute('data-accept') ||
      (kind === 'fulltext' ? '.pdf,.xml' : '.zip,.xlsx,.xls,.csv,.tsv');
    uploadBtn.addEventListener('click', () => {
      if (!jobId || !panel) return;
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = accept;
      if (kind === 'supplementary') input.multiple = true;
      input.addEventListener('change', async () => {
        const picked = input.files ? Array.from(input.files) : [];
        if (!picked.length) return;
        for (const file of picked) {
          const uploadKind = resolveCollectionUploadKind(
            { ...data, awaiting_upload: kind },
            file.name,
          );
          await uploadCollectionFile(jobId, uploadKind, file, panel);
        }
      });
      input.click();
    });
  }
  const retryBtn = contentDiv.querySelector('.collection-retry-btn');
  if (retryBtn && retryBtn.dataset.bound !== '1') {
    retryBtn.dataset.bound = '1';
    retryBtn.addEventListener('click', () => {
      const field = document.getElementById('inputField');
      if (field) {
        field.focus();
        field.placeholder = 'Enter a new PMID, or upload a PDF / quant table…';
      }
    });
  }
  const includeBtn = contentDiv.querySelector('.collection-include-btn');
  if (includeBtn && includeBtn.dataset.bound !== '1') {
    includeBtn.dataset.bound = '1';
    includeBtn.addEventListener('click', () => {
      if (!jobId || !panel) return;
      forceIncludeCollectionJob(jobId, panel, contentDiv);
    });
  }
}

function renderCollectionDownloadsHtml(jobId, data) {
  if (!jobId) return '';
  const summary = data.summary || {};
  const artifacts = summary.artifacts || {};
  const status = data.status;
  const stage = data.current_stage || data.currentStage;
  const cards = [];

  // Stage-scoped downloads: only agent-fetched artifacts (not user uploads).
  const fulltextFromUser = Boolean(
    artifacts.fulltextUserUpload || artifacts.fulltext_user_upload,
  );
  const suppFromUser = Boolean(
    artifacts.supplementaryUserUpload ||
      artifacts.supplementary_user_upload ||
      summary.stage4Source === 'user_upload',
  );

  if (stage === 'stage2' && !fulltextFromUser) {
    if (artifacts.fulltextKind === 'pdf' || artifacts.fulltextKind === 'xml') {
      const label = artifacts.fulltextKind === 'pdf' ? 'Full text PDF' : 'Full text XML';
      cards.push(`<a class="collection-file-card" href="${COLLECTION_URL}/jobs/${jobId}/download/fulltext" target="_blank" rel="noopener">
        <i class="ri-download-2-line"></i><span>${label}</span></a>`);
    }
  }

  if (stage === 'stage3' && (summary.stage3Row || summary.stage3Failed)) {
    cards.push(`<a class="collection-file-card" href="${COLLECTION_URL}/jobs/${jobId}/download/literature_info" target="_blank" rel="noopener">
      <i class="ri-download-2-line"></i><span>Experimental_info.csv</span></a>`);
  }

  if ((stage === 'stage4' || stage === 'stage5') && artifacts.hasSupplementary && !suppFromUser) {
    cards.push(`<a class="collection-file-card" href="${COLLECTION_URL}/jobs/${jobId}/download/supplementary" target="_blank" rel="noopener">
      <i class="ri-download-2-line"></i><span>Supplementary ZIP</span></a>`);
  }

  if (status === 'completed' || stage === 'stage5' || stage === 'stage6' || (summary.qratioRowCount > 0 && (stage === 'stage5' || stage === 'stage6'))) {
    cards.push(`<a class="collection-file-card" href="${COLLECTION_URL}/jobs/${jobId}/download/literature_info" target="_blank" rel="noopener">
      <i class="ri-download-2-line"></i><span>Experimental_info.csv</span></a>`);
    cards.push(`<a class="collection-file-card" href="${COLLECTION_URL}/jobs/${jobId}/download/qratio" target="_blank" rel="noopener">
      <i class="ri-download-2-line"></i><span>Quantitative_data.csv</span></a>`);
  }

  if ((stage === 'stage6' || status === 'completed') && artifacts.hasMsUrls) {
    cards.push(`<a class="collection-file-card" href="${COLLECTION_URL}/jobs/${jobId}/download/ms-urls" target="_blank" rel="noopener">
      <i class="ri-download-2-line"></i><span>MS_URLs.csv</span></a>`);
  }

  if (!cards.length) return '';
  return `<div class="collection-downloads">${cards.join('')}</div>`;
}

const CONTRIBUTE_INTRO =
  'If you are willing, you can contribute these curated results to the qPTM database to help other researchers.';

function renderContributeOfferHtml(data) {
  const offer = data.offer_contribute || data.offerContribute || (data.summary && data.summary.offerContribute);
  const contribution = data.contribution || {};
  const rowCount = (data.summary && data.summary.qratioRowCount) || 0;
  const already = contribution.willing === true || contribution.willing === false;

  // If the user already answered at Stage5, do not show the prompt again at Stage6.
  if (already) return '';
  if (!offer || rowCount <= 0) return '';
  return `<div class="collection-contribute">
    <div class="collection-contribute-title">Contribute to the qPTM database?</div>
    <div class="collection-contribute-body">
      This run curated ${escapeHtml(String(rowCount))} site-level quantitative record(s).
      Sharing them helps other researchers. Choosing “Yes, contribute” only records your intent — it does not write to the live database immediately.
    </div>
    <div class="collection-contribute-actions">
      <button type="button" class="collection-btn collection-contribute-yes"><i class="ri-heart-3-line"></i> Yes, contribute</button>
      <button type="button" class="collection-file-card collection-contribute-no">Not now</button>
    </div>
  </div>`;
}

function bindContributeButtons(contentDiv, panel, data) {
  const yes = contentDiv.querySelector('.collection-contribute-yes');
  const no = contentDiv.querySelector('.collection-contribute-no');
  if (yes && yes.dataset.bound !== '1') {
    yes.dataset.bound = '1';
    yes.addEventListener('click', () => submitContribute(panel || contentDiv, true, contentDiv));
  }
  if (no && no.dataset.bound !== '1') {
    no.dataset.bound = '1';
    no.addEventListener('click', () => submitContribute(panel || contentDiv, false, contentDiv));
  }
}

async function ensureCollectionConversation(title) {
  if (conversationId) return conversationId;
  const res = await fetch(CONVERSATIONS_URL, {
    method: 'POST',
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ title: title || 'Collection' }),
  });
  if (!res.ok) throw new Error(`Create conversation HTTP ${res.status}`);
  const data = await res.json();
  persistConversationId(data.id);
  await loadConversationList();
  return data.id;
}

async function persistCollectionUserTurn(text) {
  if (!text) return;
  const id = await ensureCollectionConversation(text.slice(0, 60));
  await fetch(`${CONVERSATIONS_URL}/${encodeURIComponent(id)}/messages`, {
    method: 'POST',
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({ messages: [{ role: 'user', content: text }] }),
  });
  chatHistory.push({ role: 'user', content: text });
  await loadConversationList();
}

async function persistCollectionAssistantTurn(message, data) {
  if (!message) return;
  const id = await ensureCollectionConversation(
    data?.pmid ? `Collect PMID ${data.pmid}` : 'Collection',
  );
  const meta = {
    collection: {
      job_id: data.job_id || data.jobId,
      pmid: data.pmid,
      status: data.status,
      current_stage: data.current_stage || data.currentStage,
      awaiting_upload: data.awaiting_upload || data.awaitingUpload || null,
      next_stage: data.next_stage || data.nextStage || null,
      stages: data.stages || {},
      summary: data.summary || {},
      offer_contribute: data.offer_contribute,
      contribution: data.contribution,
      message,
    },
  };
  await fetch(`${CONVERSATIONS_URL}/${encodeURIComponent(id)}/messages`, {
    method: 'POST',
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify({
      title: data?.pmid ? `Collect PMID ${data.pmid}` : undefined,
      messages: [{ role: 'assistant', content: message, meta }],
    }),
  });
  chatHistory.push({ role: 'assistant', content: message });
  await loadConversationList();
}

function updateCollectionPanel(panel, data) {
  if (!panel || !data) return;
  if (data.job_id || data.jobId) {
    panel.dataset.jobId = data.job_id || data.jobId;
  }
  const next = data.next_stage || data.nextStage;
  if (next) panel.dataset.nextStage = next;
  const stage = data.current_stage || data.currentStage || '';
  if (stage) panel.dataset.currentStage = stage;
  const status = data.status || '';
  if (status) panel.dataset.status = status;
  // Keep panel expanded while pipeline is running so live thinking is visible.
  if (status === 'running') panel.classList.remove('collapsed');
  const pmidEl = panel.querySelector('.collection-pmid');
  if (pmidEl) {
    const summary = data.summary || {};
    const accessions = summary.accessions || summary.stage6?.accessions;
    if ((data.resolve_urls || summary.resolveUrls) && Array.isArray(accessions) && accessions.length) {
      pmidEl.textContent = accessions.join('; ');
    } else if (data.pmid && stage === 'stage1') {
      pmidEl.textContent = `PMID ${data.pmid}`;
    } else if (data.pmid && (data.resolve_urls || summary.resolveUrls)) {
      pmidEl.textContent = String(data.pmid);
    } else {
      pmidEl.textContent = '';
    }
  }
  const titleEl = panel.querySelector('.collection-plan-title');
  if (titleEl && (data.resolve_urls || (data.summary || {}).resolveUrls)) {
    titleEl.textContent = 'MS Download URLs';
  }
  renderCollectionPlanSteps(panel, data);
}

/** Latest collection turn that can accept Stage5 free-text guidance from the input box. */
function findCollectionGuidanceTarget() {
  const panels = [...document.querySelectorAll('.collection-panel[data-job-id]')];
  for (let i = panels.length - 1; i >= 0; i--) {
    const panel = panels[i];
    const jobId = panel.dataset.jobId;
    if (!jobId) continue;
    const body = panel.parentElement;
    const content = body?.querySelector('.msg-content');
    const teach = content?.querySelector('.collection-teach:not(.is-stale)');
    const stage = panel.dataset.currentStage || '';
    const status = panel.dataset.status || '';
    const accept =
      panel.dataset.acceptGuidance === '1' ||
      Boolean(teach) ||
      ((stage === 'stage5' || stage === 'stage6') &&
        ['awaiting_continue', 'awaiting_upload'].includes(status));
    if (accept) return { jobId, panel, contentDiv: content || null };
  }
  if (activeCollectionPanel?.dataset?.jobId) {
    const stage = activeCollectionPanel.dataset.currentStage || '';
    if (stage === 'stage5' || stage === 'stage6') {
      return {
        jobId: activeCollectionPanel.dataset.jobId,
        panel: activeCollectionPanel,
        contentDiv: activeCollectionPanel.parentElement?.querySelector('.msg-content') || null,
      };
    }
  }
  return null;
}

function refreshCollectionInputPlaceholder() {
  if (!inputField) return;
  const target = findCollectionGuidanceTarget();
  if (target) {
    inputField.placeholder =
      'Describe table/column guidance to re-parse (e.g. STY is amino acid, AA is position)…';
  } else {
    inputField.placeholder =
      'Ask about a PTM site, or upload a pdf file for literature collection...';
  }
}

async function submitContribute(panel, willing, contentDivOverride) {
  const jobId = panel?.dataset?.jobId || panel?.closest?.('.collection-panel')?.dataset?.jobId;
  if (!jobId) return;
  const contentDiv =
    contentDivOverride ||
    panel?.parentElement?.querySelector('.msg-content') ||
    null;
  const buttons = (contentDiv || panel).querySelectorAll('.collection-contribute button');
  buttons.forEach((b) => { b.disabled = true; });
  try {
    const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/contribute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ willing }),
    });
    if (!res.ok) throw new Error(`Contribute HTTP ${res.status}`);
    const data = await res.json();
    if (panel?.classList?.contains('collection-panel')) updateCollectionPanel(panel, data);
    if (contentDiv) {
      contentDiv.dataset.skipPersist = '1';
      await renderCollectionMessage(contentDiv, data, data.status || 'completed', panel);
      delete contentDiv.dataset.skipPersist;
    }
  } catch (err) {
    buttons.forEach((b) => { b.disabled = false; });
    alert(err.message || 'Submit failed');
  }
}

const STAGE_THINKING_META = {
  stage1: { key: 'stage1Thinking', title: 'Abstract screening', icon: 'ri-file-search-line', label: 'Screening paper for quantitative PTM relevance…' },
  stage2: { key: 'stage2Thinking', title: 'Full text acquisition', icon: 'ri-file-text-line', label: 'Acquiring full text…' },
  stage3: { key: 'stage3Thinking', title: 'Experimental metadata', icon: 'ri-flask-line', label: 'Extracting experimental metadata…' },
  stage4: { key: 'stage4Thinking', title: 'Supplementary scout', icon: 'ri-folder-zip-line', label: 'Scouting supplementary tables…' },
  stage5: { key: 'stage5Thinking', title: 'Quantitative table parsing', icon: 'ri-brain-line', label: 'Parsing quantitative tables…' },
  stage6: { key: 'stage6Thinking', title: 'MS repository URLs', icon: 'ri-link', label: 'Resolving MS repository download URLs…' },
};

function renderGenericThinkingStepsHtml(steps, opts = {}) {
  if (!Array.isArray(steps) || !steps.length) return '';
  const live = opts.live === true;
  const title = opts.title || 'Processing';
  const icon = opts.icon || 'ri-loader-4-line';
  const items = steps
    .map((s) => {
      return `<li class="collection-think-step-item"><span class="collection-think-step">${escapeHtml(String(s.step || ''))}</span>
        <span class="collection-think-msg">${escapeHtml(String(s.message || ''))}</span>
      </li>`;
    })
    .join('');
  return `
    <div class="collection-think ${live ? 'is-live' : ''}">
      <div class="collection-think-title"><i class="${icon}"></i> ${escapeHtml(title)}${live ? ' <span class="collection-live-dot"></span>' : ''}</div>
      <ol class="collection-think-log">${items}</ol>
    </div>`;
}

function renderGenericLiveThinking(contentDiv, data, panel) {
  if (!data) return;
  const summary = data.summary || {};
  const stage = data.current_stage || data.currentStage || '';
  const meta = STAGE_THINKING_META[stage];
  if (!meta) return;
  const steps = summary[meta.key];
  if (!Array.isArray(steps) || !steps.length) return;
  if (data.status !== 'running') return;

  const planPanel = panel || contentDiv?.parentElement?.querySelector('.collection-panel') || activeCollectionPanel;
  // Expand the panel so live thinking steps are visible.
  if (planPanel) planPanel.classList.remove('collapsed');
  updateCollectionPanel(planPanel, data);

  // Stage5 has its own detailed renderer; others use the generic one.
  const html = stage === 'stage5'
    ? renderStage5ThinkingHtml(steps, { live: true })
    : renderGenericThinkingStepsHtml(steps, { title: meta.title, icon: meta.icon, live: true });

  setCollectionPlanThink(planPanel, html);

  if (contentDiv) {
    if (!contentDiv.querySelector('.msg-content-loading')) {
      contentDiv.innerHTML = '';
    }
    showContentLoading(contentDiv, meta.label);
  }

  const log = planPanel?.querySelector('.collection-think-log');
  if (log) log.scrollTop = log.scrollHeight;
  chatArea.scrollTop = chatArea.scrollHeight;
}

function beginCollectionTurn(jobId, pmid, seedData) {
  if (welcome) welcome.style.display = 'none';
  const msg = document.createElement('div');
  msg.className = 'message assistant';
  const body = document.createElement('div');
  body.className = 'assistant-body';
  const panel = createCollectionPanelEl(jobId, seedData);
  if (pmid) {
    const stage = seedData?.current_stage || seedData?.currentStage;
    if (!stage || stage === 'stage1') {
      const pmidEl = panel.querySelector('.collection-pmid');
      if (pmidEl) pmidEl.textContent = `PMID ${pmid}`;
    }
  }
  if (seedData) {
    const stage = seedData.current_stage || seedData.currentStage;
    if (stage && stage !== 'stage1') {
      panel.dataset.expectedStage = stage;
      panel.dataset.planModeLocked = 'focus';
    }
    updateCollectionPanel(panel, { ...seedData, pmid: pmid || seedData.pmid, job_id: jobId });
  }
  const contentDiv = document.createElement('div');
  contentDiv.className = 'msg-content is-loading';
  body.appendChild(panel);
  body.appendChild(contentDiv);
  msg.appendChild(body);
  chatArea.appendChild(msg);
  showContentLoading(contentDiv, 'Starting collection pipeline...');
  activeCollectionPanel = panel;
  chatArea.scrollTop = chatArea.scrollHeight;
  return { panel, contentDiv };
}

async function parseSseBufferLines(lines, onEvent, state = { currentEvent: null }) {
  for (const line of lines) {
    if (line.startsWith('event: ')) {
      state.currentEvent = line.substring(7).trim();
    } else if (line.startsWith('data: ') && state.currentEvent) {
      const data = JSON.parse(line.substring(6));
      const event = state.currentEvent;
      state.currentEvent = null;
      // onEvent may return false / 'stop' to end the stream early.
      const result = await onEvent(event, data);
      if (result === false || result === 'stop') return true;
    }
  }
  return false;
}

async function parseSseStream(response, onEvent) {
  if (!response.body) return;
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';
  const state = { currentEvent: null };
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) {
        buffer += decoder.decode();
        if (buffer) {
          await parseSseBufferLines(buffer.split('\n'), onEvent, state);
          buffer = '';
        }
        break;
      }
      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop() || '';
      const stop = await parseSseBufferLines(lines, onEvent, state);
      if (stop) {
        // Stream is locked by this reader — cancel the reader, not response.body.
        try {
          await reader.cancel();
        } catch (_) {
          /* ignore */
        }
        break;
      }
    }
  } catch (err) {
    if (err?.name === 'AbortError') return;
    throw err;
  }
}

async function streamCollectionJob(jobId, panel, contentDiv) {
  const signal = currentAbortController?.signal;
  let terminal = false;

  const handleTerminal = async (event, data) => {
    if (terminal) return;
    terminal = true;
    const arrived = collectionDisplayStage(
      { ...data, job_id: data.job_id || jobId },
      panel,
    );
    const exp = panel.dataset.expectedStage;
    const aIdx = COLLECTION_STAGE_DEFS.findIndex((d) => d.id === arrived);
    const eIdx = COLLECTION_STAGE_DEFS.findIndex((d) => d.id === exp);
    if (!exp || eIdx < 0 || aIdx >= eIdx) {
      delete panel.dataset.expectedStage;
    }
    try {
      await renderCollectionMessage(
        contentDiv,
        { ...data, job_id: data.job_id || jobId },
        event,
        panel,
      );
    } catch (err) {
      // Never surface raw "Failed to fetch" as the only Stage4/5 answer — keep prose + actions.
      hideContentLoading(contentDiv);
      const fallback = data?.message || 'Collection paused. Click Continue to retry, or refresh this conversation.';
      contentDiv.innerHTML =
        `<p style="color:#c0392b;font-size:13px;">${escapeHtml(err?.message || 'Failed to load stage widgets')}</p>` +
        collectionAnswerBlock(fallback) +
        renderCollectionDownloadsHtml(jobId, { ...data, job_id: jobId }) +
        renderCollectionActionsHtml({ ...data, job_id: jobId }, event);
      bindCollectionActions(contentDiv, panel, { ...data, job_id: jobId });
    }
    chatArea.scrollTop = chatArea.scrollHeight;
  };

  const pollOnce = async () => {
    try {
      const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}`, { signal });
      if (!res.ok) return;
      const data = await res.json();
      const status = data.status || '';
      updateCollectionPanel(panel, data);
      if (['awaiting_continue', 'awaiting_upload', 'completed', 'rejected', 'error'].includes(status)) {
        const mapped =
          status === 'completed' ? 'done' : status === 'error' ? 'error' : status;
        await handleTerminal(mapped, data);
        return;
      }
      if (!terminal) {
        const stage = data.current_stage || data.currentStage || '';
        const meta = STAGE_THINKING_META[stage];
        // Always expand panel while running so the user sees live progress.
        if (panel) panel.classList.remove('collapsed');
        if (meta && Array.isArray(data.summary?.[meta.key]) && data.summary[meta.key].length) {
          renderGenericLiveThinking(contentDiv, { ...data, job_id: data.job_id || jobId }, panel);
        } else {
          showContentLoading(contentDiv, collectionRunningLabel(data));
        }
      }
    } catch (_) {
      /* ignore transient poll errors */
    }
  };

  // Parallel poll: recovers when SSE is buffered/dropped by the reverse proxy.
  const pollTimer = setInterval(() => {
    if (!terminal && !signal?.aborted) pollOnce();
  }, 4000);

  try {
    let response = null;
    try {
      response = await fetch(`${COLLECTION_URL}/jobs/${jobId}/stream`, { signal });
    } catch (err) {
      if (err?.name === 'AbortError') return;
      // SSE open failed — fall through to poll recovery (do not throw "Failed to fetch").
      response = null;
    }

    if (response && response.ok) {
      try {
        await parseSseStream(response, async (event, data) => {
          if (terminal) return;
          updateCollectionPanel(panel, data);
          const status = data?.status || '';
          // Status payloads can already be terminal (proxy may drop the follow-up event).
          if (
            event === 'status' &&
            ['awaiting_continue', 'awaiting_upload', 'completed', 'rejected', 'error'].includes(status)
          ) {
            const mapped =
              status === 'completed' ? 'done' : status === 'error' ? 'error' : status;
            await handleTerminal(mapped, data);
            return 'stop';
          }
          if (event === 'status') {
            const stage = data.current_stage || data.currentStage || '';
            const meta = STAGE_THINKING_META[stage];
            // Always expand panel while running so the user sees live progress.
            if (panel) panel.classList.remove('collapsed');
            if (meta && Array.isArray(data.summary?.[meta.key]) && data.summary[meta.key].length) {
              renderGenericLiveThinking(contentDiv, { ...data, job_id: data.job_id || jobId }, panel);
            } else {
              showContentLoading(contentDiv, collectionRunningLabel(data));
            }
            return;
          }
          if (['awaiting_continue', 'awaiting_upload', 'done', 'rejected', 'error'].includes(event)) {
            await handleTerminal(event, data);
            return 'stop';
          }
        });
      } catch (err) {
        if (err?.name === 'AbortError') return;
        // Proxy/network dropped the SSE mid-run — recover via job status polling.
      }
    }
  } finally {
    clearInterval(pollTimer);
  }

  if (signal?.aborted) return;

  // Recover after SSE drop / open failure: poll until terminal or a few retries.
  for (let i = 0; i < 8 && !terminal && !signal?.aborted; i++) {
    await pollOnce();
    if (terminal) break;
    await new Promise((r) => setTimeout(r, 1500));
  }
  if (!terminal && !signal?.aborted) {
    hideContentLoading(contentDiv);
    contentDiv.innerHTML =
      '<p style="color:var(--text-muted);">Collection stream ended unexpectedly. Click Continue to retry, or refresh the conversation.</p>';
  }
}

function collectionRunningLabel(data) {
  const stage = data?.current_stage || data?.currentStage || '';
  const labels = {
    stage1: 'Screening paper for quantitative PTM relevance…',
    stage2: 'Acquiring full text…',
    stage3: 'Extracting experimental metadata…',
    stage4: 'Scouting supplementary tables…',
    stage5: 'Parsing quantitative tables…',
    stage6: 'Resolving MS repository URLs…',
  };
  if (labels[stage]) return labels[stage];
  const msg = (data?.message || '').trim();
  if (msg && msg.length < 80 && !/<<<|Detected PTM|This paper appears/i.test(msg)) return msg;
  return 'Running collection…';
}

async function resumeCollectionJob(jobId, panel, contentDivFromBtn) {
  if (isStreaming) return;
  setSendButtonToStop();
  const abortController = new AbortController();
  currentAbortController = abortController;
  // Freeze prior answer-box actions so Continue isn't clicked twice.
  const prevContent =
    contentDivFromBtn ||
    panel?.parentElement?.querySelector('.msg-content') ||
    null;
  if (prevContent) {
    prevContent.querySelectorAll('.collection-actions button').forEach((btn) => {
      btn.disabled = true;
    });
  }
  // Keep prior stage message visible; start a new assistant bubble for the next stage.
  const pmidText = panel.querySelector('.collection-pmid')?.textContent || '';
  const pmid = pmidText.replace(/^PMID\s+/i, '').trim() || null;
  persistCollectionUserTurn('Continue').catch(() => {});
  addMessage('user', 'Continue');
  // Infer next stage: prefer server nextStage stored on the panel, else +1.
  const prevStage = panel.dataset.currentStage || '';
  const stageIdx = COLLECTION_STAGE_DEFS.findIndex((d) => d.id === prevStage);
  const nextHint =
    panel.dataset.nextStage ||
    (stageIdx >= 0 && stageIdx < COLLECTION_STAGE_DEFS.length - 1
      ? COLLECTION_STAGE_DEFS[stageIdx + 1].id
      : prevStage || 'stage2');
  const { panel: nextPanel, contentDiv } = beginCollectionTurn(jobId, pmid, {
    current_stage: nextHint,
    next_stage: nextHint,
    status: 'running',
    stages: {},
  });
  nextPanel.dataset.expectedStage = nextHint;
  nextPanel.dataset.planModeLocked = 'focus';
  nextPanel.classList.remove('collapsed');
  showContentLoading(contentDiv, 'Continuing collection...');
  try {
    const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ resume_from: nextHint }),
      signal: abortController.signal,
    });
    if (!res.ok) throw new Error(`Resume HTTP ${res.status}`);
    const data = await res.json();
    // Prefer the next-step hint over a lagging current_stage from the API.
    updateCollectionPanel(nextPanel, {
      ...data,
      current_stage: nextHint,
      currentStage: nextHint,
      next_stage: nextHint,
      nextStage: nextHint,
      status: 'running',
    });
    await streamCollectionJob(jobId, nextPanel, contentDiv);
  } catch (err) {
    if (err.name === 'AbortError') {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = '<p style="color:var(--text-muted);font-style:italic;">Collection stopped.</p>';
      return;
    }
    hideContentLoading(contentDiv);
    contentDiv.innerHTML = `<p style="color:#c0392b;">${escapeHtml(err.message)}</p>`;
  } finally {
    if (currentAbortController === abortController) currentAbortController = null;
    setSendButtonToSend();
  }
}

/** Override Stage-1 exclude and continue the pipeline for this PMID. */
async function forceIncludeCollectionJob(jobId, panel, contentDivFromBtn) {
  if (isStreaming) return;
  setSendButtonToStop();
  const abortController = new AbortController();
  currentAbortController = abortController;
  const prevContent =
    contentDivFromBtn ||
    panel?.parentElement?.querySelector('.msg-content') ||
    null;
  if (prevContent) {
    prevContent.querySelectorAll('.collection-actions button').forEach((btn) => {
      btn.disabled = true;
    });
  }
  const pmidText = panel.querySelector('.collection-pmid')?.textContent || '';
  const pmid = pmidText.replace(/^PMID\s+/i, '').trim() || null;
  persistCollectionUserTurn('Include').catch(() => {});
  addMessage('user', 'Include');
  const { panel: nextPanel, contentDiv } = beginCollectionTurn(jobId, pmid, {
    current_stage: 'stage1',
    next_stage: 'stage2',
    status: 'running',
    stages: {},
  });
  nextPanel.dataset.expectedStage = 'stage2';
  nextPanel.dataset.planModeLocked = 'focus';
  nextPanel.classList.remove('collapsed');
  showContentLoading(contentDiv, 'Including paper and continuing collection…');
  try {
    const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/resume`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ force_include: true, resume_from: 'stage1' }),
      signal: abortController.signal,
    });
    if (!res.ok) throw new Error(`Include HTTP ${res.status}`);
    const data = await res.json();
    updateCollectionPanel(nextPanel, {
      ...data,
      status: 'running',
    });
    await streamCollectionJob(jobId, nextPanel, contentDiv);
  } catch (err) {
    if (err.name === 'AbortError') {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = '<p style="color:var(--text-muted);font-style:italic;">Collection stopped.</p>';
      return;
    }
    hideContentLoading(contentDiv);
    contentDiv.innerHTML = `<p style="color:#c0392b;">${escapeHtml(err.message)}</p>`;
  } finally {
    if (currentAbortController === abortController) currentAbortController = null;
    setSendButtonToSend();
  }
}

async function uploadCollectionFile(jobId, uploadType, file, panel) {
  if (isStreaming) return;
  const kind = resolveCollectionUploadKind(
    {
      awaiting_upload: uploadType,
      current_stage: panel?.dataset?.currentStage,
    },
    file?.name,
  );
  if (kind !== 'fulltext' && kind !== 'supplementary') {
    alert('Please upload a PDF/XML (full text) or ZIP/Excel/CSV (supplementary tables).');
    return;
  }
  setSendButtonToStop();
  const abortController = new AbortController();
  currentAbortController = abortController;
  const prevContent = panel?.parentElement?.querySelector('.msg-content');
  if (prevContent) {
    prevContent.querySelectorAll('.collection-actions button').forEach((btn) => {
      btn.disabled = true;
    });
  }
  const userText = `Uploaded ${kind === 'fulltext' ? 'full text' : 'supplementary'}: ${file.name}`;
  const userMsgEl = addMessage('user', userText);
  userMsgEl.insertAdjacentHTML('beforeend', renderUploadedFilesHtml([file]));
  persistCollectionUserTurn(userText).catch(() => {});

  // Keep prior prompt visible; show upload result in a new assistant bubble.
  const pmidText = panel.querySelector('.collection-pmid')?.textContent || '';
  const pmid = pmidText.replace(/^PMID\s+/i, '').trim() || null;
  const { panel: nextPanel, contentDiv } = beginCollectionTurn(jobId, pmid, {
    current_stage: panel.dataset.currentStage || (kind === 'fulltext' ? 'stage2' : 'stage4'),
    status: 'running',
    stages: {},
  });
  showContentLoading(contentDiv, 'Uploading file...');

  if (!pendingFiles.some((f) => pendingFileKey(f) === pendingFileKey(file))) {
    pendingFiles.push(file);
  }
  setPendingFilesUploadState([file], 'uploading', 0);

  try {
    const fd = new FormData();
    fd.append('upload_type', kind);
    fd.append('file', file);
    const data = await uploadFormData(`${COLLECTION_URL}/jobs/${jobId}/upload`, fd, {
      onProgress: (ratio) => setPendingFilesUploadState([file], 'uploading', ratio * 100),
      signal: abortController.signal,
    });
    setPendingFilesUploadState([file], 'done', 100);
    updateCollectionPanel(nextPanel, data);
    await renderCollectionMessage(contentDiv, { ...data, job_id: jobId }, data.status || 'awaiting_continue', nextPanel);
  } catch (err) {
    if (err.name === 'AbortError') {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = '<p style="color:var(--text-muted);font-style:italic;">Upload stopped.</p>';
      return;
    }
    setPendingFilesUploadState([file], 'error', 100);
    hideContentLoading(contentDiv);
    contentDiv.innerHTML = `<p style="color:#c0392b;">${escapeHtml(err.message)}</p>`;
  } finally {
    setTimeout(clearPendingFiles, 450);
    if (currentAbortController === abortController) currentAbortController = null;
    setSendButtonToSend();
  }
}

async function startCollectionFlow(message, files) {
  currentWorkflowState = null;
  currentActivityTimeline = null;
  currentThinkingTools = null;
  currentPlanPanel = null;
  if (typeof syncWorkflowSidebar === 'function') syncWorkflowSidebar();
  setSendButtonToStop();
  const abortController = new AbortController();
  currentAbortController = abortController;
  const userText = message || (files.length ? 'Uploaded files' : 'Data collection');
  const userMsgEl = addMessage('user', userText);
  if (files.length) {
    userMsgEl.insertAdjacentHTML('beforeend', renderUploadedFilesHtml(files));
  }
  persistCollectionUserTurn(userText).catch(() => {});

  const looksResolveUrls =
    !files.length &&
    /(?<![A-Za-z0-9_])(?:PXD|IPX|JPST|MSV|PDC)\d+(?![A-Za-z0-9_])/i.test(message || '') &&
    /(download|url|link|pride|iprox|jpost|massive|cptac|下载|链接|质谱)/i.test(
      message || '',
    );
  const { panel, contentDiv } = beginCollectionTurn(
    'pending',
    null,
    looksResolveUrls
      ? { current_stage: 'stage6', status: 'running', stages: {} }
      : undefined,
  );
  showContentLoading(
    contentDiv,
    looksResolveUrls
      ? 'Resolving MS repository download URLs…'
      : files.length
        ? 'Reading upload and resolving PMID…'
        : 'Starting collection…',
  );
  try {
    const fd = new FormData();
    if (message) fd.append('message', message);
    let fulltextAdded = false;
    const uploadingFiles = [];
    files.forEach((file) => {
      const kind = classifyUploadKind(file.name);
      if (kind === 'fulltext' && !fulltextAdded) {
        fd.append('fulltext', file);
        fulltextAdded = true;
        uploadingFiles.push(file);
      } else if (kind === 'supplementary') {
        // Append every tabular file so site + proteome tables all reach Stage4/5.
        fd.append('supplementary', file);
        uploadingFiles.push(file);
      }
    });

    if (uploadingFiles.length) {
      setPendingFilesUploadState(uploadingFiles, 'uploading', 0);
    }

    const data = await uploadFormData(`${COLLECTION_URL}/jobs`, fd, {
      onProgress: (ratio) => {
        if (uploadingFiles.length) {
          setPendingFilesUploadState(uploadingFiles, 'uploading', ratio * 100);
        }
      },
      signal: abortController.signal,
    });

    if (uploadingFiles.length) {
      setPendingFilesUploadState(uploadingFiles, 'done', 100);
    }

    panel.dataset.jobId = data.job_id;
    updateCollectionPanel(panel, data);

    if (data.needs_pmid) {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = `<p style="color:#c0392b;">${escapeHtml(data.message || 'Could not resolve PMID.')}</p>
        <p style="color:var(--text-muted);margin-top:8px;">Tip: enter <code>PMID 12345678</code> in the input box, then upload the PDF again — or rename the file to <code>12345678.pdf</code>.</p>`;
      const field = document.getElementById('inputField');
      if (field) {
        field.focus();
        field.placeholder = 'Enter PMID (e.g. 38670996), then re-upload the PDF…';
      }
      return;
    }

    if (data.status === 'error') {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = `<p style="color:#c0392b;">${escapeHtml(data.message || data.error || 'Collection failed')}</p>`;
      return;
    }

    if (['awaiting_continue', 'awaiting_upload', 'completed', 'rejected'].includes(data.status)) {
      await renderCollectionMessage(contentDiv, data, data.status, panel);
      return;
    }

    // Job accepted — replace PMID-resolve spinner with stage progress before SSE.
    showContentLoading(
      contentDiv,
      data.pmid
        ? `PMID ${data.pmid} resolved. ${collectionRunningLabel(data)}`
        : collectionRunningLabel(data),
    );
    await streamCollectionJob(data.job_id, panel, contentDiv);
  } catch (err) {
    if (err.name === 'AbortError') {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = '<p style="color:var(--text-muted);font-style:italic;">Collection stopped.</p>';
      return;
    }
    if (files.length) setPendingFilesUploadState(files, 'error', 100);
    hideContentLoading(contentDiv);
    contentDiv.innerHTML = `<p style="color:#c0392b;">Collection error: ${escapeHtml(err.message)}</p>
      <p style="font-size:13px;color:var(--text-muted);">Make sure the qPTM Agent backend is running.</p>`;
  } finally {
    setTimeout(clearPendingFiles, 450);
    if (currentAbortController === abortController) currentAbortController = null;
    setSendButtonToSend();
    inputField.focus();
  }
}

function persistConversationId(id) {
  conversationId = id || null;
  if (id) localStorage.setItem(CONV_STORAGE_KEY, id);
  else localStorage.removeItem(CONV_STORAGE_KEY);
}

async function loadConversationList() {
  try {
    const res = await fetch(CONVERSATIONS_URL, { headers: apiHeaders() });
    if (!res.ok) return;
    const data = await res.json();
    conversationList = data.conversations || [];
    renderSidebar();
  } catch (err) {
    console.warn('Failed to load conversation list:', err);
  }
}

function renderSidebar() {
  if (!sidebarHistory) return;
  if (!conversationList.length) {
    sidebarHistory.innerHTML = '<div class="sidebar-empty">No history yet</div>';
    return;
  }
  sidebarHistory.innerHTML = '';
  conversationList.forEach((conv) => {
    const item = document.createElement('div');
    item.className = 'sidebar-item' + (conv.id === conversationId ? ' active' : '');
    item.title = conv.title || 'Untitled';

    const title = document.createElement('span');
    title.className = 'sidebar-item-title';
    title.textContent = conv.title || 'Untitled';

    const delBtn = document.createElement('button');
    delBtn.type = 'button';
    delBtn.className = 'sidebar-item-delete';
    delBtn.title = 'Delete';
    delBtn.setAttribute('aria-label', 'Delete conversation');
    delBtn.innerHTML = '<i class="ri-delete-bin-line"></i>';
    delBtn.addEventListener('click', (e) => {
      e.preventDefault();
      e.stopPropagation();
      deleteConversation(conv.id);
    });

    item.appendChild(title);
    item.appendChild(delBtn);
    item.addEventListener('click', () => loadConversation(conv.id));
    sidebarHistory.appendChild(item);
  });
}

async function deleteConversation(id) {
  if (!id || isStreaming) return;
  if (!window.confirm('Delete this conversation from history?')) return;
  try {
    const res = await fetch(`${CONVERSATIONS_URL}/${encodeURIComponent(id)}`, {
      method: 'DELETE',
      headers: apiHeaders(),
    });
    if (!res.ok) {
      console.warn('Failed to delete conversation:', res.status);
      return;
    }
    conversationList = conversationList.filter((c) => c.id !== id);
    if (conversationId === id) {
      persistConversationId(null);
      const oldSid = sessionId;
      sessionId = null;
      clearChatArea();
      resetRuntimeSession(oldSid);
    }
    renderSidebar();
  } catch (err) {
    console.warn('Failed to delete conversation:', err);
  }
}

function clearChatArea() {
  chatArea.querySelectorAll('.message').forEach((el) => el.remove());
  if (welcome) welcome.style.display = '';
  chatHistory = [];
  currentThinkingTools = null;
  currentPlanPanel = null;
  currentActivityTimeline = null;
  currentWorkflowState = null;
  activeCollectionPanel = null;
  pendingClarificationState = null;
  if (typeof syncWorkflowSidebar === 'function') syncWorkflowSidebar();
}

function startNewConversation() {
  if (isStreaming) return;
  const oldSid = sessionId;
  const oldCid = conversationId;
  persistConversationId(null);
  sessionId = null;
  const oldKey = sessionStorageKey(oldCid);
  if (oldKey) sessionStorage.removeItem(oldKey);
  clearChatArea();
  renderSidebar();
  resetRuntimeSession(oldSid);
  inputField.focus();
}

async function loadConversation(id, { force = false } = {}) {
  if (isStreaming) return;
  if (!force && id === conversationId && chatArea.querySelector('.message')) return;
  try {
    const res = await fetch(`${CONVERSATIONS_URL}/${encodeURIComponent(id)}`, {
      headers: apiHeaders(),
    });
    if (!res.ok) {
      if (res.status === 403 || res.status === 404) persistConversationId(null);
      return;
    }
    const data = await res.json();
    persistConversationId(data.id);
    sessionId = restoreSessionForConversation(data.id);
    clearChatArea();
    if (welcome) welcome.style.display = 'none';
    chatHistory = [];
    (data.messages || []).forEach((msg) => {
      if (msg.role === 'assistant') {
        addStoredAssistantMessage(msg.content, msg.meta);
      } else {
        addMessage(msg.role, msg.content);
      }
      chatHistory.push({ role: msg.role, content: msg.content });
    });
    await refreshStoredCollectionJobs(data.messages || []);
    renderSidebar();
    chatArea.scrollTop = chatArea.scrollHeight;
    refreshCollectionInputPlaceholder();
  } catch (err) {
    console.warn('Failed to load conversation:', err);
  }
}

/**
 * After restoring a conversation, refresh collection job states from the live
 * job files. A stage6 result is normally persisted by the browser tab that ran
 * it, but if that tab was closed mid-run the final message is never stored —
 * so re-sync the tail of the conversation with the actual job state.
 */
async function refreshStoredCollectionJobs(messages) {
  const lastByJob = new Map();
  (messages || []).forEach((msg) => {
    const c = msg?.meta?.collection;
    if (!c?.job_id) return;
    lastByJob.set(c.job_id, {
      lastStage: c.current_stage || c.currentStage || '',
      lastStatus: c.status || '',
      msgMeta: c,
    });
  });
  for (const [jobId, info] of lastByJob) {
    try {
      const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}`);
      if (!res.ok) continue;
      const data = await res.json();
      const status = data.status || '';
      const pauseOrDone = ['completed', 'rejected', 'error', 'awaiting_continue', 'awaiting_upload'].includes(
        status,
      );
      if (!pauseOrDone) continue;
      // Already reflected by the last stored collection message.
      if (info.lastStatus === status && ['completed', 'rejected', 'error'].includes(status)) continue;
      // For pause states, re-render live widgets (supp-preview / teach form) in place when possible.
      if (['awaiting_continue', 'awaiting_upload'].includes(status)) {
        const panels = [...document.querySelectorAll(`.collection-panel[data-job-id="${jobId}"]`)];
        const panel = panels[panels.length - 1];
        const contentDiv = panel?.parentElement?.querySelector('.msg-content');
        if (panel && contentDiv) {
          contentDiv.dataset.skipPersist = '1';
          const event =
            status === 'awaiting_upload' ? 'awaiting_upload' : 'awaiting_continue';
          await renderCollectionMessage(contentDiv, { ...data, job_id: jobId }, event, panel);
          continue;
        }
      }
      if (!['completed', 'rejected', 'error'].includes(status)) continue;
      if (info.lastStatus === status) continue;
      const msg = document.createElement('div');
      msg.className = 'message assistant';
      const body = document.createElement('div');
      body.className = 'assistant-body';
      const panel = createCollectionPanelEl(jobId, {
        current_stage: data.current_stage || 'stage6',
        status: 'running',
        stages: data.stages || {},
      });
      const contentDiv = document.createElement('div');
      contentDiv.className = 'msg-content';
      contentDiv.dataset.skipPersist = '1';
      body.appendChild(panel);
      body.appendChild(contentDiv);
      msg.appendChild(body);
      chatArea.appendChild(msg);
      const event = status === 'completed' ? 'done' : status;
      await renderCollectionMessage(contentDiv, { ...data, job_id: jobId }, event, panel);
      if (data.message) chatHistory.push({ role: 'assistant', content: data.message });
    } catch (_) {
      /* ignore */
    }
  }
}

/** Re-render the live assistant bubble from the persisted conversation (same path as page refresh). */
async function refreshAssistantContentFromStore(contentDiv, { attempts = 4 } = {}) {
  if (!conversationId || !contentDiv) return;
  for (let i = 0; i < attempts; i++) {
    try {
      const res = await fetch(`${CONVERSATIONS_URL}/${encodeURIComponent(conversationId)}`, {
        headers: apiHeaders(),
      });
      if (!res.ok) return;
      const data = await res.json();
      const msgs = data.messages || [];
      const last = [...msgs].reverse().find((m) => m.role === 'assistant');
      if (!last?.content) {
        await new Promise((r) => setTimeout(r, 120 * (i + 1)));
        continue;
      }
      contentDiv.classList.remove('is-loading', 'is-streaming');
      const displayText = stripTrailingInvite(last.content);
      contentDiv.innerHTML = renderMarkdown(displayText);
      attachMessageActions(contentDiv, last.content);
      const qs = last.meta?.follow_ups?.length
        ? last.meta.follow_ups
        : extractNextStepQuestions(last.content);
      mountFollowUpPanel(contentDiv.closest('.assistant-body'), qs, detectLangFromText(last.content));
      if (last.meta?.workflow) {
        const body = contentDiv.closest('.assistant-body');
        if (body && !body.querySelector('.agent-workflow')) {
          body.insertBefore(mountWorkflowPanel(last.meta.workflow), contentDiv);
        }
      }
      if (chatHistory.length && chatHistory[chatHistory.length - 1].role === 'assistant') {
        chatHistory[chatHistory.length - 1].content = last.content;
      } else {
        chatHistory.push({ role: 'assistant', content: last.content });
      }
      chatArea.scrollTop = chatArea.scrollHeight;
      return;
    } catch (err) {
      console.warn('refreshAssistantContentFromStore failed:', err);
      await new Promise((r) => setTimeout(r, 120 * (i + 1)));
    }
  }
}

const messageRawText = new WeakMap();

function attachMessageActions(contentDiv, rawText) {
  if (!contentDiv || contentDiv.querySelector('.msg-actions')) return;
  const actions = document.createElement('div');
  actions.className = 'msg-actions';
  const text = rawText || '';
  messageRawText.set(actions, text);
  // Keep a short attribute fallback for tiny answers; large text stays in WeakMap.
  if (text.length <= 1500) actions.dataset.rawText = text;
  const copyBtn = document.createElement('button');
  copyBtn.type = 'button';
  copyBtn.className = 'msg-action-btn';
  copyBtn.title = 'Copy';
  copyBtn.innerHTML = '<i class="ri-file-copy-line"></i>';
  copyBtn.addEventListener('click', () => copyMessage(copyBtn));
  const downloadBtn = document.createElement('button');
  downloadBtn.type = 'button';
  downloadBtn.className = 'msg-action-btn';
  downloadBtn.title = 'Download';
  downloadBtn.innerHTML = '<i class="ri-download-2-line"></i>';
  downloadBtn.addEventListener('click', () => downloadMessage(downloadBtn));
  actions.appendChild(copyBtn);
  actions.appendChild(downloadBtn);
  contentDiv.appendChild(actions);
}

function getMessageRawText(btn) {
  const actions = btn.closest('.msg-actions');
  if (!actions) return btn.closest('.msg-content')?.innerText || '';
  return messageRawText.get(actions) || actions.dataset.rawText || btn.closest('.msg-content')?.innerText || '';
}

async function copyMessage(btn) {
  const text = getMessageRawText(btn);
  try {
    await navigator.clipboard.writeText(text);
    btn.classList.add('copied');
    const icon = btn.querySelector('i');
    if (icon) icon.className = 'ri-check-line';
    setTimeout(() => {
      btn.classList.remove('copied');
      if (icon) icon.className = 'ri-file-copy-line';
    }, 2000);
  } catch (err) {
    console.warn('Copy failed:', err);
  }
}

function loadScriptOnce(src) {
  return new Promise((resolve, reject) => {
    const existing = document.querySelector(`script[data-pdf-lib="${src}"]`);
    if (existing) {
      if (existing.dataset.loaded === '1') resolve();
      else existing.addEventListener('load', () => resolve(), { once: true });
      return;
    }
    const s = document.createElement('script');
    s.src = src;
    s.async = true;
    s.dataset.pdfLib = src;
    s.onload = () => {
      s.dataset.loaded = '1';
      resolve();
    };
    s.onerror = () => reject(new Error(`Failed to load ${src}`));
    document.head.appendChild(s);
  });
}

async function ensurePdfLibs() {
  if (!window.html2canvas) {
    await loadScriptOnce('https://cdn.jsdelivr.net/npm/html2canvas@1.4.1/dist/html2canvas.min.js');
  }
  if (!window.jspdf?.jsPDF) {
    await loadScriptOnce('https://cdn.jsdelivr.net/npm/jspdf@2.5.2/dist/jspdf.umd.min.js');
  }
}

function loadImageDataUrl(src) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => {
      const canvas = document.createElement('canvas');
      canvas.width = img.naturalWidth;
      canvas.height = img.naturalHeight;
      canvas.getContext('2d').drawImage(img, 0, 0);
      resolve({
        dataUrl: canvas.toDataURL('image/png'),
        width: img.naturalWidth,
        height: img.naturalHeight,
      });
    };
    img.onerror = () => reject(new Error(`Failed to load image: ${src}`));
    img.src = src;
  });
}

/** Build a per-row "has ink" mask so we can break pages between text lines. */
function buildCanvasRowInkMask(canvas, alphaThreshold = 24) {
  const ctx = canvas.getContext('2d', { willReadFrequently: true });
  const { width, height } = canvas;
  const data = ctx.getImageData(0, 0, width, height).data;
  const ink = new Uint8Array(height);
  const stepX = Math.max(1, Math.floor(width / 400));
  for (let y = 0; y < height; y++) {
    const row = y * width * 4;
    let hasInk = 0;
    for (let x = 0; x < width; x += stepX) {
      if (data[row + x * 4 + 3] > alphaThreshold) {
        hasInk = 1;
        break;
      }
    }
    ink[y] = hasInk;
  }
  return ink;
}

/** Prefer cutting inside a blank gap near the ideal page end. */
function findSafeCanvasCutY(ink, startY, idealEnd, minPagePx) {
  const height = ink.length;
  const hardEnd = Math.min(height, idealEnd);
  if (hardEnd >= height) return height;
  if (hardEnd - startY <= minPagePx) return hardEnd;

  const searchFrom = Math.max(startY + minPagePx, hardEnd - Math.floor((hardEnd - startY) * 0.35));
  let bestCut = hardEnd;
  let bestGap = -1;
  let y = hardEnd;
  while (y > searchFrom) {
    while (y > searchFrom && ink[y - 1]) y--;
    if (y <= searchFrom) break;
    const gapEnd = y;
    while (y > searchFrom && !ink[y - 1]) y--;
    const gapStart = y;
    const gap = gapEnd - gapStart;
    if (gap > bestGap) {
      bestGap = gap;
      bestCut = Math.min(hardEnd, gapStart + Math.ceil(gap / 2));
    }
    if (bestGap >= 4) break;
  }
  if (!ink[hardEnd - 1] && (hardEnd >= height || !ink[hardEnd])) return hardEnd;
  return bestCut;
}

function sliceCanvasToDataUrl(sourceCanvas, srcY, sliceH) {
  const sliceCanvas = document.createElement('canvas');
  sliceCanvas.width = sourceCanvas.width;
  sliceCanvas.height = sliceH;
  const ctx = sliceCanvas.getContext('2d');
  ctx.clearRect(0, 0, sliceCanvas.width, sliceCanvas.height);
  ctx.drawImage(
    sourceCanvas,
    0, srcY, sliceCanvas.width, sliceH,
    0, 0, sliceCanvas.width, sliceH,
  );
  return sliceCanvas.toDataURL('image/png');
}

/** Force tables/code to wrap; pin brand blues to match the live page. */
function preparePdfExportStyles(root) {
  const style = document.createElement('style');
  style.textContent = `
    .pdf-export, .pdf-export * { box-sizing: border-box !important; }
    .pdf-export {
      --primary: #0d57d6;
      --primary-dark: #0d57d6;
      --primary-light: #e0edff;
      --primary-medium: #b3ccf5;
      --primary-alt: #0868c2;
      --text: #1e2022;
      --text-light: #5e676f;
      --text-muted: #8e97a0;
      --border: #d4e1f5;
      --bg: #f5f7fa;
      width: 100% !important;
      max-width: 100% !important;
      overflow: hidden !important;
      color: #1e2022 !important;
      font-family: Georgia, "Times New Roman", serif !important;
    }
    .pdf-export img, .pdf-export pre, .pdf-export table {
      max-width: 100% !important;
    }
    .pdf-export table {
      width: 100% !important;
      table-layout: fixed !important;
      border-collapse: collapse !important;
    }
    .pdf-export th, .pdf-export td {
      word-break: break-word !important;
      overflow-wrap: anywhere !important;
      white-space: normal !important;
      vertical-align: top !important;
    }
    .pdf-export code, .pdf-export a {
      word-break: break-all !important;
      overflow-wrap: anywhere !important;
      white-space: pre-wrap !important;
    }
    .pdf-export pre {
      white-space: pre-wrap !important;
      overflow: hidden !important;
      word-break: break-word !important;
    }
    .pdf-export .msg-content a,
    .pdf-export .msg-content h1,
    .pdf-export .msg-content h2,
    .pdf-export .msg-content h3,
    .pdf-export .msg-content h4,
    .pdf-export .msg-content h5,
    .pdf-export .msg-content > p > strong:only-child {
      color: #0d57d6 !important;
    }
    .pdf-export .msg-content a:hover {
      color: #0d57d6 !important;
    }
  `;
  root.prepend(style);
}

async function downloadMessage(btn) {
  const contentDiv = btn.closest('.msg-content');
  if (!contentDiv) return;

  const conv = conversationList.find((c) => c.id === conversationId);
  const baseName = (conv?.title || 'qptm-agent').replace(/[^\w\-]+/g, '_').slice(0, 40) || 'qptm-agent';

  const prevTitle = btn.title;
  const prevHtml = btn.innerHTML;
  btn.disabled = true;
  btn.title = 'Generating PDF...';
  btn.innerHTML = '<i class="ri-loader-4-line"></i>';

  try {
    await ensurePdfLibs();
    const { jsPDF } = window.jspdf;

    const exportEl = document.createElement('div');
    exportEl.className = 'pdf-export';
    exportEl.setAttribute('aria-hidden', 'true');
    exportEl.style.cssText = [
      'position:fixed',
      'left:-10000px',
      'top:0',
      'width:680px',
      'max-width:680px',
      'padding:4px 2px',
      'box-sizing:border-box',
      'overflow:hidden',
      'background:transparent',
      'color:#1e2022',
      'font-family:Georgia,"Times New Roman",serif',
      'font-size:14px',
      'line-height:1.65',
    ].join(';');

    const clone = contentDiv.cloneNode(true);
    clone.classList.remove('is-loading', 'is-streaming');
    clone.querySelector('.msg-actions')?.remove();
    clone.querySelector('.msg-content-loading')?.remove();
    clone.querySelector('.streaming-cursor')?.remove();
    clone.style.cssText = [
      'background:transparent',
      'border:none',
      'box-shadow:none',
      'padding:0',
      'margin:0',
      'width:100%',
      'max-width:100%',
      'overflow:hidden',
    ].join(';');
    exportEl.appendChild(clone);
    preparePdfExportStyles(exportEl);
    document.body.appendChild(exportEl);

    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));

    const canvas = await window.html2canvas(exportEl, {
      scale: 2,
      backgroundColor: null,
      useCORS: true,
      logging: false,
      width: 680,
      windowWidth: 680,
    });
    exportEl.remove();

    const logo = await loadImageDataUrl('assets/img/logo.gif');
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    const pageW = pdf.internal.pageSize.getWidth();
    const pageH = pdf.internal.pageSize.getHeight();
    const margin = 16;
    const footerH = 10;
    const contentW = pageW - margin * 2;
    const contentH = pageH - margin - footerH;
    const imgW = contentW;
    const pxPerMm = canvas.width / imgW;
    const maxPagePx = Math.max(1, Math.floor(contentH * pxPerMm));
    const minPagePx = Math.max(1, Math.floor(maxPagePx * 0.55));
    const ink = buildCanvasRowInkMask(canvas);

    const logoW = pageW * 0.42;
    const logoH = logoW * (logo.height / logo.width);
    const logoX = (pageW - logoW) / 2;
    const logoY = (pageH - logoH) / 2;

    let srcY = 0;
    let page = 0;
    while (srcY < canvas.height) {
      if (page > 0) pdf.addPage();
      pdf.setFillColor(255, 255, 255);
      pdf.rect(0, 0, pageW, pageH, 'F');

      pdf.saveGraphicsState();
      pdf.setGState(new pdf.GState({ opacity: 0.14 }));
      pdf.addImage(logo.dataUrl, 'PNG', logoX, logoY, logoW, logoH);
      pdf.restoreGraphicsState();

      const idealEnd = Math.min(canvas.height, srcY + maxPagePx);
      const cutY = findSafeCanvasCutY(ink, srcY, idealEnd, minPagePx);
      const sliceH = Math.max(1, cutY - srcY);
      const sliceData = sliceCanvasToDataUrl(canvas, srcY, sliceH);
      const sliceHmm = sliceH / pxPerMm;
      pdf.addImage(sliceData, 'PNG', margin, margin, imgW, sliceHmm);

      srcY = cutY;
      page += 1;
      if (page > 80) break;
    }

    const totalPages = pdf.internal.getNumberOfPages();
    for (let i = 1; i <= totalPages; i++) {
      pdf.setPage(i);
      pdf.setFont('helvetica', 'normal');
      pdf.setFontSize(9);
      pdf.setTextColor(140, 145, 155);
      pdf.text(`${i} / ${totalPages}`, pageW / 2, pageH - 6, { align: 'center' });
    }

    pdf.save(`${baseName}.pdf`);
  } catch (err) {
    console.warn('PDF download failed:', err);
    alert('Failed to generate PDF. Please try again.');
  } finally {
    btn.disabled = false;
    btn.title = prevTitle;
    btn.innerHTML = prevHtml;
  }
}

document.addEventListener('DOMContentLoaded', async () => {
  initWorkflowSidebarUi();
  const drBtn = document.getElementById('deepResearchBtn');
  if (drBtn) drBtn.addEventListener('click', toggleDeepResearchMode);
  await loadConversationList();
  if (conversationId && conversationList.some((c) => c.id === conversationId)) {
    await loadConversation(conversationId, { force: true });
  } else if (conversationId) {
    persistConversationId(null);
  }
  refreshCollectionInputPlaceholder();
});

chatArea.addEventListener('click', (e) => {
  const btn = e.target.closest('.next-step-chip, .follow-up-item');
  if (!btn || isStreaming) return;
  const q = btn.getAttribute('data-question');
  const intent = btn.getAttribute('data-intent') || 'qa';
  if (q) sendExample(q, intent);
});

// ── Scroll-to-bottom button ─────────────────────────────
const scrollBottomBtn = document.getElementById('scrollBottomBtn');
const agentMainEl = document.querySelector('.agent-main');

function isNearBottom(area) {
  return area.scrollHeight - area.scrollTop - area.clientHeight < 120;
}

/** Align the scroll-to-bottom button vertically with the send button. */
function positionScrollBottomBtn() {
  if (!scrollBottomBtn || !agentMainEl || !sendBtn) return;
  const mainRect = agentMainEl.getBoundingClientRect();
  const sendRect = sendBtn.getBoundingClientRect();
  const sendCenter = sendRect.top + sendRect.height / 2;
  const fromBottom = mainRect.bottom - sendCenter;
  const btnHalf = scrollBottomBtn.offsetHeight / 2 || 19;
  scrollBottomBtn.style.bottom = Math.max(8, fromBottom - btnHalf) + 'px';
}

function updateScrollBottomBtn() {
  if (!scrollBottomBtn) return;
  positionScrollBottomBtn();
  const near = isNearBottom(chatArea);
  scrollBottomBtn.classList.toggle('show', !near);
}

chatArea.addEventListener('scroll', updateScrollBottomBtn, { passive: true });
window.addEventListener('resize', updateScrollBottomBtn, { passive: true });
window.addEventListener('load', updateScrollBottomBtn, { passive: true });
inputField.addEventListener('input', updateScrollBottomBtn);

if (scrollBottomBtn) {
  scrollBottomBtn.addEventListener('click', () => {
    chatArea.scrollTo({ top: chatArea.scrollHeight, behavior: 'smooth' });
  });
}

function resizeInputField() {
  inputField.style.height = 'auto';
  const maxH = 120;
  const nextH = Math.min(inputField.scrollHeight, maxH);
  inputField.style.height = nextH + 'px';
  inputField.style.overflowY = inputField.scrollHeight > maxH ? 'auto' : 'hidden';
}

inputField.addEventListener('input', resizeInputField);

function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    if (isStreaming) {
      stopStreaming();
    } else {
      sendMessage();
    }
  }
}

function sendExample(text, mode = 'qa') {
  inputField.value = text;
  setAgentChatMode(mode);
  sendMessage();
}

function setAgentChatMode(mode) {
  agentChatMode = mode === 'deep_research' ? 'deep_research' : 'qa';
  const btn = document.getElementById('deepResearchBtn');
  if (btn) {
    btn.classList.toggle('active', agentChatMode === 'deep_research');
    btn.setAttribute('aria-pressed', agentChatMode === 'deep_research' ? 'true' : 'false');
  }
}

function toggleDeepResearchMode() {
  setAgentChatMode(agentChatMode === 'deep_research' ? 'qa' : 'deep_research');
}

function htmlDecode(text) {
  const div = document.createElement('div');
  div.innerHTML = text;
  return div.textContent || '';
}

function escapeAttr(text) {
  return String(text)
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function stripInlineMdMarkers(text) {
  return String(text)
    .replace(/\*\*(.+?)\*\*/g, '$1')
    .replace(/\*(.+?)\*/g, '$1')
    .replace(/`([^`]+)`/g, '$1')
    .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
    .trim();
}

function isNextStepHeadingText(text) {
  const t = stripInlineMdMarkers(htmlDecode(text)).replace(/[:：]\s*$/, '').trim();
  return /^(next\s*steps?|下一步|后续问题)$/i.test(t);
}

function matchNextStepInline(text) {
  const raw = htmlDecode(text);
  const m = raw.match(/^(?:\*\*)?next\s*steps?(?:\*\*)?\s*[:：]\s*(.+)$/i)
    || raw.match(/^(?:\*\*)?(?:下一步|后续问题)(?:\*\*)?\s*[:：]\s*(.+)$/);
  return m ? stripInlineMdMarkers(m[1]) : null;
}

function renderNextStepChips(questions) {
  const chips = [];
  for (const q of questions) {
    const plain = stripInlineMdMarkers(htmlDecode(q)).replace(/^[\-\*\d.\s]+/, '').trim();
    if (!plain) continue;
    chips.push(
      `<button type="button" class="example-chip next-step-chip" data-question="${escapeAttr(plain)}">${escapeHtml(plain)}</button>`
    );
  }
  if (!chips.length) return '';
  return `<div class="next-step-block"><div class="next-step-chips">${chips.join('')}</div></div>`;
}

function stripNextStepSection(text) {
  return String(text || '').replace(
    /\r?\n##\s*(?:Next step|后续问题|下一步)\s*\r?\n[\s\S]*?(?=\r?\n##\s|$)/i,
    '',
  ).trim();
}

/** Remove trailing invite / next-step copy — follow-ups live in the panel.
 *  Do NOT strip markdown thematic breaks (`---`); deep-research reports use them
 *  as section dividers and a greedy cut would delete most of the answer. */
function stripTrailingInvite(text) {
  let s = stripNextStepSection(text);
  // Only drop a trailing --- block when it clearly looks like an invite, not a section HR.
  s = s.replace(
    /\n+---\s*\n(?:[^\n]*\n){0,8}(?:如果您想了解|如果您想查|若想了解|如需查询|如果只是想了解|Next step|后续问题|下一步|If you want to|To look up)[\s\S]*$/iu,
    '',
  ).trim();
  s = s.replace(
    /\n+(如果您想了解|如果您想查|若想了解|如需查询|如果只是想了解)[^\n]{0,200}[？?]?\s*$/u,
    '',
  ).trim();
  s = s.replace(
    /\n+(If you want to|To look up|For database|If you have a concrete)[^\n]{0,220}[?.]?\s*$/i,
    '',
  ).trim();
  return s;
}

function extractNextStepQuestions(text) {
  const m = String(text || '').match(
    /\r?\n##\s*(?:Next step|后续问题|下一步)\s*\r?\n([\s\S]*?)(?=\r?\n##\s|$)/i,
  );
  if (!m) return [];
  const questions = [];
  for (const line of m[1].split('\n')) {
    const t = line.trim();
    if (!t) continue;
    const q = stripInlineMdMarkers(t.replace(/^[\-\*\d.]+\s*/, ''));
    if (q.length >= 8 && !questions.includes(q)) questions.push(q);
  }
  return questions.slice(0, 4);
}

function detectLangFromText(text) {
  const zh = (String(text || '').match(/[\u4e00-\u9fff]/g) || []).length;
  return zh >= 2 ? 'zh' : 'en';
}

function followUpPanelTitle(lang) {
  return lang === 'zh' ? '后续问题' : 'Follow-up questions';
}

function normalizeFollowUpItem(item) {
  if (typeof item === 'string') {
    return { text: item, intent: 'qa' };
  }
  if (item && typeof item === 'object' && item.text) {
    return {
      text: String(item.text),
      intent: item.intent === 'deep_research' ? 'deep_research' : 'qa',
    };
  }
  return null;
}

function followUpDisplayText(item) {
  const norm = normalizeFollowUpItem(item);
  return norm ? norm.text : '';
}

function createFollowUpPanel(questions, langHint) {
  if (!questions?.length) return null;
  const normalized = questions.map(normalizeFollowUpItem).filter(Boolean);
  if (!normalized.length) return null;
  const lang = langHint || detectLangFromText(normalized.map((q) => q.text).join(' '));
  const panel = document.createElement('div');
  panel.className = 'follow-up-panel';
  panel.innerHTML = `
    <button type="button" class="follow-up-header" aria-expanded="true">
      <i class="ri-chat-forward-line" aria-hidden="true"></i>
      <span class="follow-up-title">${escapeHtml(followUpPanelTitle(lang))}</span>
      <i class="ri-arrow-down-s-line follow-up-toggle" aria-hidden="true"></i>
    </button>
    <div class="follow-up-list"></div>
  `;
  const list = panel.querySelector('.follow-up-list');
  normalized.forEach((q) => {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'follow-up-item';
    btn.dataset.question = q.text;
    btn.dataset.intent = q.intent;
    const drIcon = q.intent === 'deep_research'
      ? '<i class="ri-telescope-line dr-badge" title="Deep Research" aria-hidden="true"></i>'
      : '';
    btn.innerHTML = `<i class="ri-arrow-right-s-line" aria-hidden="true"></i><span>${escapeHtml(q.text)}</span>${drIcon}`;
    list.appendChild(btn);
  });
  panel.querySelector('.follow-up-header').addEventListener('click', () => {
    const collapsed = panel.classList.toggle('collapsed');
    panel.querySelector('.follow-up-header').setAttribute('aria-expanded', String(!collapsed));
  });
  return panel;
}

function mountFollowUpPanel(assistantBody, questions, langHint) {
  if (!assistantBody || !questions?.length) return;
  assistantBody.querySelector('.follow-up-panel')?.remove();
  const panel = createFollowUpPanel(questions, langHint);
  if (panel) assistantBody.appendChild(panel);
}

function applyInlineMarkdown(text) {
  let s = text;
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
  // Bare PMID:12345678 → PubMed link (skip markdown-link form [PMID:…](…))
  s = s.replace(/(?<!\[)\bPMID[:\s]*(\d{5,9})\b(?!\])/gi, (_, id) =>
    `<a href="https://pubmed.ncbi.nlm.nih.gov/${id}/" target="_blank" rel="noopener">PMID:${id}</a>`
  );
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  // Inline source citations [S1], [S2, S3] → superscript
  s = s.replace(/\[(S\d+(?:\s*,\s*S\d+)*)\]/g, '<sup class="cite-ref">[$1]</sup>');
  return s;
}

function stripProtocolMarkup(text) {
  if (!text) return '';
  let s = String(text);
  s = s.replace(/<\|DSML\|[\s\S]*?(?:\|DSML\|>|$)/gi, '');
  s = s.replace(/<\/?tool_call\b[^>]*>[\s\S]*?(<\/tool_call>|$)/gi, '');
  s = s.replace(/```(?:json|xml|text)?\s*\{[\s\S]*?"tool_calls"[\s\S]*?```/gi, '');
  s = s.replace(/"?tool_calls"?\s*[:=]\s*\[[\s\S]*?\]/gi, '');
  s = s.replace(/"?function_call"?\s*[:=]\s*\{[\s\S]*?\}/gi, '');
  s = s.replace(/<\|[^|]{0,80}\|>/g, '');
  return s.replace(/\n{3,}/g, '\n\n').trim();
}

function sanitizeUserVisibleText(text) {
  const raw = String(text || '');
  const leaked = /<\|?DSML\|?|<\/?tool_call\b|tool_calls|function_call|<tool\b|<\/tool>/i.test(raw);
  const cleaned = stripProtocolMarkup(raw);
  if (leaked && cleaned.replace(/\s/g, '').length < 12) {
    return /[\u4e00-\u9fff]/.test(raw) ? '生成失败，请重试。' : 'Generation failed. Please retry.';
  }
  return cleaned;
}

function renderMarkdown(text) {
  if (!text) return '';
  text = sanitizeUserVisibleText(text);
  if (!text) return '';

  const codeBlocks = [];
  let src = text.replace(/```([\s\S]*?)```/g, (_, code) => {
    const idx = codeBlocks.length;
    codeBlocks.push(code);
    return `\x00CODEBLOCK${idx}\x00`;
  });

  src = escapeHtml(src);

  codeBlocks.forEach((code, idx) => {
    const trimmed = code.trim();
    const placeholder = `\x00CODEBLOCK${idx}\x00`;
    if (trimmed.includes('|') && trimmed.includes('\n')) {
      src = src.replace(placeholder, renderTable(trimmed));
    } else {
      src = src.replace(placeholder, `<pre><code>${escapeHtml(trimmed)}</code></pre>`);
    }
  });

  const lines = src.split('\n');
  const result = [];
  let i = 0;
  let inList = false;
  let listType = 'ul';
  /** First number of the current <ol> (for start= and continuity checks). */
  let olStart = 1;
  /** How many <li> already emitted in the current <ol>. */
  let olItemCount = 0;

  function closeList() {
    if (inList) {
      result.push(`</${listType}>`);
      inList = false;
      olStart = 1;
      olItemCount = 0;
    }
  }

  function openOrderedList(startNum) {
    const start = Number.isFinite(startNum) && startNum > 0 ? startNum : 1;
    olStart = start;
    olItemCount = 0;
    result.push(start > 1 ? `<ol start="${start}">` : '<ol>');
    inList = true;
    listType = 'ol';
  }

  function openUnorderedList() {
    olStart = 1;
    olItemCount = 0;
    result.push('<ul>');
    inList = true;
    listType = 'ul';
  }

  while (i < lines.length) {
    const line = lines[i];
    const trimmed = line.trim();

    if (trimmed.includes('|')) {
      const tableLines = [];
      let j = i;
      while (j < lines.length && lines[j].trim().includes('|')) {
        tableLines.push(lines[j]);
        j++;
      }
      const colCount = tableLines[0].replace(/^\|/, '').replace(/\|$/, '').split('|').length;
      if (tableLines.length >= 2 && colCount >= 2) {
        closeList();
        result.push(renderTable(tableLines.join('\n')));
        i = j;
        continue;
      }
    }

    if (/^-{3,}$/.test(trimmed)) {
      closeList();
      result.push('<hr>');
      i++;
      continue;
    }

    const heading = trimmed.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      closeList();
      const level = heading[1].length;
      const headingText = heading[2];
      if (isNextStepHeadingText(headingText)) {
        result.push(`<h${level}>${applyInlineMarkdown(headingText)}</h${level}>`);
        i++;
        const questions = [];
        while (i < lines.length) {
          const qTrim = lines[i].trim();
          if (qTrim === '') { i++; continue; }
          if (/^(#{1,6})\s+/.test(qTrim) || /^-{3,}$/.test(qTrim)) break;
          if (qTrim.includes('|') && i + 1 < lines.length && /^[\|\s:\-]+$/.test(lines[i + 1].trim())) break;
          const qUl = qTrim.match(/^[\-\*] (.+)$/);
          const qOl = qTrim.match(/^\d+\. (.+)$/);
          if (qUl || qOl) {
            questions.push(qUl ? qUl[1] : qOl[1]);
            i++;
            continue;
          }
          questions.push(qTrim);
          i++;
        }
        const chips = renderNextStepChips(questions);
        if (chips) result.push(chips);
        continue;
      }
      result.push(`<h${level}>${applyInlineMarkdown(headingText)}</h${level}>`);
      i++;
      continue;
    }

    // Inline "Next step: …" / "**Next step:** …"
    const nextInlineQ = matchNextStepInline(trimmed);
    if (nextInlineQ) {
      closeList();
      result.push('<h3>Next step</h3>');
      const questions = [nextInlineQ];
      i++;
      while (i < lines.length) {
        const qTrim = lines[i].trim();
        if (qTrim === '') { i++; continue; }
        if (/^(#{1,6})\s+/.test(qTrim) || /^-{3,}$/.test(qTrim)) break;
        if (isNextStepHeadingText(qTrim) || matchNextStepInline(qTrim)) break;
        const qUl = qTrim.match(/^[\-\*] (.+)$/);
        const qOl = qTrim.match(/^\d+\. (.+)$/);
        if (qUl || qOl) {
          questions.push(qUl ? qUl[1] : qOl[1]);
          i++;
          continue;
        }
        // Only keep collecting if still in a list-like follow-up block
        if (/^[\-\*] /.test(qTrim) || /^\d+\. /.test(qTrim)) {
          questions.push(qTrim);
          i++;
          continue;
        }
        break;
      }
      const chips = renderNextStepChips(questions);
      if (chips) result.push(chips);
      continue;
    }

    // Blockquotes: strip leading ">" — keep icons/emoji, never show the raw ">".
    if (/^&gt;\s?/.test(trimmed) || /^>\s?/.test(trimmed)) {
      closeList();
      const quoteLines = [];
      while (i < lines.length) {
        const qTrim = lines[i].trim();
        if (!/^&gt;\s?/.test(qTrim) && !/^>\s?/.test(qTrim)) break;
        const body = qTrim.replace(/^(&gt;|>)\s?/, '');
        if (body !== '') quoteLines.push(body);
        i++;
      }
      if (quoteLines.length) {
        const inner = quoteLines.map((l) => `<p>${applyInlineMarkdown(l)}</p>`).join('');
        result.push(`<blockquote>${inner}</blockquote>`);
      }
      continue;
    }

    const ulMatch = trimmed.match(/^[\-\*] (.+)$/);
    const olMatch = trimmed.match(/^(\d+)\. (.+)$/);
    if (ulMatch || olMatch) {
      const newType = ulMatch ? 'ul' : 'ol';
      const mdNum = olMatch ? parseInt(olMatch[1], 10) : 1;
      if (!inList) {
        if (newType === 'ol') openOrderedList(mdNum);
        else openUnorderedList();
      } else if (listType !== newType) {
        closeList();
        if (newType === 'ol') openOrderedList(mdNum);
        else openUnorderedList();
      } else if (newType === 'ol' && Number.isFinite(mdNum) && mdNum !== olStart + olItemCount) {
        // Number jumped (e.g. 1,2 then 5) — reopen so ::marker matches markdown.
        closeList();
        openOrderedList(mdNum);
      }
      result.push(`<li>${applyInlineMarkdown(ulMatch ? ulMatch[1] : olMatch[2])}</li>`);
      if (listType === 'ol') olItemCount++;
      i++;
      continue;
    }

    // Blank lines: keep the same list open when the next non-empty line is still
    // a list item of the same type (so ::marker does not restart at 1).
    if (trimmed === '') {
      let k = i + 1;
      while (k < lines.length && lines[k].trim() === '') k++;
      const next = k < lines.length ? lines[k].trim() : '';
      const nextUl = /^[\-\*] /.test(next);
      const nextOl = /^\d+\. /.test(next);
      if (inList && ((listType === 'ul' && nextUl) || (listType === 'ol' && nextOl))) {
        i++;
        continue;
      }
      closeList();
      i++;
      continue;
    }

    closeList();
    // trimmed is non-empty here

    // Bare "Next step" / "下一步" line (no ##) followed by questions
    if (isNextStepHeadingText(trimmed)) {
      result.push(`<h3>${applyInlineMarkdown(trimmed)}</h3>`);
      i++;
      const questions = [];
      while (i < lines.length) {
        const qTrim = lines[i].trim();
        if (qTrim === '') { i++; continue; }
        if (/^(#{1,6})\s+/.test(qTrim) || /^-{3,}$/.test(qTrim)) break;
        if (isNextStepHeadingText(qTrim) || matchNextStepInline(qTrim)) break;
        const qUl = qTrim.match(/^[\-\*] (.+)$/);
        const qOl = qTrim.match(/^\d+\. (.+)$/);
        if (qUl || qOl) {
          questions.push(qUl ? qUl[1] : qOl[1]);
          i++;
          continue;
        }
        questions.push(qTrim);
        i++;
      }
      const chips = renderNextStepChips(questions);
      if (chips) result.push(chips);
      continue;
    }

    result.push(`<p>${applyInlineMarkdown(trimmed)}</p>`);
    i++;
  }
  closeList();
  return result.join('\n');
}

function renderTable(text) {
  const lines = text.split('\n').filter(l => l.trim());
  if (lines.length < 1) return '';
  const cells = (line) => line.replace(/^\|/, '').replace(/\|$/, '').split('|').map(c => c.trim());
  const headers = cells(lines[0]);
  let html = '<table><thead><tr>';
  headers.forEach(h => { html += `<th>${applyInlineMarkdown(h)}</th>`; });
  html += '</tr></thead><tbody>';
  for (let i = 1; i < lines.length; i++) {
    if (/^[\|\s:\-]+$/.test(lines[i])) continue;
    html += '<tr>';
    cells(lines[i]).forEach(c => { html += `<td>${applyInlineMarkdown(c)}</td>`; });
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

function addMessage(role, content) {
  if (welcome) welcome.style.display = 'none';

  const msg = document.createElement('div');
  msg.className = `message ${role}`;

  const contentDiv = document.createElement('div');
  contentDiv.className = 'msg-content';
  contentDiv.innerHTML = role === 'user' ? escapeHtml(content) : renderMarkdown(content);

  msg.appendChild(contentDiv);
  chatArea.appendChild(msg);
  chatArea.scrollTop = chatArea.scrollHeight;
  return contentDiv;
}

function createPlanPanelEl(data, collapsed = false) {
  const panel = document.createElement('div');
  panel.className = 'plan-panel' + (collapsed ? ' collapsed' : '');
  const stepsHtml = (data.steps || []).map(s => `
    <div class="plan-step${s.status ? ` ${escapeHtml(s.status)}` : ''}" data-step="${s.step}">
      <div class="plan-step-num">${s.step}</div>
      <div class="plan-step-body">
        <div class="plan-step-title">${escapeHtml(s.title || '')}</div>
        <div class="plan-step-meta">${escapeHtml(s.database || '')} · ${escapeHtml(s.tool || '')}</div>
        <div class="plan-step-desc">${escapeHtml(s.description || '')}</div>
      </div>
    </div>
  `).join('');
  panel.innerHTML = `
    <div class="plan-panel-header"><i class="ri-list-check"></i> Research Plan<i class="ri-arrow-down-s-line toggle-arrow"></i></div>
    <div class="plan-panel-details">
      <div class="plan-panel-summary">${escapeHtml(data.intent_summary || '')}</div>
      <div class="plan-steps">${stepsHtml}</div>
    </div>
  `;
  panel.querySelector('.plan-panel-header').addEventListener('click', () => {
    panel.classList.toggle('collapsed');
  });
  return panel;
}

function createThinkingToolsEl(tools, collapsed = false) {
  const el = document.createElement('div');
  el.className = 'thinking-tools has-tools' + (collapsed ? ' collapsed' : '');
  const count = tools.length;
  const summary = document.createElement('div');
  summary.className = 'thinking-tools-summary';
  summary.innerHTML = `<i class="ri-database-2-line"></i><span class="thinking-summary-text">Queried ${count} data source${count > 1 ? 's' : ''}</span><i class="ri-arrow-down-s-line toggle-arrow"></i>`;
  summary.addEventListener('click', () => el.classList.toggle('collapsed'));
  el.appendChild(summary);

  tools.forEach((t) => {
    const success = t.success !== false;
    const kind = t.error_kind || '';
    const st = t.status || (success ? (kind === 'empty_result' ? 'empty' : 'done') : 'error');
    const ind = document.createElement('div');
    ind.className = 'tool-indicator ' + (st === 'done' ? 'success' : st);
    ind.innerHTML = `
      <i class="ri-tools-line tool-icon"></i>
      <div class="tool-indicator-body">
        <span class="tool-name">${escapeHtml(t.tool_name || '')}</span>
        <span class="tool-args">${escapeHtml(formatArgs(t.arguments || {}))}</span>
        <span class="tool-summary">${escapeHtml((t.summary || '').substring(0, 120))}</span>
      </div>
      <span class="tool-status">${escapeHtml(toolStatusLabel(st, kind))}</span>
    `;
    el.appendChild(ind);
  });
  return el;
}

function addStoredAssistantMessage(content, meta) {
  if (welcome) welcome.style.display = 'none';

  const msg = document.createElement('div');
  msg.className = 'message assistant';

  const body = document.createElement('div');
  body.className = 'assistant-body';

  if (meta?.collection) {
    const c = meta.collection;
    const panel = createCollectionPanelEl(c.job_id || 'stored');
    if (c.pmid && (!c.current_stage || c.current_stage === 'stage1')) {
      const pmidEl = panel.querySelector('.collection-pmid');
      if (pmidEl) pmidEl.textContent = `PMID ${c.pmid}`;
    }
    updateCollectionPanel(panel, {
      job_id: c.job_id,
      pmid: c.pmid,
      status: c.status,
      current_stage: c.current_stage,
      awaiting_upload: c.awaiting_upload || c.awaitingUpload || null,
      next_stage: c.next_stage || c.nextStage || null,
      stages: c.stages || {},
      summary: c.summary || {},
      offer_contribute: c.offer_contribute,
      contribution: c.contribution,
      message: c.message || content,
    });
    body.appendChild(panel);
    const contentDiv = document.createElement('div');
    contentDiv.className = 'msg-content';
    contentDiv.dataset.skipPersist = '1';
    body.appendChild(contentDiv);
    msg.appendChild(body);
    chatArea.appendChild(msg);
    renderCollectionMessage(
      contentDiv,
      {
        job_id: c.job_id,
        pmid: c.pmid,
        status: c.status,
        current_stage: c.current_stage,
        awaiting_upload: c.awaiting_upload || c.awaitingUpload || null,
        next_stage: c.next_stage || c.nextStage || null,
        stages: c.stages || {},
        summary: c.summary || {},
        offer_contribute: c.offer_contribute,
        contribution: c.contribution,
        message: c.message || content,
      },
      c.status || 'completed',
      panel,
    ).catch(() => {
      contentDiv.innerHTML = `<p style="white-space:pre-wrap;">${escapeHtml(content || '')}</p>`;
    });
    return contentDiv;
  }

  if (meta?.workflow) {
    body.appendChild(mountWorkflowPanel(meta.workflow));
  } else if (meta?.plan) {
    body.appendChild(createPlanPanelEl(meta.plan, true));
  }
  if (meta?.tools?.length) {
    body.appendChild(createThinkingToolsEl(meta.tools, true));
  }

  const contentDiv = document.createElement('div');
  contentDiv.className = 'msg-content';
  const displayContent = stripTrailingInvite(content || '');
  contentDiv.innerHTML = renderMarkdown(displayContent);
  body.appendChild(contentDiv);
  const followUps = (meta?.follow_ups?.length ? meta.follow_ups : extractNextStepQuestions(content || ''));
  mountFollowUpPanel(body, followUps, detectLangFromText(content || ''));
  msg.appendChild(body);
  chatArea.appendChild(msg);
  attachMessageActions(contentDiv, content || '');
  return contentDiv;
}

let currentThinkingTools = null;
let currentPlanPanel = null;
let currentActivityTimeline = null;
let activityToolCount = 0;

let currentWorkflowState = null;
let workflowSidebarOpen = false;
const workflowPanelMeta = new WeakMap();

const PHASE_META = {
  planning: { en: 'Planning', zh: '规划', icon: 'ri-compass-3-line' },
  resolving: { en: 'Resolving', zh: '解析实体', icon: 'ri-focus-3-line' },
  clarifying: { en: 'Clarifying', zh: '澄清需求', icon: 'ri-question-answer-line' },
  retrieving_tools: { en: 'Preparing tools', zh: '准备工具', icon: 'ri-tools-line' },
  database: { en: 'Database', zh: '数据库查询', icon: 'ri-database-2-line' },
  literature: { en: 'Literature', zh: '文献检索', icon: 'ri-book-open-line' },
  synthesis: { en: 'Writing', zh: '撰写回答', icon: 'ri-quill-pen-line' },
  reply: { en: 'Reply', zh: '回复', icon: 'ri-chat-3-line' },
};

function phaseLabel(phaseId, fallback) {
  const zh = workflowLang() === 'zh';
  const meta = PHASE_META[phaseId];
  if (!meta) return fallback || phaseId || '';
  return zh ? meta.zh : meta.en;
}

function initWorkflowSidebarUi() {
  document.getElementById('workflowSidebarClose')?.addEventListener('click', closeWorkflowSidebar);
  document.getElementById('workflowSidebarBackdrop')?.addEventListener('click', closeWorkflowSidebar);
  document.getElementById('workflowSidebarToggle')?.addEventListener('click', () => {
    if (workflowSidebarOpen) closeWorkflowSidebar();
    else openWorkflowSidebar();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && workflowSidebarOpen) closeWorkflowSidebar();
  });
  syncWorkflowToggleButton();
}

function syncWorkflowToggleButton() {
  const btn = document.getElementById('workflowSidebarToggle');
  if (!btn) return;
  btn.classList.toggle('active', workflowSidebarOpen);
  const zh = workflowLang() === 'zh';
  btn.title = zh ? 'Agent 工作室' : 'Agent Studio';
  const label = btn.querySelector('span');
  if (label) label.textContent = zh ? 'Agent 工作室' : 'Agent Studio';
}

function activateWorkflowPanel(activityEl, state) {
  if (!activityEl || !state) return;
  currentActivityTimeline = activityEl;
  currentWorkflowState = state;
  workflowPanelMeta.set(activityEl, state);
  renderWorkflowPanel();
}

function openWorkflowSidebar() {
  const main = document.querySelector('.agent-main');
  const sidebar = document.getElementById('workflowSidebar');
  if (!main || !sidebar) return;
  workflowSidebarOpen = true;
  main.classList.add('workflow-sidebar-open');
  sidebar.setAttribute('aria-hidden', 'false');
  document.getElementById('workflowSidebarBackdrop')?.setAttribute('aria-hidden', 'false');
  syncWorkflowToggleButton();
  syncWorkflowSidebar();
}

function closeWorkflowSidebar() {
  const main = document.querySelector('.agent-main');
  const sidebar = document.getElementById('workflowSidebar');
  if (!main || !sidebar) return;
  workflowSidebarOpen = false;
  main.classList.remove('workflow-sidebar-open');
  sidebar.setAttribute('aria-hidden', 'true');
  document.getElementById('workflowSidebarBackdrop')?.setAttribute('aria-hidden', 'true');
  syncWorkflowToggleButton();
}

function workflowLang() {
  const sample = currentWorkflowState?.goal
    || currentWorkflowState?.plan?.summary
    || document.querySelector('.message.user:last-of-type')?.textContent
    || '';
  return /[\u4e00-\u9fff]/.test(sample) ? 'zh' : 'en';
}

function toolResultStatus(data) {
  if (data.success === false) {
    if (data.error_kind === 'missing_params') return 'missing';
    return 'error';
  }
  if (data.error_kind === 'empty_result') return 'empty';
  return 'done';
}

function toolStatusLabel(status, errorKind) {
  const zh = workflowLang() === 'zh';
  if (status === 'running') return zh ? '进行中' : 'Running';
  if (status === 'empty') return zh ? '无结果' : 'Empty';
  if (status === 'missing' || errorKind === 'missing_params') return zh ? '缺参' : 'Missing';
  if (status === 'error') {
    if (errorKind === 'call_bug') return zh ? '调用失败' : 'Failed';
    return zh ? '失败' : 'Error';
  }
  if (status === 'done') return zh ? '完成' : 'Done';
  return zh ? '等待' : 'Pending';
}

function statusBadgeLabel(status, errorKind) {
  return toolStatusLabel(status, errorKind);
}

function logWorkflowEvent(kind, message, extra = {}) {
  if (!currentWorkflowState) return;
  if (!currentWorkflowState.events) currentWorkflowState.events = [];
  currentWorkflowState.events.push({ ts: Date.now(), kind, message, ...extra });
  if (currentWorkflowState.events.length > 80) {
    currentWorkflowState.events = currentWorkflowState.events.slice(-80);
  }
}

function formatFlowTime(ts) {
  try {
    return new Date(ts).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  } catch (_) {
    return '';
  }
}

function createActivityTimelineEl({ initState = true } = {}) {
  const el = document.createElement('div');
  el.className = 'activity-timeline agent-workflow collapsed workflow-launcher';
  const zh = /[\u4e00-\u9fff]/.test(
    document.getElementById('inputField')?.placeholder || '',
  ) || /^zh/i.test(navigator.language || '');
  el.innerHTML = `
    <div class="activity-header" role="button" tabindex="0" title="Open Agent Studio">
      <i class="ri-git-branch-line"></i>
      <span class="activity-summary-text">Agent Studio</span>
      <span class="workflow-open-hint">${zh ? '点击查看' : 'View panel'}</span>
      <i class="ri-layout-right-line toggle-arrow"></i>
    </div>
    <div class="workflow-nodes"></div>
    <div class="activity-tools" hidden></div>
  `;
  const open = () => {
    const state = workflowPanelMeta.get(el) || currentWorkflowState;
    if (state) activateWorkflowPanel(el, state);
    openWorkflowSidebar();
  };
  el.querySelector('.activity-header').addEventListener('click', open);
  el.querySelector('.activity-header').addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      open();
    }
  });
  if (initState) initWorkflowState();
  return el;
}

/** Normalize persisted meta (new single-agent or legacy multi-agent). */
function workflowStateFromMeta(wf) {
  if (!wf || typeof wf !== 'object') return initWorkflowStateObject();
  if (wf.phases || wf.plan || wf.tools || Array.isArray(wf.events)) {
    return {
      ...initWorkflowStateObject(),
      ...wf,
      phases: Array.isArray(wf.phases) ? wf.phases : [],
      plan: wf.plan || { summary: '', steps: [] },
      tools: Array.isArray(wf.tools) ? wf.tools : [],
      literature: Array.isArray(wf.literature) ? wf.literature : [],
      events: Array.isArray(wf.events) ? wf.events : [],
      status: wf.status || 'done',
    };
  }

  // Legacy multi-agent meta → single-agent timeline
  const state = initWorkflowStateObject();
  const orch = wf.orchestrator || {};
  state.goal = orch.goal || '';
  state.plan = {
    summary: orch.goal || orch.reasoning || '',
    steps: (orch.tasks || []).map((t, i) => ({
      step: i + 1,
      title: t.focus || t.agent || `Step ${i + 1}`,
      description: '',
      database: t.agent || '',
      status: t.enabled === false ? 'pending' : 'done',
    })),
  };
  Object.values(wf.agents || {}).forEach((a) => {
    (a.tools || []).forEach((t) => {
      state.tools.push({
        tool_name: t.tool_name || t.name || 'tool',
        kind: t.kind || 'database',
        status: 'done',
        summary: '',
        ts: Date.now(),
      });
    });
    (a.searchTraces || []).forEach((tr) => state.literature.push({ ...tr, ts: Date.now() }));
  });
  state.events = Array.isArray(wf.events) ? wf.events : [];
  state.status = 'done';
  return state;
}

function mountWorkflowPanel(wfMeta) {
  const activity = createActivityTimelineEl({ initState: false });
  const state = workflowStateFromMeta(wfMeta);
  workflowPanelMeta.set(activity, state);
  const prevTimeline = currentActivityTimeline;
  const prevState = currentWorkflowState;
  currentActivityTimeline = activity;
  currentWorkflowState = state;
  renderWorkflowPanel();
  currentActivityTimeline = prevTimeline;
  currentWorkflowState = prevState;
  return activity;
}

function initWorkflowStateObject() {
  return {
    goal: '',
    currentPhase: '',
    status: 'pending',
    phases: [],
    plan: { summary: '', steps: [] },
    tools: [],
    literature: [],
    events: [],
  };
}

function initWorkflowState() {
  currentWorkflowState = initWorkflowStateObject();
  if (currentActivityTimeline) {
    workflowPanelMeta.set(currentActivityTimeline, currentWorkflowState);
  }
}

function studioHasData(state) {
  if (!state) return false;
  return Boolean(
    state.goal
    || state.currentPhase
    || state.phases?.length
    || state.plan?.summary
    || state.plan?.steps?.length
    || state.tools?.length
    || state.literature?.length
    || state.events?.length,
  );
}

function flowTickIcon(kind) {
  if (kind === 'plan') return 'ri-list-check-3';
  if (kind === 'phase') return 'ri-flashlight-line';
  if (kind === 'literature') return 'ri-book-open-line';
  if (kind === 'tool') return 'ri-database-2-line';
  if (kind === 'tool_result') return 'ri-checkbox-circle-line';
  if (kind === 'synthesis') return 'ri-quill-pen-line';
  return 'ri-record-circle-line';
}

function renderStudioSection(title, icon, bodyHtml) {
  if (!bodyHtml) return '';
  return `<section class="studio-section">
    <div class="studio-section-title"><i class="${icon}"></i> ${escapeHtml(title)}</div>
    ${bodyHtml}
  </section>`;
}

function renderPhasesBlock(phases, currentPhase) {
  if (!phases?.length) return '';
  const items = phases.map((p) => {
    const st = p.status || (p.id === currentPhase ? 'running' : 'done');
    const icon = PHASE_META[p.id]?.icon || 'ri-circle-line';
    return `<div class="studio-phase-item status-${st}">
      <i class="${icon}"></i>
      <div class="studio-phase-body">
        <div class="studio-phase-name">${escapeHtml(p.label || phaseLabel(p.id))}</div>
        ${p.ts ? `<time>${escapeHtml(formatFlowTime(p.ts))}</time>` : ''}
      </div>
      <span class="studio-stage-badge ${st}">${statusBadgeLabel(st)}</span>
    </div>`;
  }).join('');
  return `<div class="studio-phase-list">${items}</div>`;
}

function renderPlanBlock(plan) {
  if (!plan?.summary && !plan?.steps?.length) return '';
  const zh = workflowLang() === 'zh';
  const steps = (plan.steps || []).map((s, i) => {
    const st = s.status || 'pending';
    return `<div class="studio-plan-step status-${st}">
      <div class="studio-plan-step-idx">${escapeHtml(String(s.step || i + 1))}</div>
      <div class="studio-plan-step-body">
        <div class="studio-plan-step-title">${escapeHtml(s.title || '')}</div>
        ${s.description ? `<div class="studio-plan-step-desc">${escapeHtml(s.description)}</div>` : ''}
        ${s.database ? `<div class="studio-plan-step-meta">${escapeHtml(s.database)}</div>` : ''}
      </div>
    </div>`;
  }).join('');
  return `<div class="studio-plan-card">
    ${plan.summary ? `<div class="studio-plan-summary">${escapeHtml(plan.summary)}</div>` : ''}
    ${steps ? `<div class="studio-plan-steps">${steps}</div>` : `<div class="studio-stage-summary">${zh ? '暂无分步计划' : 'No step plan'}</div>`}
  </div>`;
}

function renderToolsBlock(tools) {
  if (!tools?.length) return '';
  return `<div class="studio-tool-rows">${tools.map((t) => {
    const st = t.status || 'done';
    const icon = t.kind === 'literature' ? 'ri-book-open-line' : 'ri-database-2-line';
    return `<div class="studio-tool-row kind-${escapeHtml(t.kind || 'database')} status-${st}">
      <i class="${icon}"></i>
      <div class="studio-tool-body">
        <div class="studio-tool-name">${escapeHtml(t.tool_name || 'tool')}</div>
        ${t.summary ? `<div class="studio-tool-summary">${escapeHtml(t.summary)}</div>` : ''}
      </div>
      <span class="studio-stage-badge ${st}">${statusBadgeLabel(st, t.error_kind)}</span>
    </div>`;
  }).join('')}</div>`;
}

function renderLiteratureBlock(traces) {
  if (!traces?.length) return '';
  const zh = workflowLang() === 'zh';
  const items = traces.map((t) => (
    `<div class="studio-lit-trace">
      <span class="studio-lit-trace-round">#${escapeHtml(String(t.round || ''))}</span>
      <span class="studio-lit-trace-query">${escapeHtml(t.query || '')}</span>
      <span class="studio-lit-trace-meta">${escapeHtml(String(t.papers_found ?? 0))} · ${escapeHtml(String(t.elapsed_s ?? ''))}s</span>
    </div>`
  )).join('');
  return `<details class="studio-lit-traces" open>
    <summary>${zh ? `文献检索 · ${traces.length} 轮` : `Literature · ${traces.length} round(s)`}</summary>
    ${items}
  </details>`;
}

function renderEventsBlock(events) {
  if (!events?.length) return '';
  const zh = workflowLang() === 'zh';
  const shown = events.slice(-24);
  const items = shown.map((ev, i) => {
    const isLatest = i === shown.length - 1 && currentWorkflowState?.status === 'running';
    return `<li class="studio-flow-item kind-${escapeHtml(ev.kind || 'phase')}${isLatest ? ' is-live' : ''}">
      <i class="${flowTickIcon(ev.kind)}"></i>
      <div>
        <span>${escapeHtml(ev.message || '')}</span>
        ${ev.ts ? `<time>${escapeHtml(formatFlowTime(ev.ts))}</time>` : ''}
      </div>
    </li>`;
  }).join('');
  return `<details class="studio-activity-log">
    <summary>${zh ? `活动日志 · ${events.length} 条` : `Activity log · ${events.length}`}</summary>
    <ul class="studio-flow-log">${items}</ul>
  </details>`;
}

function syncWorkflowSidebar() {
  const body = document.getElementById('workflowSidebarBody');
  const titleEl = document.getElementById('workflowSidebarTitle');
  if (!body) return;

  const zh = workflowLang() === 'zh';
  if (titleEl) titleEl.textContent = zh ? 'Agent 工作室' : 'Agent Studio';

  if (!studioHasData(currentWorkflowState)) {
    body.innerHTML = `<div class="workflow-sidebar-empty">
      <i class="ri-git-branch-line"></i>
      <p>${zh ? '此处展示 Agent 的思考、计划与工作流（阶段、工具、文献）。' : 'Thinking, plan, and workflow (phases, tools, literature) appear here.'}</p>
      <p class="workflow-sidebar-empty-hint">${zh ? '发起问题后，点击消息中的「Agent Studio」打开本面板。' : 'Ask a question, then open Agent Studio from the message.'}</p>
    </div>`;
    return;
  }

  const st = currentWorkflowState;
  const header = `<div class="studio-stage status-${st.status || 'running'}">
    <div class="studio-stage-head">
      <div class="studio-stage-name"><i class="ri-robot-2-line"></i> ${zh ? 'Agent 工作流' : 'Agent workflow'}</div>
      <span class="studio-stage-badge ${st.status || 'running'}">${statusBadgeLabel(st.status || 'running')}</span>
    </div>
    ${st.goal ? `<div class="studio-stage-focus">${escapeHtml(st.goal)}</div>` : ''}
    ${st.currentPhase ? `<div class="studio-stage-summary">${zh ? '当前阶段：' : 'Current phase: '}${escapeHtml(phaseLabel(st.currentPhase))}</div>` : ''}
  </div>`;

  const html = [
    header,
    renderStudioSection(zh ? '思考阶段' : 'Thinking phases', 'ri-brain-line', renderPhasesBlock(st.phases, st.currentPhase)),
    renderStudioSection(zh ? '研究计划' : 'Research plan', 'ri-list-check-3', renderPlanBlock(st.plan)),
    renderStudioSection(zh ? '工具调用' : 'Tool calls', 'ri-database-2-line', renderToolsBlock(st.tools)),
    renderStudioSection(zh ? '文献检索' : 'Literature', 'ri-book-open-line', renderLiteratureBlock(st.literature)),
    renderEventsBlock(st.events),
  ].filter(Boolean).join('');

  body.innerHTML = `<div class="studio-pipeline studio-single-agent">${html}</div>`;

  if (workflowSidebarOpen) {
    body.scrollTop = body.scrollHeight;
  }
}

function renderWorkflowPanel() {
  if (!currentActivityTimeline || !currentWorkflowState) return;
  const root = currentActivityTimeline.querySelector('.workflow-nodes');
  const summaryEl = currentActivityTimeline.querySelector('.activity-summary-text');
  const hintEl = currentActivityTimeline.querySelector('.workflow-open-hint');
  const zh = workflowLang() === 'zh';
  const st = currentWorkflowState;

  if (summaryEl) {
    if (st.status === 'running' && st.currentPhase) {
      summaryEl.textContent = zh
        ? `Agent Studio · ${phaseLabel(st.currentPhase)}`
        : `Agent Studio · ${phaseLabel(st.currentPhase)}`;
    } else if (st.tools?.length || st.plan?.steps?.length) {
      const n = st.tools?.length || 0;
      summaryEl.textContent = zh
        ? `Agent Studio · ${n ? `${n} 个工具` : '已规划'}`
        : `Agent Studio · ${n ? `${n} tool(s)` : 'planned'}`;
    } else {
      summaryEl.textContent = 'Agent Studio';
    }
  }
  if (hintEl) hintEl.textContent = zh ? '点击查看' : 'View panel';

  if (root) {
    const chips = [];
    if (st.goal) chips.push(st.goal.slice(0, 48) + (st.goal.length > 48 ? '…' : ''));
    else if (st.currentPhase) chips.push(phaseLabel(st.currentPhase));
    (st.phases || []).slice(-3).forEach((p) => {
      if (p.status === 'done') chips.push(`${phaseLabel(p.id, p.label)} ✓`);
    });
    root.innerHTML = chips.length
      ? `<div class="workflow-node-meta" style="padding:4px 12px 10px;font-size:12px">${escapeHtml(chips.join(' · '))}</div>`
      : '';
  }

  currentActivityTimeline.classList.add('collapsed');
  if (currentActivityTimeline && currentWorkflowState) {
    workflowPanelMeta.set(currentActivityTimeline, currentWorkflowState);
  }
  syncWorkflowSidebar();
}

function handlePhaseUpdate(phase, label) {
  if (!currentWorkflowState) initWorkflowState();
  const st = currentWorkflowState;
  st.status = 'running';
  const prev = st.currentPhase;
  if (prev && prev !== phase) {
    const prevItem = st.phases.find((p) => p.id === prev);
    if (prevItem && prevItem.status === 'running') prevItem.status = 'done';
  }
  st.currentPhase = phase || '';
  let item = st.phases.find((p) => p.id === phase);
  if (!item) {
    item = {
      id: phase,
      label: label || phaseLabel(phase),
      status: 'running',
      ts: Date.now(),
    };
    st.phases.push(item);
  } else {
    item.status = 'running';
    item.label = label || item.label || phaseLabel(phase);
    item.ts = Date.now();
  }
  logWorkflowEvent('phase', label || phaseLabel(phase), { phase });
  renderWorkflowPanel();
}

function handlePlanCreated(data) {
  if (!currentWorkflowState) initWorkflowState();
  const summary = data.intent_summary || data.summary || '';
  currentWorkflowState.goal = summary || currentWorkflowState.goal;
  currentWorkflowState.status = 'running';
  currentWorkflowState.plan = {
    summary,
    steps: (data.steps || []).map((s, i) => ({
      step: s.step || i + 1,
      title: s.title || s.description || `Step ${i + 1}`,
      description: s.description || '',
      database: s.database || s.entity || '',
      status: s.status || 'pending',
    })),
  };
  logWorkflowEvent('plan', summary || (workflowLang() === 'zh' ? '研究计划已生成' : 'Research plan created'));
  renderWorkflowPanel();
}

function handleLiteratureSearch(data) {
  if (!currentWorkflowState) initWorkflowState();
  currentWorkflowState.literature.push({
    round: data.round,
    query: data.query,
    papers_found: data.papers_found,
    elapsed_s: data.elapsed_s,
    ts: Date.now(),
  });
  const zh = workflowLang() === 'zh';
  const msg = zh
    ? `文献检索 #${data.round}: ${data.query} (${data.papers_found} 篇, ${data.elapsed_s}s)`
    : `Literature #${data.round}: ${data.query} (${data.papers_found} papers, ${data.elapsed_s}s)`;
  logWorkflowEvent('literature', msg);
  renderWorkflowPanel();
}

function handleWorkflowToolCall(data) {
  if (!currentWorkflowState) initWorkflowState();
  currentWorkflowState.tools.push({
    tool_name: data.tool_name,
    kind: data.kind || 'database',
    status: 'running',
    summary: '',
    ts: Date.now(),
  });
  logWorkflowEvent('tool', data.tool_name || 'tool', { kind: data.kind });
  renderWorkflowPanel();
}

function handleWorkflowToolResult(data) {
  if (!currentWorkflowState) return;
  const tools = currentWorkflowState.tools || [];
  let target = null;
  for (let i = tools.length - 1; i >= 0; i -= 1) {
    if (tools[i].tool_name === data.tool_name || tools[i].status === 'running') {
      target = tools[i];
      break;
    }
  }
  if (target) {
    target.status = toolResultStatus(data);
    target.summary = data.summary || target.summary || '';
    target.error_kind = data.error_kind || '';
  }
  if (data.summary) {
    logWorkflowEvent('tool_result', `${data.tool_name || 'tool'}: ${data.summary}`);
  }
  renderWorkflowPanel();
}

function markWorkflowDone() {
  if (!currentWorkflowState) return;
  if (currentWorkflowState.status !== 'error') {
    currentWorkflowState.status = 'done';
  }
  currentWorkflowState.phases.forEach((p) => {
    if (p.status === 'running') p.status = 'done';
  });
  currentWorkflowState.tools.forEach((t) => {
    if (t.status === 'running') t.status = 'done';
  });
  (currentWorkflowState.plan?.steps || []).forEach((s) => {
    if (s.status === 'pending' || s.status === 'running') s.status = 'done';
  });
  renderWorkflowPanel();
}

function setActivityPhase(phase) {
  // Kept for compatibility with any residual phase-pill UI.
  if (!currentActivityTimeline) return;
  currentActivityTimeline.querySelectorAll('.phase-pill').forEach((pill) => {
    const p = pill.dataset.phase;
    pill.classList.remove('active', 'done');
    if (p === phase) pill.classList.add('active');
    else if (
      (phase === 'literature' && p === 'database') ||
      (phase === 'synthesis' && (p === 'database' || p === 'literature'))
    ) {
      pill.classList.add('done');
    }
  });
}

function refreshActivitySummary() {
  if (!currentActivityTimeline) return;
  const textEl = currentActivityTimeline.querySelector('.activity-summary-text');
  if (textEl) {
    textEl.textContent = activityToolCount
      ? `Queried ${activityToolCount} source${activityToolCount > 1 ? 's' : ''}`
      : 'Research activity';
  }
}

function beginAssistantTurn() {
  if (welcome) welcome.style.display = 'none';
  activityToolCount = 0;
  initWorkflowState();

  const msg = document.createElement('div');
  msg.className = 'message assistant';

  const avatar = document.createElement('img');
  avatar.className = 'msg-avatar';
  avatar.src = 'assets/img/logo.gif';
  avatar.alt = '';

  const body = document.createElement('div');
  body.className = 'assistant-body';

  const activity = createActivityTimelineEl();
  currentActivityTimeline = activity;
  activateWorkflowPanel(activity, currentWorkflowState);
  currentThinkingTools = activity.querySelector('.activity-tools');

  const contentDiv = document.createElement('div');
  contentDiv.className = 'msg-content is-loading';

  body.appendChild(activity);
  body.appendChild(contentDiv);
  msg.appendChild(avatar);
  msg.appendChild(body);
  chatArea.appendChild(msg);

  currentPlanPanel = null;
  showContentLoading(contentDiv, 'Starting…');
  showStreamStatus('Starting…', '');
  chatArea.scrollTop = chatArea.scrollHeight;
  return contentDiv;
}

function refreshThinkingToolsHeader() {
  refreshActivitySummary();
}

function showContentLoading(contentDiv, label = 'Thinking...') {
  if (!contentDiv) return;
  contentDiv.classList.add('is-loading');
  contentDiv.classList.remove('is-streaming');
  hideStreamingCursor(contentDiv);
  let loading = contentDiv.querySelector('.msg-content-loading');
  if (!loading) {
    loading = document.createElement('div');
    loading.className = 'msg-content-loading';
    loading.innerHTML = '<div class="typing-dots"><span></span><span></span><span></span></div><span class="loading-label"></span>';
    contentDiv.appendChild(loading);
  }
  const labelEl = loading.querySelector('.loading-label');
  if (labelEl) labelEl.textContent = label;
}

function hideContentLoading(contentDiv) {
  if (!contentDiv) return;
  contentDiv.classList.remove('is-loading');
  contentDiv.querySelector('.msg-content-loading')?.remove();
}

function showStreamingCursor(contentDiv) {
  if (!contentDiv) return;
  contentDiv.classList.add('is-streaming');
  hideContentLoading(contentDiv);
  if (!contentDiv.querySelector('.streaming-cursor')) {
    const cursor = document.createElement('span');
    cursor.className = 'streaming-cursor';
    cursor.setAttribute('aria-hidden', 'true');
    contentDiv.appendChild(cursor);
  }
}

function hideStreamingCursor(contentDiv) {
  if (!contentDiv) return;
  contentDiv.classList.remove('is-streaming');
  contentDiv.querySelector('.streaming-cursor')?.remove();
}

function renderStreamingContent(contentDiv, text) {
  contentDiv.innerHTML = renderMarkdown(text);
  showStreamingCursor(contentDiv);
}

function collapseThinkingTools() {
  if (currentActivityTimeline) {
    currentActivityTimeline.classList.add('collapsed');
  }
}

function collapsePlanPanel() {
  if (!currentPlanPanel) return;
  currentPlanPanel.classList.add('collapsed');
}

function addToolIndicator(toolName, args, kindHint) {
  if (!currentThinkingTools) return null;
  const meta = friendlyTool(toolName, kindHint);
  const icon = meta.kind === 'literature' ? 'ri-article-line' : 'ri-database-2-line';
  const ind = document.createElement('div');
  ind.className = 'tool-indicator';
  ind.dataset.kind = meta.kind;
  ind.innerHTML = `
    <i class="${icon} tool-icon"></i>
    <div class="tool-indicator-body">
      <span class="tool-name">${escapeHtml(meta.label)}</span>
      <span class="tool-args">${escapeHtml(meta.desc)}${formatArgs(args) ? ' · ' + escapeHtml(formatArgs(args)) : ''}</span>
      <span class="tool-summary"></span>
    </div>
    <span class="tool-status">running...</span>
  `;
  currentThinkingTools.appendChild(ind);
  if (currentActivityTimeline) currentActivityTimeline.classList.remove('collapsed');
  activityToolCount += 1;
  refreshActivitySummary();
  chatArea.scrollTop = chatArea.scrollHeight;
  return ind;
}

function formatArgs(args) {
  if (!args || Object.keys(args).length === 0) return '';
  const parts = [];
  for (const [k, v] of Object.entries(args)) {
    let val = String(v);
    if (val.length > 30) val = val.substring(0, 30) + '...';
    parts.push(`${k}=${val}`);
  }
  return parts.join(', ');
}

function updateToolIndicator(ind, success, summary, errorKind) {
  const st = toolResultStatus({ success, error_kind: errorKind });
  ind.classList.remove('success', 'error', 'empty', 'missing');
  ind.classList.add(st === 'done' ? 'success' : st);
  const status = ind.querySelector('.tool-status');
  status.textContent = toolStatusLabel(st, errorKind);
  if (summary) {
    const summaryEl = ind.querySelector('.tool-summary');
    if (summaryEl) summaryEl.textContent = summary.substring(0, 120);
  }
  chatArea.scrollTop = chatArea.scrollHeight;
}

function addPlanPanel(data) {
  const panel = createPlanPanelEl(data, false);
  const body = currentThinkingTools?.parentElement;
  if (body) {
    body.insertBefore(panel, currentThinkingTools);
  } else {
    chatArea.appendChild(panel);
  }
  currentPlanPanel = panel;
  chatArea.scrollTop = chatArea.scrollHeight;
}

function updatePlanStep(stepData) {
  if (!currentPlanPanel) return;
  const el = currentPlanPanel.querySelector(`.plan-step[data-step="${stepData.step}"]`);
  if (!el) return;
  el.classList.remove('running', 'completed', 'skipped', 'failed');
  if (stepData.status) el.classList.add(stepData.status);
}

function looksLikeCollectionGuidance(text) {
  const t = (text || '').trim();
  if (!t || t.length < 4) return false;
  if (/\.(xlsx|xls|csv|tsv)\b/i.test(t)) return true;
  if (/log2?\s*ratio\s*\(\s*protein\s*\)/i.test(t)) return true;
  if (/log\s*2\s*\(\s*[A-Za-z0-9][\w.\-]*\s*\/\s*[A-Za-z0-9]/i.test(t)) return true;
  if (/\buse\b.+\.(?:xlsx|xls|csv)/i.test(t)) return true;
  if (/→|->|=>/.test(t) && /\.(xlsx|xls|csv)/i.test(t)) return true;
  if (/蛋白/.test(t) && /(定量|log|ratio|比值|定量表)/i.test(t)) return true;
  // Column-role corrections from Adjust-tables / chat (e.g. "column AA is position")
  if (/\bcolumn\b/i.test(t) && /\b(amino|position|residue|uniprot|protein|gene|sty|aa)\b/i.test(t)) {
    return true;
  }
  if (
    /\b(sty|aa|position|residue)\b/i.test(t) &&
    /\b(is|are|=|means?|等于|是)\b/i.test(t) &&
    /\b(amino|position|residue|site|位点|氨基酸)\b/i.test(t)
  ) {
    return true;
  }
  // Sample / sheet-as-sample (e.g. MCF7 / MDA-MB-231 sheets are different samples)
  if (/mismatch\s*sample/i.test(t)) return true;
  if (/sheet.+as.+(?:different\s+)?samples?/i.test(t)) return true;
  if (/(?:different|separate|distinct)\s+samples?/i.test(t) && /sheet/i.test(t)) return true;
  if (/use.+sheets?.+as.+samples?/i.test(t)) return true;
  if (/each\s+sheet.+(?:sample|cell\s*line)/i.test(t)) return true;
  if (/\bsamples?\b/i.test(t) && /\bsheets?\b/i.test(t)) return true;
  if (/cell\s*lines?/i.test(t) && /\b(sample|sheet|different|three)\b/i.test(t)) return true;
  if (/三个|不同/.test(t) && /sample|样品|细胞系|sheet/i.test(t)) return true;
  if (/样品不对|样品错|sample\s*(?:wrong|mismatch|incorrect)/i.test(t)) return true;
  // Combined-site / split-column Teach notes
  if (/site[- ]level/i.test(t)) return true;
  if (/split\s+(?:this\s+)?column/i.test(t)) return true;
  if (/\bsplit\b/i.test(t) && /\b(column|uniprot|amino|acide|acid|position|mod[_\s-]?sites?)\b/i.test(t)) {
    return true;
  }
  if (/phosphosite|mod[_\s-]?sites?/i.test(t) && /split|amino|acide|acid|position|column|uniprot/i.test(t)) {
    return true;
  }
  if (/protein\s*\+\s*phosphosite/i.test(t)) return true;
  if (/\w+\s+columns?\s+is\s+uniprot/i.test(t)) return true;
  if (/columns?\s+\w+.+(?:uniprot|gene).+(?:amino|position)/i.test(t)) return true;
  if (/missing\s+log2?\s*ratio\s*\(\s*protein\s*\)/i.test(t)) return true;
  if (/protein[- ]level/i.test(t)) return true;
  if (/do\s+not\s+skip/i.test(t)) return true;
  if (/protein\s*groups?/i.test(t) && /uniprot/i.test(t)) return true;
  return /为什么|为啥|没有|漏了|没读|读入|重新解析|condition|re-?parse|missing|should (?:use|include|read)|附表|定量表|extract\s+ptm|count\s+log|列名|表头|\bsample\b|样品|细胞系|\bsheet\b/i.test(
    t,
  );
}

async function sendCollectionGuidance(jobId, text, panel) {
  if (isStreaming) return;
  setSendButtonToStop();
  const abortController = new AbortController();
  currentAbortController = abortController;
  persistCollectionUserTurn(text).catch(() => {});
  addMessage('user', text);
  const pmidText = panel?.querySelector('.collection-pmid')?.textContent || '';
  const pmid = pmidText.replace(/^PMID\s+/i, '').trim() || null;
  const { panel: nextPanel, contentDiv } = beginCollectionTurn(jobId, pmid, {
    current_stage: 'stage5',
    next_stage: 'stage5',
    status: 'running',
    stages: {},
  });
  nextPanel.dataset.expectedStage = 'stage5';
  nextPanel.dataset.planModeLocked = 'focus';
  nextPanel.classList.remove('collapsed');
  showContentLoading(contentDiv, 'Applying your table guidance…');
  try {
    const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/guidance`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, resume: true }),
      signal: abortController.signal,
    });
    if (!res.ok) {
      let detail = `Guidance HTTP ${res.status}`;
      try {
        const errBody = await res.json();
        if (errBody?.detail) detail = String(errBody.detail);
      } catch (_) {
        /* ignore */
      }
      throw new Error(detail);
    }
    const body = await res.json();
    if (body.job) {
      updateCollectionPanel(nextPanel, {
        ...body.job,
        current_stage: 'stage5',
        currentStage: 'stage5',
        status: 'running',
      });
    }
    const ack = body.message || 'Re-parsing with your guidance…';
    contentDiv.innerHTML = `<p class="collection-answer-text" style="white-space:pre-wrap;">${formatCollectionAnswerHtml(ack)}</p>`;
    await streamCollectionJob(jobId, nextPanel, contentDiv);
  } catch (err) {
    if (err.name === 'AbortError') {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = '<p style="color:var(--text-muted);font-style:italic;">Guidance stopped.</p>';
      return;
    }
    hideContentLoading(contentDiv);
    contentDiv.innerHTML = `<p style="color:#c0392b;">${escapeHtml(err.message || 'Guidance failed')}</p>`;
  } finally {
    if (currentAbortController === abortController) currentAbortController = null;
    setSendButtonToSend();
  }
}

let pendingClarificationState = null;

function initClarificationModal() {
  // Clarification is rendered inline in chat (Biomni-style); no modal binding.
}

function normalizeClarifyOptions(rawOptions) {
  return (rawOptions || []).map((opt) => {
    if (typeof opt === 'string') return { label: opt, description: '' };
    return {
      label: opt.label || opt.value || '',
      description: opt.description || '',
      value: opt.value || opt.label || '',
    };
  }).filter((o) => o.label);
}

function showInlineClarification(contentDiv, payload) {
  if (!contentDiv) return;
  hideContentLoading(contentDiv);
  hideStreamingCursor(contentDiv);
  contentDiv.classList.remove('is-loading', 'is-streaming');

  const card = document.createElement('div');
  card.className = 'clarify-inline-card';
  card.setAttribute('role', 'form');
  card.setAttribute('aria-label', 'Research clarification');

  const intro = document.createElement('p');
  intro.className = 'clarify-inline-intro';
  intro.textContent = payload.intro || '';
  card.appendChild(intro);

  const fieldsWrap = document.createElement('div');
  fieldsWrap.className = 'clarify-inline-fields';

  (payload.fields || []).forEach((field, fieldIdx) => {
    const section = document.createElement('section');
    section.className = 'clarify-inline-field';
    section.dataset.fieldId = field.id;

    const title = document.createElement('div');
    title.className = 'clarify-inline-field-title';
    title.textContent = field.label || field.id;
    section.appendChild(title);

    if (field.prompt) {
      const prompt = document.createElement('div');
      prompt.className = 'clarify-inline-field-prompt';
      prompt.textContent = field.prompt;
      section.appendChild(prompt);
    }

    const opts = document.createElement('div');
    opts.className = 'clarify-inline-options';
    const options = normalizeClarifyOptions(field.options);
    options.forEach((opt, optIdx) => {
      const id = `clarify-${field.id}-${optIdx}-${Date.now()}`;
      const row = document.createElement('label');
      row.className = 'clarify-inline-option';
      row.htmlFor = id;

      const input = document.createElement('input');
      input.type = 'radio';
      input.name = `clarify-field-${field.id}`;
      input.id = id;
      input.value = opt.value || opt.label;
      input.addEventListener('change', () => {
        opts.querySelectorAll('.clarify-inline-option').forEach((el) => el.classList.remove('selected'));
        row.classList.add('selected');
        const custom = section.querySelector('.clarify-inline-custom');
        if (custom) custom.value = '';
      });

      const body = document.createElement('div');
      body.className = 'clarify-inline-option-body';
      const name = document.createElement('div');
      name.className = 'clarify-inline-option-label';
      name.textContent = opt.label;
      body.appendChild(name);
      if (opt.description) {
        const desc = document.createElement('div');
        desc.className = 'clarify-inline-option-desc';
        desc.textContent = opt.description;
        body.appendChild(desc);
      }

      row.appendChild(input);
      row.appendChild(body);
      opts.appendChild(row);
    });
    section.appendChild(opts);

    if (field.allow_custom) {
      const otherRow = document.createElement('label');
      otherRow.className = 'clarify-inline-option clarify-inline-other';
      const otherInput = document.createElement('input');
      otherInput.type = 'radio';
      otherInput.name = `clarify-field-${field.id}`;
      otherInput.value = '__other__';
      otherInput.addEventListener('change', () => {
        opts.querySelectorAll('.clarify-inline-option').forEach((el) => el.classList.remove('selected'));
        otherRow.classList.add('selected');
        section.querySelector('.clarify-inline-custom')?.focus();
      });
      const otherBody = document.createElement('div');
      otherBody.className = 'clarify-inline-option-body';
      otherBody.innerHTML = '<div class="clarify-inline-option-label">Other</div>';
      otherRow.appendChild(otherInput);
      otherRow.appendChild(otherBody);
      opts.appendChild(otherRow);

      const custom = document.createElement('input');
      custom.type = 'text';
      custom.className = 'clarify-inline-custom';
      custom.placeholder = field.placeholder || 'Other…';
      custom.addEventListener('input', () => {
        if (custom.value.trim()) {
          opts.querySelectorAll('input[type="radio"]').forEach((r) => {
            r.checked = r.value === '__other__';
          });
          opts.querySelectorAll('.clarify-inline-option').forEach((el) => el.classList.remove('selected'));
          otherRow.classList.add('selected');
        }
      });
      section.appendChild(custom);
    }

    fieldsWrap.appendChild(section);
    if (fieldIdx < (payload.fields || []).length - 1) {
      const sep = document.createElement('hr');
      sep.className = 'clarify-inline-sep';
      fieldsWrap.appendChild(sep);
    }
  });
  card.appendChild(fieldsWrap);

  const ft = payload.free_text || {};
  if (ft.label || ft.placeholder) {
    const freeWrap = document.createElement('div');
    freeWrap.className = 'clarify-inline-free';
    const freeLabel = document.createElement('div');
    freeLabel.className = 'clarify-inline-field-title';
    freeLabel.textContent = ft.label || '';
    freeWrap.appendChild(freeLabel);
    const freeInput = document.createElement('textarea');
    freeInput.className = 'clarify-inline-free-input';
    freeInput.rows = 2;
    freeInput.placeholder = ft.placeholder || '';
    freeWrap.appendChild(freeInput);
    card.appendChild(freeWrap);
  }

  const actions = document.createElement('div');
  actions.className = 'clarify-inline-actions';
  const skipBtn = document.createElement('button');
  skipBtn.type = 'button';
  skipBtn.className = 'clarify-inline-skip';
  skipBtn.textContent = payload.skip_label || 'Skip';
  skipBtn.addEventListener('click', () => handleClarificationSubmit(true));
  const submitBtn = document.createElement('button');
  submitBtn.type = 'button';
  submitBtn.className = 'clarify-inline-submit';
  submitBtn.innerHTML = `<i class="ri-play-fill"></i> ${escapeHtml(payload.submit_label || 'Submit')}`;
  submitBtn.addEventListener('click', () => handleClarificationSubmit(false));
  actions.appendChild(skipBtn);
  actions.appendChild(submitBtn);
  card.appendChild(actions);

  contentDiv.innerHTML = '';
  contentDiv.appendChild(card);
  chatArea.scrollTop = chatArea.scrollHeight;
}

function collectClarificationForm(root) {
  const card = root || document.querySelector('.clarify-inline-card');
  const selections = {};
  if (!card) return { selections, free_text: '' };

  card.querySelectorAll('.clarify-inline-field').forEach((section) => {
    const fieldId = section.dataset.fieldId;
    if (!fieldId) return;
    const custom = section.querySelector('.clarify-inline-custom');
    const customVal = custom?.value?.trim() || '';
    const checked = section.querySelector('input[type="radio"]:checked');
    if (customVal) {
      selections[fieldId] = customVal;
    } else if (checked && checked.value !== '__other__') {
      selections[fieldId] = checked.value || '';
    }
  });

  const freeText = card.querySelector('.clarify-inline-free-input')?.value?.trim() || '';
  return { selections, free_text: freeText };
}

function buildClarificationUserLabel(skip, selections, freeText, payload) {
  if (skip) {
    return payload?.skip_label || '跳过，直接执行';
  }
  const parts = [];
  const fields = payload?.fields || [];
  fields.forEach((field) => {
    const val = (selections[field.id] || '').trim();
    if (val) parts.push(`${field.label || field.id}: ${val}`);
  });
  if (freeText) {
    const noteLabel = payload?.free_text?.label || '补充';
    parts.push(`${noteLabel}: ${freeText}`);
  }
  if (parts.length) return parts.join(' · ');
  return payload?.submit_label || '开始研究';
}

function removeAssistantBubble(contentDiv) {
  const msg = contentDiv?.closest('.message.assistant');
  if (!msg) return;
  if (currentThinkingTools && msg.contains(currentThinkingTools)) {
    currentThinkingTools = null;
    currentActivityTimeline = null;
  }
  msg.remove();
}

async function handleClarificationSubmit(skip) {
  const state = pendingClarificationState;
  if (!state || isStreaming) return;

  const host = state.hostContent || document.querySelector('.clarify-inline-card')?.closest('.msg-content');
  const { selections, free_text: freeText } = skip
    ? { selections: {}, free_text: '' }
    : collectClarificationForm(host?.querySelector('.clarify-inline-card'));

  // Freeze the clarification card as submitted state
  const card = host?.querySelector('.clarify-inline-card');
  if (card) {
    card.classList.add('is-submitted');
    card.querySelectorAll('input, textarea, button').forEach((el) => {
      el.disabled = true;
    });
  }

  const userLabel = buildClarificationUserLabel(skip, selections, freeText, state.payload);
  addMessage('user', userLabel);
  chatHistory.push({ role: 'user', content: userLabel });

  setSendButtonToStop();
  const abortController = new AbortController();
  currentAbortController = abortController;
  pendingClarificationState = null;

  const assistantContent = beginAssistantTurn();

  try {
    await executeChatRequest({
      message: state.originalMessage,
      assistantContent,
      abortController,
      clarificationResponse: skip
        ? { skip: true, selections: {}, free_text: '' }
        : { skip: false, selections, free_text: freeText },
    });
  } catch (err) {
    if (err.name === 'AbortError') {
      hideContentLoading(assistantContent);
      hideStreamingCursor(assistantContent);
      collapseThinkingTools();
      collapsePlanPanel();
      assistantContent.innerHTML = '<p style="color:var(--text-muted);font-style:italic;">Generation stopped.</p>';
      return;
    }
    hideContentLoading(assistantContent);
    hideStreamingCursor(assistantContent);
    assistantContent.innerHTML = `<p style="color:#c0392b;">Connection error: ${escapeHtml(err.message)}</p>`;
    collapsePlanPanel();
  } finally {
    if (currentAbortController === abortController) currentAbortController = null;
    setSendButtonToSend();
    inputField.focus();
  }
}

async function executeChatRequest({
  message,
  assistantContent,
  abortController,
  clarificationResponse = null,
}) {
  let fullText = '';
  let followUps = [];
  let clarificationPayload = null;

  const body = {
    message,
    mode: agentChatMode,
    session_id: sessionId,
    conversation_id: conversationId,
    history: chatHistory.slice(-10),
  };
  if (clarificationResponse) {
    body.clarification_response = clarificationResponse;
  }

  const response = await fetch(CHAT_URL, {
    method: 'POST',
    headers: apiHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(body),
    signal: abortController.signal,
  });

  const newSessionId = response.headers.get('X-Session-Id');
  if (newSessionId) {
    sessionId = newSessionId;
    persistSessionForConversation(conversationId, newSessionId);
  }

  const newConvId = response.headers.get('X-Conversation-Id');
  if (newConvId) persistConversationId(newConvId);

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }

  await parseSseStream(response, async (currentEvent, data) => {
    if (currentEvent === 'text') {
      fullText += data.content;
      renderStreamingContent(assistantContent, fullText);
      chatArea.scrollTop = chatArea.scrollHeight;
    } else if (currentEvent === 'phase_update') {
      setActivityPhase(data.phase);
      handlePhaseUpdate(data.phase, data.label);
      showStreamStatus(data.label || 'Working…', '');
      const earlyPhases = ['planning', 'resolving', 'clarifying', 'retrieving_tools'];
      if (earlyPhases.includes(data.phase) || data.phase === 'database') {
        showContentLoading(assistantContent, data.label || 'Working…');
      } else if (data.phase === 'literature') {
        showContentLoading(assistantContent, data.label || 'Searching literature…');
      } else if (data.phase === 'synthesis') {
        showContentLoading(assistantContent, data.label || 'Generating answer…');
      }
    } else if (currentEvent === 'plan_created') {
      showContentLoading(assistantContent, 'Investigating…');
      handlePlanCreated(data);
    } else if (currentEvent === 'step_started') {
      updatePlanStep(data);
    } else if (currentEvent === 'step_completed') {
      updatePlanStep(data);
    } else if (currentEvent === 'literature_search') {
      handleLiteratureSearch(data);
    } else if (currentEvent === 'tool_call') {
      handleWorkflowToolCall(data);
      showContentLoading(assistantContent, data.label || 'Querying…');
      addToolIndicator(data.tool_name, data.arguments, data.kind);
    } else if (currentEvent === 'tool_result') {
      handleWorkflowToolResult(data);
      const indicators = currentThinkingTools?.querySelectorAll('.tool-indicator') || [];
      const lastInd = indicators[indicators.length - 1];
      if (lastInd) updateToolIndicator(lastInd, data.success, data.summary, data.error_kind);
    } else if (currentEvent === 'sources') {
      window.__lastSources = data.citations || [];
      const synthLabel = /[\u4e00-\u9fff]/.test(fullText || message || '')
        ? '撰写回答中…' : 'Writing answer…';
      showStreamStatus(synthLabel, '');
      if (fullText) {
        hideContentLoading(assistantContent);
        showStreamingCursor(assistantContent);
      } else {
        showContentLoading(assistantContent, synthLabel);
      }
      renderSourcesDrawer(window.__lastSources, 'database');
    } else if (currentEvent === 'follow_up_questions') {
      followUps = data.questions || [];
    } else if (currentEvent === 'clarification_request') {
      clarificationPayload = data;
    } else if (currentEvent === 'done') {
      showStreamStatus('');
      markWorkflowDone();
      collapseThinkingTools();
      collapsePlanPanel();
    } else if (currentEvent === 'error') {
      showStreamStatus('');
      if (currentWorkflowState) currentWorkflowState.status = 'error';
      markWorkflowDone();
      hideContentLoading(assistantContent);
      hideStreamingCursor(assistantContent);
      assistantContent.innerHTML = `<p style="color:#c0392b;">${escapeHtml(data.message)}</p>`;
      collapsePlanPanel();
    }
  });

  if (clarificationPayload) {
    pendingClarificationState = {
      originalMessage: message,
      payload: clarificationPayload,
      hostContent: assistantContent,
    };
    showInlineClarification(assistantContent, clarificationPayload);
    return { clarification: true };
  }

  hideContentLoading(assistantContent);
  hideStreamingCursor(assistantContent);
  if (fullText) {
    const safeText = sanitizeUserVisibleText(fullText);
    const displayText = stripTrailingInvite(safeText);
    assistantContent.innerHTML = renderMarkdown(displayText);
    chatHistory.push({ role: 'assistant', content: safeText });
    attachMessageActions(assistantContent, fullText);
    const qs = followUps.length ? followUps : extractNextStepQuestions(fullText);
    mountFollowUpPanel(assistantContent.closest('.assistant-body'), qs, detectLangFromText(fullText));
  } else if (!assistantContent.querySelector('p[style*="c0392b"]')) {
    assistantContent.innerHTML = '<p style="color:var(--text-muted);">No response received.</p>';
  }
  collapseThinkingTools();
  collapsePlanPanel();
  await loadConversationList();
  if (conversationId && fullText) {
    isStreaming = false;
    await refreshAssistantContentFromStore(assistantContent);
  }
  return { clarification: false, fullText };
}

async function sendMessage() {
  const text = inputField.value.trim();
  const files = [...pendingFiles];
  if ((!text && !files.length) || isStreaming) return;

  inputField.value = '';
  resizeInputField();

  // Stage5 free-text intervention from the bottom input-wrapper: when a collection
  // job is paused with Adjust tables / teach UI (or stage5/6 awaiting), route the
  // message to /guidance instead of starting a new chat / collection job.
  const guidanceTarget = findCollectionGuidanceTarget();
  if (guidanceTarget && !files.length && text) {
    const openTeach = Boolean(
      guidanceTarget.contentDiv?.querySelector('.collection-teach:not(.is-stale)'),
    );
    const acceptFlag = guidanceTarget.panel.dataset.acceptGuidance === '1';
    // When Adjust tables / teach UI is open, any free-text from the input box is
    // treated as Stage5 guidance. Otherwise only guidance-like messages route here.
    if (openTeach || acceptFlag || looksLikeCollectionGuidance(text)) {
      activeCollectionPanel = guidanceTarget.panel;
      await sendCollectionGuidance(guidanceTarget.jobId, text, guidanceTarget.panel);
      refreshCollectionInputPlaceholder();
      return;
    }
  }

  let routeCollection = files.some((f) => classifyUploadKind(f.name) !== 'unknown');
  if (!routeCollection) {
    try {
      const intent = await classifyIntent(text, files.map((f) => f.name));
      routeCollection = Boolean(intent.route_collection);
    } catch (err) {
      console.warn('Intent classify failed, defaulting to chat:', err);
    }
  }

  if (routeCollection) {
    await startCollectionFlow(text, files);
    return;
  }

  setSendButtonToStop();
  const abortController = new AbortController();
  currentAbortController = abortController;
  clearPendingFiles();

  addMessage('user', text);
  chatHistory.push({ role: 'user', content: text });

  const assistantContent = beginAssistantTurn();

  try {
    await executeChatRequest({
      message: text,
      assistantContent,
      abortController,
    });
  } catch (err) {
    if (err.name === 'AbortError') {
      hideContentLoading(assistantContent);
      hideStreamingCursor(assistantContent);
      collapseThinkingTools();
      collapsePlanPanel();
      assistantContent.innerHTML = '<p style="color:var(--text-muted);font-style:italic;">Generation stopped.</p>';
      return;
    }
    hideContentLoading(assistantContent);
    hideStreamingCursor(assistantContent);
    assistantContent.innerHTML = `<p style="color:#c0392b;">Connection error: ${escapeHtml(err.message)}</p>
      <p style="font-size:13px;color:var(--text-muted);">Make sure the qPTM Agent backend is running at ${escapeHtml(CHAT_URL)}</p>`;
    collapsePlanPanel();
  } finally {
    if (currentAbortController === abortController) currentAbortController = null;
    setSendButtonToSend();
    inputField.focus();
  }
}

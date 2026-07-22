<?php
/**
 * qPTM Agent — Chat frontend page
 *
 * Deploy this file as /agent.php (or /agent via URL rewrite) on the qPTM web server.
 * It serves the standalone HTML chat interface that connects to the Python FastAPI backend.
 *
 * The backend API URL is auto-detected:
 *   - If on the same server: http://localhost:8100/chat
 *   - Override by setting $BACKEND_URL below
 */

// Backend API URL — change if the Python backend runs on a different host/port
$BACKEND_URL = 'http://localhost:8100/chat';

// Allow overriding via environment variable
$envUrl = getenv('QPTM_AGENT_BACKEND_URL');
if ($envUrl) {
    $BACKEND_URL = $envUrl . '/chat';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>qPTM Agent — PTM Research Assistant</title>
<style>
/* ── Reset & base ─────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
:root {
  --bg: #faf9f3;
  --surface: #ffffff;
  --border: #e0ddd5;
  --text: #1a1a1a;
  --text-muted: #6b6b6b;
  --primary: #0279ee;
  --primary-light: #e8f1fd;
  --accent: #ff9400;
  --green: #75a025;
  --pink: #fd9bed;
  --stage1: #0279ee;
  --stage2: #75a025;
  --stage3: #ff9400;
  --radius: 10px;
  --shadow: 0 1px 3px rgba(0,0,0,0.08);
  --shadow-lg: 0 4px 16px rgba(0,0,0,0.12);
  font-family: -apple-system, BlinkMacSystemFont, "Liberation Sans", "Segoe UI", Arial, sans-serif;
}
body { background: var(--bg); color: var(--text); line-height: 1.6; height: 100vh; display: flex; flex-direction: column; }

/* ── Header ───────────────────────────────────────────── */
.header {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 12px 24px;
  display: flex;
  align-items: center;
  gap: 16px;
  flex-shrink: 0;
}
.header-logo {
  font-size: 20px;
  font-weight: 700;
  color: var(--primary);
  letter-spacing: -0.5px;
}
.header-logo span { color: var(--text); font-weight: 400; font-size: 14px; margin-left: 8px; }
.header-link { margin-left: auto; font-size: 13px; color: var(--text-muted); text-decoration: none; }
.header-link:hover { color: var(--primary); }

/* ── Stage indicator ──────────────────────────────────── */
.stage-bar {
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  padding: 8px 24px;
  display: flex;
  align-items: center;
  gap: 0;
  flex-shrink: 0;
  overflow-x: auto;
}
.stage-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 12px;
  font-size: 13px;
  color: var(--text-muted);
  white-space: nowrap;
  transition: color 0.3s;
}
.stage-item.active { font-weight: 600; }
.stage-item.active .stage-dot { transform: scale(1.3); }
.stage-item.done { color: var(--green); }
.stage-item.done .stage-dot { background: var(--green); }
.stage-dot {
  width: 10px; height: 10px;
  border-radius: 50%;
  background: var(--border);
  transition: all 0.3s;
  flex-shrink: 0;
}
.stage-item:nth-child(1).active .stage-dot { background: var(--stage1); }
.stage-item:nth-child(3).active .stage-dot { background: var(--stage2); }
.stage-item:nth-child(5).active .stage-dot { background: var(--stage3); }
.stage-arrow { color: var(--border); font-size: 14px; }

/* ── Chat area ────────────────────────────────────────── */
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.chat-area::-webkit-scrollbar { width: 6px; }
.chat-area::-webkit-scrollbar-thumb { background: var(--border); border-radius: 3px; }

/* ── Welcome screen ───────────────────────────────────── */
.welcome {
  max-width: 720px;
  margin: auto;
  text-align: center;
  padding: 40px 20px;
}
.welcome h1 { font-size: 26px; margin-bottom: 8px; color: var(--text); }
.welcome p { color: var(--text-muted); margin-bottom: 28px; font-size: 15px; }
.example-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 12px;
  text-align: left;
}
.example-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 16px;
  cursor: pointer;
  transition: all 0.2s;
}
.example-card:hover {
  border-color: var(--primary);
  box-shadow: var(--shadow-lg);
  transform: translateY(-1px);
}
.example-card .ex-stage {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 6px;
}
.example-card:nth-child(1) .ex-stage { color: var(--stage1); }
.example-card:nth-child(2) .ex-stage { color: var(--stage2); }
.example-card:nth-child(3) .ex-stage { color: var(--stage3); }
.example-card:nth-child(4) .ex-stage { color: var(--stage1); }
.example-card .ex-text { font-size: 14px; color: var(--text); }

/* ── Messages ─────────────────────────────────────────── */
.message {
  max-width: 820px;
  width: 100%;
  margin: 0 auto;
  display: flex;
  gap: 12px;
  animation: fadeIn 0.3s ease;
}
@keyframes fadeIn { from { opacity: 0; transform: translateY(8px); } to { opacity: 1; transform: translateY(0); } }
.message.user { flex-direction: row-reverse; }
.msg-avatar {
  width: 36px; height: 36px;
  border-radius: 50%;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
}
.message.user .msg-avatar { background: var(--primary); color: white; }
.message.assistant .msg-avatar { background: var(--green); color: white; }
.msg-content {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 14px 18px;
  flex: 1;
  min-width: 0;
  word-wrap: break-word;
}
.message.user .msg-content { background: var(--primary-light); border-color: var(--primary-light); }
.msg-content p { margin-bottom: 8px; }
.msg-content p:last-child { margin-bottom: 0; }
.msg-content strong { font-weight: 700; }
.msg-content em { font-style: italic; }
.msg-content code {
  background: #f0ede5;
  padding: 2px 6px;
  border-radius: 4px;
  font-size: 13px;
  font-family: "SF Mono", "Fira Code", monospace;
}
.msg-content pre {
  background: #f5f3ed;
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 12px;
  overflow-x: auto;
  margin: 8px 0;
}
.msg-content pre code { background: none; padding: 0; }
.msg-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: 13px;
}
.msg-content th, .msg-content td {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}
.msg-content th { background: #f5f3ed; font-weight: 600; }
.msg-content tr:nth-child(even) { background: #faf9f3; }
.msg-content ul, .msg-content ol { margin: 8px 0 8px 20px; }
.msg-content li { margin-bottom: 4px; }
.msg-content a { color: var(--primary); text-decoration: none; }
.msg-content a:hover { text-decoration: underline; }

/* ── Tool call indicators ─────────────────────────────── */
.tool-indicator {
  max-width: 820px;
  width: 100%;
  margin: 0 auto;
  padding: 8px 14px;
  background: #f5f3ed;
  border: 1px solid var(--border);
  border-radius: 8px;
  font-size: 13px;
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 8px;
  animation: fadeIn 0.2s ease;
}
.tool-indicator .tool-icon { font-size: 14px; }
.tool-indicator .tool-name { font-weight: 600; color: var(--text); }
.tool-indicator .tool-status { margin-left: auto; font-size: 12px; }
.tool-indicator.success .tool-status { color: var(--green); }
.tool-indicator.error .tool-status { color: #d44; }
.tool-indicator .spinner {
  width: 14px; height: 14px;
  border: 2px solid var(--border);
  border-top-color: var(--primary);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }

/* ── Stage update banner ──────────────────────────────── */
.stage-banner {
  max-width: 820px;
  width: 100%;
  margin: 0 auto;
  padding: 10px 16px;
  background: var(--primary-light);
  border: 1px solid #c5d9f0;
  border-radius: 8px;
  font-size: 13px;
  color: var(--primary);
  display: flex;
  align-items: flex-start;
  gap: 8px;
  animation: fadeIn 0.3s ease;
}
.stage-banner .banner-icon { font-size: 16px; flex-shrink: 0; margin-top: 1px; }
.stage-banner strong { font-weight: 700; }

/* ── Typing indicator ─────────────────────────────────── */
.typing-dots {
  display: inline-flex;
  gap: 4px;
  padding: 4px 0;
}
.typing-dots span {
  width: 8px; height: 8px;
  border-radius: 50%;
  background: var(--text-muted);
  animation: bounce 1.4s ease-in-out infinite;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

/* ── Input area ───────────────────────────────────────── */
.input-area {
  background: var(--surface);
  border-top: 1px solid var(--border);
  padding: 16px 24px;
  flex-shrink: 0;
}
.input-wrapper {
  max-width: 820px;
  margin: 0 auto;
  display: flex;
  gap: 10px;
  align-items: flex-end;
}
.input-field {
  flex: 1;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 12px 16px;
  font-size: 15px;
  font-family: inherit;
  resize: none;
  max-height: 120px;
  min-height: 46px;
  transition: border-color 0.2s;
  background: var(--bg);
}
.input-field:focus {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px var(--primary-light);
}
.send-btn {
  background: var(--primary);
  color: white;
  border: none;
  border-radius: var(--radius);
  padding: 12px 20px;
  font-size: 15px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
  white-space: nowrap;
  height: 46px;
}
.send-btn:hover { background: #0260c0; }
.send-btn:disabled { background: var(--border); cursor: not-allowed; }
.input-hint {
  max-width: 820px;
  margin: 6px auto 0;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}

/* ── Responsive ───────────────────────────────────────── */
@media (max-width: 768px) {
  .header { padding: 10px 16px; }
  .chat-area { padding: 16px; }
  .input-area { padding: 12px 16px; }
  .example-grid { grid-template-columns: 1fr; }
  .message { max-width: 100%; }
}
</style>
</head>
<body>

<!-- ── Header ──────────────────────────────────────────── -->
<div class="header">
  <div class="header-logo">qPTM Agent<span>PTM Research Assistant</span></div>
  <a class="header-link" href="https://qptm3.omicsbio.info" target="_blank">qPTM Database ↗</a>
</div>

<!-- ── Stage indicator ─────────────────────────────────── -->
<div class="stage-bar" id="stageBar">
  <div class="stage-item" data-stage="idle">
    <div class="stage-dot"></div>
    <span>Start</span>
  </div>
  <span class="stage-arrow">→</span>
  <div class="stage-item" data-stage="conditions">
    <div class="stage-dot"></div>
    <span>Stage 1: Where &amp; When</span>
  </div>
  <span class="stage-arrow">→</span>
  <div class="stage-item" data-stage="kinase">
    <div class="stage-dot"></div>
    <span>Stage 2: Who</span>
  </div>
  <span class="stage-arrow">→</span>
  <div class="stage-item" data-stage="function">
    <div class="stage-dot"></div>
    <span>Stage 3: Why It Matters</span>
  </div>
</div>

<!-- ── Chat area ───────────────────────────────────────── -->
<div class="chat-area" id="chatArea">
  <div class="welcome" id="welcome">
    <h1>qPTM Agent</h1>
    <p>Your AI guide for exploring protein post-translational modifications.<br>
       Search 14M+ quantitative PTM events, identify kinases, and discover functional consequences.</p>
    <div class="example-grid">
      <div class="example-card" onclick="sendExample('Under what conditions is TP53 S15 phosphorylated?')">
        <div class="ex-stage">Stage 1 — Where &amp; When</div>
        <div class="ex-text">Under what conditions is TP53 S15 phosphorylated?</div>
      </div>
      <div class="example-card" onclick="sendExample('Which kinase phosphorylates AKT1 S473?')">
        <div class="ex-stage">Stage 2 — Who</div>
        <div class="ex-text">Which kinase phosphorylates AKT1 S473?</div>
      </div>
      <div class="example-card" onclick="sendExample('What is the functional effect of phosphorylating TP53 S15?')">
        <div class="ex-stage">Stage 3 — Why It Matters</div>
        <div class="ex-text">What is the functional effect of phosphorylating TP53 S15?</div>
      </div>
      <div class="example-card" onclick="sendExample('Search for acetylation events on histone H3 in human')">
        <div class="ex-stage">Stage 1 — Where &amp; When</div>
        <div class="ex-text">Search for acetylation events on histone H3 in human</div>
      </div>
    </div>
  </div>
</div>

<!-- ── Input area ──────────────────────────────────────── -->
<div class="input-area">
  <div class="input-wrapper">
    <textarea class="input-field" id="inputField"
      placeholder="Ask about PTM sites, conditions, kinases, or functional effects..."
      rows="1" onkeydown="handleKey(event)"></textarea>
    <button class="send-btn" id="sendBtn" onclick="sendMessage()">Send</button>
  </div>
  <div class="input-hint">Press Enter to send, Shift+Enter for new line</div>
</div>

<script>
// ── Configuration ────────────────────────────────────────
// Backend URL — injected by PHP, can be overridden by environment variable
const CHAT_URL = '<?php echo htmlspecialchars($BACKEND_URL, ENT_QUOTES); ?>';

// ── State ────────────────────────────────────────────────
let sessionId = null;
let isStreaming = false;
let chatHistory = [];
const stageOrder = ['idle', 'conditions', 'kinase', 'function', 'synthesis'];

// ── DOM elements ─────────────────────────────────────────
const chatArea = document.getElementById('chatArea');
const welcome = document.getElementById('welcome');
const inputField = document.getElementById('inputField');
const sendBtn = document.getElementById('sendBtn');
const stageBar = document.getElementById('stageBar');

// ── Auto-resize textarea ─────────────────────────────────
inputField.addEventListener('input', () => {
  inputField.style.height = 'auto';
  inputField.style.height = Math.min(inputField.scrollHeight, 120) + 'px';
});

// ── Key handler ──────────────────────────────────────────
function handleKey(e) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
}

// ── Send example question ────────────────────────────────
function sendExample(text) {
  inputField.value = text;
  sendMessage();
}

// ── Markdown rendering (lightweight) ─────────────────────
function renderMarkdown(text) {
  if (!text) return '';
  let html = text;

  // Code blocks (```...```)
  html = html.replace(/```(\w*)\n?([\s\S]*?)```/g, (m, lang, code) =>
    `<pre><code>${escapeHtml(code.trim())}</code></pre>`);

  // Inline code (`...`)
  html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

  // Bold (**...**)
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');

  // Italic (*...*)
  html = html.replace(/(?<!\*)\*([^*]+)\*(?!\*)/g, '<em>$1</em>');

  // Links [text](url)
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank">$1</a>');

  // Tables (pipe-delimited)
  html = renderTables(html);

  // Headers (### ...)
  html = html.replace(/^### (.+)$/gm, '<p><strong>$1</strong></p>');
  html = html.replace(/^## (.+)$/gm, '<p><strong>$1</strong></p>');

  // Lists
  html = renderLists(html);

  // Line breaks (preserve paragraph structure)
  html = html.replace(/\n\n/g, '</p><p>');
  html = html.replace(/\n/g, '<br>');

  // Wrap in paragraphs
  if (!html.startsWith('<')) html = '<p>' + html + '</p>';

  return html;
}

function renderTables(text) {
  const lines = text.split('\n');
  let result = [];
  let inTable = false;
  let tableLines = [];

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i].trim();
    if (line.startsWith('|') && line.endsWith('|')) {
      if (!inTable) { inTable = true; tableLines = []; }
      tableLines.push(line);
    } else {
      if (inTable) {
        result.push(buildTable(tableLines));
        inTable = false;
        tableLines = [];
      }
      result.push(lines[i]);
    }
  }
  if (inTable) result.push(buildTable(tableLines));
  return result.join('\n');
}

function buildTable(lines) {
  if (lines.length < 2) return lines.join('\n');
  const parseRow = (line) => line.split('|').map(c => c.trim()).filter(c => c !== '');
  const headers = parseRow(lines[0]);
  const separator = lines[1];
  const isSeparator = /^[\s|:-]+$/.test(separator);
  const dataStart = isSeparator ? 2 : 1;
  let html = '<table><thead><tr>';
  headers.forEach(h => html += `<th>${h}</th>`);
  html += '</tr></thead><tbody>';
  for (let i = dataStart; i < lines.length; i++) {
    const cells = parseRow(lines[i]);
    html += '<tr>';
    cells.forEach(c => html += `<td>${c}</td>`);
    html += '</tr>';
  }
  html += '</tbody></table>';
  return html;
}

function renderLists(text) {
  const lines = text.split('\n');
  let result = [];
  let inList = false;
  let listType = '';

  for (let line of lines) {
    const ulMatch = line.match(/^\s*[-]\s+(.+)/);
    const olMatch = line.match(/^\s*\d+\.\s+(.+)/);
    if (ulMatch) {
      if (!inList || listType !== 'ul') {
        if (inList) result.push(`</${listType}>`);
        result.push('<ul>');
        inList = true; listType = 'ul';
      }
      result.push(`<li>${ulMatch[1]}</li>`);
    } else if (olMatch) {
      if (!inList || listType !== 'ol') {
        if (inList) result.push(`</${listType}>`);
        result.push('<ol>');
        inList = true; listType = 'ol';
      }
      result.push(`<li>${olMatch[1]}</li>`);
    } else {
      if (inList) { result.push(`</${listType}>`); inList = false; }
      result.push(line);
    }
  }
  if (inList) result.push(`</${listType}>`);
  return result.join('\n');
}

function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// ── Add message to chat ──────────────────────────────────
function addMessage(role, content) {
  if (welcome) welcome.style.display = 'none';

  const msg = document.createElement('div');
  msg.className = `message ${role}`;

  const avatar = document.createElement('div');
  avatar.className = 'msg-avatar';
  avatar.textContent = role === 'user' ? 'U' : 'A';

  const contentDiv = document.createElement('div');
  contentDiv.className = 'msg-content';
  contentDiv.innerHTML = role === 'user' ? escapeHtml(content) : renderMarkdown(content);

  msg.appendChild(avatar);
  msg.appendChild(contentDiv);
  chatArea.appendChild(msg);
  chatArea.scrollTop = chatArea.scrollHeight;
  return contentDiv;
}

// ── Add tool indicator ───────────────────────────────────
function addToolIndicator(toolName, arguments) {
  const ind = document.createElement('div');
  ind.className = 'tool-indicator';
  ind.innerHTML = `
    <span class="spinner"></span>
    <span class="tool-icon">&#128295;</span>
    <span class="tool-name">${toolName}</span>
    <span style="color: var(--text-muted); font-size: 12px;">${formatArgs(arguments)}</span>
    <span class="tool-status">running...</span>
  `;
  chatArea.appendChild(ind);
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

function updateToolIndicator(ind, success, summary) {
  ind.classList.remove('success', 'error');
  ind.classList.add(success ? 'success' : 'error');
  const spinner = ind.querySelector('.spinner');
  if (spinner) spinner.style.display = 'none';
  const status = ind.querySelector('.tool-status');
  status.textContent = success ? '\u2713 done' : '\u2717 error';
  if (summary) {
    const summarySpan = document.createElement('span');
    summarySpan.style.cssText = 'color: var(--text-muted); font-size: 12px; margin-left: 8px; max-width: 300px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;';
    summarySpan.textContent = summary.substring(0, 80);
    ind.appendChild(summarySpan);
  }
  chatArea.scrollTop = chatArea.scrollHeight;
}

// ── Add stage banner ─────────────────────────────────────
function addStageBanner(label, description) {
  const banner = document.createElement('div');
  banner.className = 'stage-banner';
  banner.innerHTML = `
    <span class="banner-icon">&#128205;</span>
    <div><strong>${label}</strong><br>${description}</div>
  `;
  chatArea.appendChild(banner);
  chatArea.scrollTop = chatArea.scrollHeight;
}

// ── Update stage indicator ───────────────────────────────
function updateStageIndicator(stage) {
  const stageIdx = stageOrder.indexOf(stage);
  const items = stageBar.querySelectorAll('.stage-item');
  items.forEach((item, i) => {
    item.classList.remove('active', 'done');
    if (i < stageIdx) item.classList.add('done');
    if (i === stageIdx) item.classList.add('active');
  });
}

// ── Send message (SSE streaming via fetch) ───────────────
async function sendMessage() {
  const text = inputField.value.trim();
  if (!text || isStreaming) return;

  isStreaming = true;
  sendBtn.disabled = true;
  inputField.value = '';
  inputField.style.height = 'auto';

  // Add user message
  addMessage('user', text);
  chatHistory.push({ role: 'user', content: text });

  // Create assistant message placeholder
  const assistantContent = addMessage('assistant', '');
  let fullText = '';
  let typingDots = null;

  // Add typing indicator
  typingDots = document.createElement('div');
  typingDots.className = 'typing-dots';
  typingDots.innerHTML = '<span></span><span></span><span></span>';
  assistantContent.appendChild(typingDots);

  try {
    const response = await fetch(CHAT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        session_id: sessionId,
        history: chatHistory.slice(-10),
      }),
    });

    // Get session ID from response headers
    const newSessionId = response.headers.get('X-Session-Id');
    if (newSessionId) sessionId = newSessionId;

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

    // Read SSE stream
    const reader = response.body.getReader();
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });
      const lines = buffer.split('\n');
      buffer = lines.pop();

      let currentEvent = null;
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          currentEvent = line.substring(7).trim();
        } else if (line.startsWith('data: ') && currentEvent) {
          const data = JSON.parse(line.substring(6));

          if (currentEvent === 'text') {
            if (typingDots) { typingDots.remove(); typingDots = null; }
            fullText += data.content;
            assistantContent.innerHTML = renderMarkdown(fullText);
            chatArea.scrollTop = chatArea.scrollHeight;
          }
          else if (currentEvent === 'tool_call') {
            if (typingDots) { typingDots.remove(); typingDots = null; }
            const ind = addToolIndicator(data.tool_name, data.arguments);
            ind.dataset.toolName = data.tool_name;
          }
          else if (currentEvent === 'tool_result') {
            const indicators = chatArea.querySelectorAll('.tool-indicator');
            const lastInd = indicators[indicators.length - 1];
            if (lastInd) {
              updateToolIndicator(lastInd, data.success, data.summary);
            }
          }
          else if (currentEvent === 'stage_update') {
            updateStageIndicator(data.stage);
            if (data.description) {
              addStageBanner(data.label, data.description);
            }
          }
          else if (currentEvent === 'error') {
            if (typingDots) { typingDots.remove(); typingDots = null; }
            assistantContent.innerHTML = `<p style="color: #d44;">${data.message}</p>`;
          }
          else if (currentEvent === 'done') {
            // Stream complete
          }

          currentEvent = null;
        }
      }
    }

    // Save assistant response to history
    if (fullText) {
      chatHistory.push({ role: 'assistant', content: fullText });
    }

  } catch (err) {
    if (typingDots) { typingDots.remove(); typingDots = null; }
    assistantContent.innerHTML = `<p style="color: #d44;">Connection error: ${err.message}</p>
      <p style="font-size: 13px; color: var(--text-muted);">Make sure the qPTM Agent backend is running at ${CHAT_URL}</p>`;
  } finally {
    isStreaming = false;
    sendBtn.disabled = false;
    inputField.focus();
  }
}
</script>
</body>
</html>

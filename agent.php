<?php
/**
 * qPTM Agent — Chat frontend page
 *
 * Same-origin /agent-api/* is proxied by Apache to uvicorn :8100.
 */

$BACKEND_URL = '/agent-api/chat';
$envUrl = getenv('QPTM_AGENT_BACKEND_URL');
if ($envUrl) {
    $BACKEND_URL = rtrim($envUrl, '/') . '/chat';
}
?>
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>qPTM | Agent</title>
<script src="assets/js/include.js"></script>
<style>
/* Agent layout — inherits site CSS variables from style.css */
body.agent-page {
  height: 100vh;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  --agent-content-width: 1000px;
}

.agent-shell {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: row;
  background: linear-gradient(180deg, #e0edff 0%, #eef5ff 60%, var(--bg) 100%);
}

/* ── Sidebar ──────────────────────────────────────────── */
.agent-sidebar {
  width: 260px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.92);
  border-right: 1px solid var(--border);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.sidebar-new-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  margin: 14px 12px 10px;
  padding: 10px 14px;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--bg-white);
  color: var(--primary);
  font-size: 14px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.sidebar-new-btn:hover {
  background: var(--primary-light);
  border-color: var(--primary-medium);
}
.sidebar-history-label {
  padding: 8px 16px 6px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.6px;
  color: var(--text-muted);
}
.sidebar-history {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px 12px;
}
.sidebar-history::-webkit-scrollbar { width: 4px; }
.sidebar-history::-webkit-scrollbar-thumb { background: var(--border-dark); border-radius: 2px; }
.sidebar-item {
  padding: 10px 12px;
  margin-bottom: 4px;
  border-radius: 8px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: background 0.15s;
  border: 1px solid transparent;
}
.sidebar-item:hover { background: var(--primary-light); }
.sidebar-item.active {
  background: var(--primary-light);
  border-color: var(--primary-medium);
  color: var(--primary);
  font-weight: 600;
}
.sidebar-empty {
  padding: 12px;
  font-size: 12px;
  color: var(--text-muted);
  text-align: center;
}

.agent-main {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
}

/* ── Stage indicator ──────────────────────────────────── */
/* ── Chat area ────────────────────────────────────────── */
.chat-area {
  flex: 1;
  overflow-y: auto;
  padding: 28px 32px;
  display: flex;
  flex-direction: column;
  gap: 18px;
  scroll-behavior: smooth;
}
.chat-area::-webkit-scrollbar { width: 5px; }
.chat-area::-webkit-scrollbar-thumb {
  background: rgba(14, 116, 211, 0.25);
  border-radius: 3px;
}
.chat-area::-webkit-scrollbar-thumb:hover { background: rgba(14, 116, 211, 0.4); }

/* ── Welcome screen ───────────────────────────────────── */
.welcome {
  max-width: var(--agent-content-width);
  margin: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 40px 20px 32px;
  animation: welcomeIn 0.6s ease;
}
@keyframes welcomeIn {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}
.welcome-badge {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 0 0 0 16px;
  margin-left: 16px;
  font-size: 16px;
  font-weight: 500;
  letter-spacing: 0.1px;
  color: #0e74d3;
  background: transparent;
  border: none;
  border-left: 1px solid rgba(179, 204, 245, 0.9);
  border-radius: 0;
  box-shadow: none;
  white-space: nowrap;
}
.welcome-badge i { font-size: 18px; color: var(--primary); }
.welcome-header {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 28px;
  padding: 12px 28px 12px 18px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(232, 242, 255, 0.88) 100%);
  border: 1px solid var(--border);
  border-radius: 48px;
  box-shadow: 0 8px 24px rgba(14, 116, 211, 0.14);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
}
.welcome-logo {
  height: 58px;
  width: auto;
  display: block;
  filter: none;
}
.welcome p {
  color: var(--text-light);
  margin-bottom: 32px;
  font-size: var(--font-size-md);
  line-height: 1.65;
  max-width: 680px;
  margin-left: auto;
  margin-right: auto;
}
.example-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 12px;
  text-align: left;
  width: 100%;
}
.example-label {
  font-size: 13px;
  letter-spacing: 0;
  font-weight: 600;
  color: var(--text-muted);
  margin-bottom: 14px;
  text-align: left;
  width: 100%;
}
.example-card {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  gap: 10px;
  height: 100%;
  background: rgba(255, 255, 255, 0.92);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  padding: 10px 36px 10px 12px;
  cursor: pointer;
  transition: all 0.25s ease;
  overflow: hidden;
}
.example-card:hover {
  background: rgba(232, 242, 255, 0.88);
  border-color: var(--primary-medium);
  transform: translateY(-2px);
}
.example-card .ex-icon {
  flex-shrink: 0;
  width: 30px;
  height: 30px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 7px;
  background: var(--primary-light);
  color: var(--primary);
  font-size: 16px;
  transition: background 0.25s ease;
}
.example-card:hover .ex-icon {
  background: var(--primary);
  color: #fff;
}
.example-card .ex-text {
  flex: 1;
  font-size: var(--font-size-sm);
  color: var(--text);
  line-height: 1.4;
  text-align: left;
}
.example-card .ex-arrow {
  position: absolute;
  right: 14px;
  top: 50%;
  transform: translateY(-50%) translateX(4px);
  color: var(--primary);
  font-size: 16px;
  opacity: 0;
  transition: all 0.25s ease;
}
.example-card:hover .ex-arrow {
  opacity: 0.7;
  transform: translateY(-50%) translateX(0);
}

/* ── Messages ─────────────────────────────────────────── */
.message {
  max-width: var(--agent-content-width);
  width: 100%;
  margin: 0 auto;
  display: flex;
  align-items: flex-start;
  gap: 12px;
  animation: agentFadeIn 0.3s ease;
}
@keyframes agentFadeIn {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: translateY(0); }
}
.message.user { flex-direction: row-reverse; }
.message.assistant .assistant-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-self: stretch;
}

.msg-content {
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
  padding: 14px 18px;
  flex: 1;
  min-width: 0;
  word-wrap: break-word;
  font-size: var(--font-size-md);
  line-height: 1.6;
  align-self: stretch;
}
.message.user .msg-content {
  background: linear-gradient(135deg, #e8f2ff 0%, var(--primary-light) 100%);
  border-color: var(--primary-medium);
  box-shadow: 0 2px 8px rgba(14, 116, 211, 0.08);
}
.msg-content p { margin-bottom: 8px; }
.msg-content p:last-child { margin-bottom: 0; }
.msg-content strong { font-weight: 700; }
.msg-content em { font-style: italic; }
.msg-content code {
  background: var(--primary-light);
  padding: 2px 6px;
  border-radius: 3px;
  font-size: var(--font-size-xs);
  font-family: var(--font-mono);
}
.msg-content pre {
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--card-radius);
  padding: 12px;
  overflow-x: auto;
  margin: 8px 0;
}
.msg-content pre code { background: none; padding: 0; }
.msg-content table {
  width: 100%;
  border-collapse: collapse;
  margin: 10px 0;
  font-size: var(--font-size-xs);
}
.msg-content th, .msg-content td {
  border: 1px solid var(--border);
  padding: 6px 10px;
  text-align: left;
}
.msg-content th { background: var(--primary-light); font-weight: 600; }
.msg-content tr:nth-child(even) { background: var(--bg); }
.msg-content ul, .msg-content ol { margin: 8px 0 8px 20px; }
.msg-content li { margin-bottom: 4px; }
.msg-content a { color: var(--primary); }
.msg-content a:hover { color: var(--primary-dark); }
.msg-content h1 { font-size: 1.3em; font-weight: 700; margin: 14px 0 8px; color: var(--primary); }
.msg-content h2 { font-size: 1.15em; font-weight: 700; margin: 12px 0 6px; color: var(--primary); }
.msg-content h3 { font-size: 1.05em; font-weight: 600; margin: 10px 0 6px; color: var(--primary); }
.msg-content h4 { font-size: 1em; font-weight: 600; margin: 10px 0 6px; color: var(--primary); }
.msg-content h5 { font-size: 0.95em; font-weight: 600; margin: 8px 0 4px; color: var(--primary-dark); }
.msg-content h6 { font-size: 0.9em; font-weight: 600; margin: 8px 0 4px; color: var(--text-light); }
.msg-content blockquote {
  margin: 10px 0;
  padding: 10px 14px;
  border-left: 3px solid var(--primary-medium);
  background: rgba(232, 242, 255, 0.55);
  border-radius: 0 8px 8px 0;
  color: var(--text);
}
.msg-content blockquote p { margin: 0 0 6px; }
.msg-content blockquote p:last-child { margin-bottom: 0; }
/* Numbered logic-line section titles sometimes rendered as bold paragraphs */
.message.assistant .msg-content > p > strong:only-child {
  color: var(--primary);
}
.msg-content hr { border: none; border-top: 1px solid var(--border); margin: 12px 0; }
.msg-actions {
  display: flex;
  gap: 6px;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid var(--border);
}
.msg-action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-white);
  color: var(--text-muted);
  cursor: pointer;
  font-size: 16px;
  transition: all 0.2s;
}
.msg-action-btn:hover {
  color: var(--primary);
  border-color: var(--primary-medium);
  background: var(--primary-light);
}
.msg-action-btn.copied { color: var(--primary-alt); border-color: var(--primary-alt); }

/* ── Collapsible headers (plan + tools) ───────────────── */
.thinking-tools,
.plan-panel {
  display: flex;
  flex-direction: column;
  gap: 6px;
  width: 100%;
  margin: 0;
  padding: 0;
  background: none;
  border: none;
  box-shadow: none;
  animation: agentFadeIn 0.3s ease;
}
.thinking-tools-summary,
.plan-panel-header {
  display: none;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 500;
  color: var(--text-muted);
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.85);
  cursor: pointer;
  user-select: none;
  transition: background 0.2s;
  margin: 0;
}
.thinking-tools.has-tools .thinking-tools-summary,
.plan-panel .plan-panel-header { display: flex; }
.thinking-tools-summary:hover,
.plan-panel-header:hover { background: var(--primary-light); }
.thinking-tools-summary > i:first-child,
.plan-panel-header > i:first-child { color: var(--primary); }
.thinking-tools-summary .toggle-arrow,
.plan-panel-header .toggle-arrow {
  margin-left: auto;
  color: var(--text-muted);
  font-weight: 400;
  transition: transform 0.2s ease;
}
.thinking-tools:not(.collapsed) .thinking-tools-summary .toggle-arrow,
.plan-panel:not(.collapsed) .plan-panel-header .toggle-arrow {
  transform: rotate(180deg);
}
.thinking-tools.collapsed .tool-indicator { display: none; }
.plan-panel.collapsed .plan-panel-details { display: none; }

.plan-panel-details {
  padding: 14px 18px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 2px 10px rgba(14, 116, 211, 0.08);
}
.plan-panel-summary {
  font-size: 12px;
  color: var(--text-light);
  margin-bottom: 12px;
  line-height: 1.5;
}

/* ── Tool call indicators ─────────────────────────────── */
.tool-indicator {
  width: 100%;
  margin: 0;
  padding: 10px 14px;
  background: rgba(255, 255, 255, 0.9);
  border: 1px solid var(--border);
  border-radius: 10px;
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  display: flex;
  align-items: center;
  gap: 8px;
  animation: agentFadeIn 0.2s ease;
  box-shadow: 0 1px 4px rgba(0, 0, 0, 0.03);
}
.tool-indicator .tool-icon { flex-shrink: 0; color: var(--primary); font-size: 14px; }
.tool-indicator-body {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 8px;
  overflow: hidden;
}
.tool-indicator .tool-name {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--text);
}
.tool-indicator .tool-args {
  flex-shrink: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tool-indicator .tool-summary {
  flex: 1;
  min-width: 0;
  font-size: 12px;
  color: var(--text-light);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tool-indicator .tool-status {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
}
.tool-indicator.success .tool-status { color: var(--primary-alt); }
.tool-indicator.error .tool-status { color: #c0392b; }

/* ── msg-content loading / streaming ──────────────────── */
.msg-content.is-loading,
.msg-content.is-streaming {
  min-height: 36px;
}
.msg-content-loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 0;
  color: var(--text-muted);
  font-size: 13px;
}
.msg-content-loading .loading-label {
  font-weight: 500;
  color: var(--text-light);
}
.streaming-cursor {
  display: inline-block;
  width: 2px;
  height: 1em;
  margin-left: 2px;
  vertical-align: text-bottom;
  background: var(--primary);
  border-radius: 1px;
  animation: agentCursorBlink 0.9s step-end infinite;
}
@keyframes agentCursorBlink {
  0%, 100% { opacity: 1; }
  50% { opacity: 0; }
}

/* ── Research plan steps ──────────────────────────────── */
.plan-steps { display: flex; flex-direction: column; gap: 8px; }
.plan-step {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  font-size: 12px;
  transition: all 0.2s ease;
}
.plan-step.running {
  border-color: var(--primary-medium);
  background: rgba(232, 242, 255, 0.5);
}
.plan-step.completed { opacity: 0.85; }
.plan-step.skipped { opacity: 0.5; }
.plan-step-num {
  flex-shrink: 0;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--primary-light);
  color: var(--primary);
  font-weight: 700;
  font-size: 11px;
  display: flex;
  align-items: center;
  justify-content: center;
}
.plan-step.running .plan-step-num {
  background: var(--primary);
  color: #fff;
}
.plan-step.completed .plan-step-num {
  background: var(--primary-alt);
  color: #fff;
}
.plan-step-body { flex: 1; min-width: 0; }
.plan-step-title { font-weight: 600; color: var(--text); margin-bottom: 2px; }
.plan-step-meta { color: var(--text-muted); font-size: 11px; }
.plan-step-desc { color: var(--text-light); margin-top: 3px; line-height: 1.4; }

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
  animation: agentBounce 1.4s ease-in-out infinite;
}
.typing-dots span:nth-child(2) { animation-delay: 0.2s; }
.typing-dots span:nth-child(3) { animation-delay: 0.4s; }
@keyframes agentBounce {
  0%, 60%, 100% { transform: translateY(0); opacity: 0.4; }
  30% { transform: translateY(-6px); opacity: 1; }
}

/* ── Input ────────────────────────────────────────────── */
.input-wrapper {
  flex-shrink: 0;
  max-width: var(--agent-content-width);
  width: calc(100% - 64px);
  margin: 0 auto 18px;
  display: flex;
  gap: 10px;
  align-items: flex-end;
  background: var(--bg-white);
  border: 1px solid var(--border);
  border-radius: 28px;
  padding: 6px 8px 6px 20px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.input-wrapper:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(14, 116, 211, 0.12);
}
.input-field {
  flex: 1;
  border: none;
  border-radius: 0;
  padding: 10px 0;
  font-size: var(--font-size-md);
  line-height: 22px;
  font-family: inherit;
  resize: none;
  overflow-y: hidden;
  max-height: 120px;
  min-height: 42px;
  background: transparent;
  color: var(--text);
}
.input-field:focus { outline: none; }
.input-field::placeholder { color: var(--text-muted); }
.send-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  padding: 0;
  background: var(--primary);
  color: #fff;
  border: none;
  border-radius: 50%;
  cursor: pointer;
  transition: background 0.2s ease;
}
.send-btn i {
  font-size: 20px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.send-btn:hover { background: var(--primary-alt); }
.send-btn:active { transform: scale(0.95); }
.send-btn:disabled {
  background: var(--border-dark);
  color: #fff;
  cursor: not-allowed;
  transform: none;
}

@media (max-width: 768px) {
  .agent-shell { flex-direction: column; }
  .agent-sidebar {
    width: 100%;
    max-height: 140px;
    border-right: none;
    border-bottom: 1px solid var(--border);
  }
  .sidebar-history { display: flex; gap: 6px; overflow-x: auto; padding: 0 8px 10px; }
  .sidebar-item { flex-shrink: 0; max-width: 160px; margin-bottom: 0; }
  .chat-area { padding: 16px; }
  .input-wrapper { width: calc(100% - 32px); margin-bottom: 12px; }
  .example-grid { grid-template-columns: 1fr; }
  .message { max-width: 100%; }
  .welcome-header {
    flex-direction: column;
    gap: 10px;
    padding: 18px 22px;
    border-radius: 20px;
  }
  .welcome-logo { height: 56px; }
  .welcome-badge {
    margin-left: 0;
    padding: 0;
    border-left: none;
    border-top: 1px solid rgba(179, 204, 245, 0.9);
    padding-top: 10px;
    font-size: 15px;
  }
}
</style>
</head>
<body class="agent-page">
<div id="preloader">
  <div class="preloader-inner">
    <div class="preloader-spinner"></div>
    <span class="preloader-text">Loading...</span>
  </div>
</div>

<div id="site-header"></div>

<div class="agent-shell">
  <aside class="agent-sidebar" id="agentSidebar">
    <button class="sidebar-new-btn" type="button" onclick="startNewConversation()">
      <i class="ri-add-line"></i> New chat
    </button>
    <div class="sidebar-history-label">History</div>
    <div class="sidebar-history" id="sidebarHistory"></div>
  </aside>

  <div class="agent-main">
  <div class="chat-area" id="chatArea">
    <div class="welcome" id="welcome">
      <div class="welcome-header">
        <img class="welcome-logo" src="assets/img/logo.png" alt="qPTM">
        <div class="welcome-badge"><i class="ri-sparkling-2-line"></i> AI-Powered PTM Explorer</div>
      </div>
      <p>Your intelligent guide for exploring PTM sites along a four-stage logic line — <strong>WHO</strong> regulates it, <strong>WHEN</strong> it changes, <strong>WHERE</strong> it happens, and <strong>WHY</strong> it matters.</p>
      <div class="example-label">Try an example</div>
      <div class="example-grid">
        <div class="example-card" onclick="sendExample('Who regulates AKT1 S473 phosphorylation?')">
          <div class="ex-icon"><i class="ri-node-tree"></i></div>
          <div class="ex-text">Who regulates AKT1 S473 phosphorylation?</div>
          <i class="ri-arrow-right-s-line ex-arrow"></i>
        </div>
        <div class="example-card" onclick="sendExample('When does TP53 S15 phosphorylation change?')">
          <div class="ex-icon"><i class="ri-timer-flash-line"></i></div>
          <div class="ex-text">When does TP53 S15 phosphorylation change?</div>
          <i class="ri-arrow-right-s-line ex-arrow"></i>
        </div>
        <div class="example-card" onclick="sendExample('Where does EGFR Y1173 phosphorylation happen?')">
          <div class="ex-icon"><i class="ri-map-pin-line"></i></div>
          <div class="ex-text">Where does EGFR Y1173 phosphorylation happen?</div>
          <i class="ri-arrow-right-s-line ex-arrow"></i>
        </div>
        <div class="example-card" onclick="sendExample('Why does TP53 S15 phosphorylation matter?')">
          <div class="ex-icon"><i class="ri-lightbulb-line"></i></div>
          <div class="ex-text">Why does TP53 S15 phosphorylation matter?</div>
          <i class="ri-arrow-right-s-line ex-arrow"></i>
        </div>
      </div>
    </div>
  </div>

  <div class="input-wrapper">
    <textarea class="input-field" id="inputField"
      placeholder="Ask about a PTM site — WHO / WHEN / WHERE / WHY (e.g. RFTN1 S467)..."
      rows="1" onkeydown="handleKey(event)"></textarea>
    <button class="send-btn" id="sendBtn" onclick="sendMessage()">
      <i class="ri-send-plane-fill"></i>
    </button>
  </div>
  </div><!-- /.agent-main -->
</div>

<script>
const CHAT_URL = '<?php echo htmlspecialchars($BACKEND_URL, ENT_QUOTES); ?>';
const CONVERSATIONS_URL = CHAT_URL.replace(/\/chat\/?$/, '/conversations');
const CONV_STORAGE_KEY = 'qptm_agent_conversation_id';

let sessionId = null;
let conversationId = localStorage.getItem(CONV_STORAGE_KEY) || null;
let conversationList = [];
let isStreaming = false;
let chatHistory = [];

const chatArea = document.getElementById('chatArea');
const welcome = document.getElementById('welcome');
const inputField = document.getElementById('inputField');
const sendBtn = document.getElementById('sendBtn');
const sidebarHistory = document.getElementById('sidebarHistory');

function persistConversationId(id) {
  conversationId = id || null;
  if (id) localStorage.setItem(CONV_STORAGE_KEY, id);
  else localStorage.removeItem(CONV_STORAGE_KEY);
}

async function loadConversationList() {
  try {
    const res = await fetch(CONVERSATIONS_URL);
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
    item.textContent = conv.title || 'Untitled';
    item.addEventListener('click', () => loadConversation(conv.id));
    sidebarHistory.appendChild(item);
  });
}

function clearChatArea() {
  chatArea.querySelectorAll('.message').forEach((el) => el.remove());
  if (welcome) welcome.style.display = '';
  chatHistory = [];
  currentThinkingTools = null;
  currentPlanPanel = null;
}

function startNewConversation() {
  if (isStreaming) return;
  persistConversationId(null);
  sessionId = null;
  clearChatArea();
  renderSidebar();
  inputField.focus();
}

async function loadConversation(id, { force = false } = {}) {
  if (isStreaming) return;
  if (!force && id === conversationId && chatArea.querySelector('.message')) return;
  try {
    const res = await fetch(`${CONVERSATIONS_URL}/${encodeURIComponent(id)}`);
    if (!res.ok) {
      if (res.status === 403 || res.status === 404) persistConversationId(null);
      return;
    }
    const data = await res.json();
    persistConversationId(data.id);
    sessionId = null;
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
    renderSidebar();
    chatArea.scrollTop = chatArea.scrollHeight;
  } catch (err) {
    console.warn('Failed to load conversation:', err);
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
  downloadBtn.innerHTML = '<i class="ri-download-line"></i>';
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

    const logo = await loadImageDataUrl('assets/img/logo.png');
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
  await loadConversationList();
  if (conversationId && conversationList.some((c) => c.id === conversationId)) {
    await loadConversation(conversationId, { force: true });
  } else if (conversationId) {
    persistConversationId(null);
  }
});

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
    sendMessage();
  }
}

function sendExample(text) {
  inputField.value = text;
  sendMessage();
}

function applyInlineMarkdown(text) {
  let s = text;
  s = s.replace(/`([^`]+)`/g, '<code>$1</code>');
  s = s.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
  s = s.replace(/\*(.+?)\*/g, '<em>$1</em>');
  s = s.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
  return s;
}

function renderMarkdown(text) {
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

  function closeList() {
    if (inList) { result.push(`</${listType}>`); inList = false; }
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
      result.push(`<h${level}>${applyInlineMarkdown(heading[2])}</h${level}>`);
      i++;
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
    const olMatch = trimmed.match(/^\d+\. (.+)$/);
    if (ulMatch || olMatch) {
      const newType = ulMatch ? 'ul' : 'ol';
      if (!inList) { result.push(`<${newType}>`); inList = true; listType = newType; }
      else if (listType !== newType) { result.push(`</${listType}><${newType}>`); listType = newType; }
      result.push(`<li>${applyInlineMarkdown(ulMatch ? ulMatch[1] : olMatch[1])}</li>`);
      i++;
      continue;
    }

    closeList();
    if (trimmed === '') { i++; continue; }
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
    <div class="plan-panel-header"><i class="ri-route-line"></i> Research Plan<i class="ri-arrow-down-s-line toggle-arrow"></i></div>
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
    const ind = document.createElement('div');
    ind.className = 'tool-indicator ' + (success ? 'success' : 'error');
    ind.innerHTML = `
      <i class="ri-tools-line tool-icon"></i>
      <div class="tool-indicator-body">
        <span class="tool-name">${escapeHtml(t.tool_name || '')}</span>
        <span class="tool-args">${escapeHtml(formatArgs(t.arguments || {}))}</span>
        <span class="tool-summary">${escapeHtml((t.summary || '').substring(0, 120))}</span>
      </div>
      <span class="tool-status">${success ? '✓ Done' : '✗ Error'}</span>
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

  if (meta?.plan) {
    body.appendChild(createPlanPanelEl(meta.plan, true));
  }
  if (meta?.tools?.length) {
    body.appendChild(createThinkingToolsEl(meta.tools, true));
  }

  const contentDiv = document.createElement('div');
  contentDiv.className = 'msg-content';
  contentDiv.innerHTML = renderMarkdown(content || '');
  body.appendChild(contentDiv);
  msg.appendChild(body);
  chatArea.appendChild(msg);
  attachMessageActions(contentDiv, content || '');
  return contentDiv;
}

let currentThinkingTools = null;
let currentPlanPanel = null;

function beginAssistantTurn() {
  if (welcome) welcome.style.display = 'none';

  const msg = document.createElement('div');
  msg.className = 'message assistant';

  const body = document.createElement('div');
  body.className = 'assistant-body';

  const thinkingTools = document.createElement('div');
  thinkingTools.className = 'thinking-tools';
  const summary = document.createElement('div');
  summary.className = 'thinking-tools-summary';
  summary.innerHTML = '<i class="ri-database-2-line"></i><span class="thinking-summary-text"></span><i class="ri-arrow-down-s-line toggle-arrow"></i>';
  summary.addEventListener('click', () => thinkingTools.classList.toggle('collapsed'));
  thinkingTools.appendChild(summary);

  const contentDiv = document.createElement('div');
  contentDiv.className = 'msg-content is-loading';

  body.appendChild(thinkingTools);
  body.appendChild(contentDiv);
  msg.appendChild(body);
  chatArea.appendChild(msg);

  currentThinkingTools = thinkingTools;
  currentPlanPanel = null;
  showContentLoading(contentDiv, 'Planning...');
  chatArea.scrollTop = chatArea.scrollHeight;
  return contentDiv;
}

function refreshThinkingToolsHeader() {
  if (!currentThinkingTools) return;
  const count = currentThinkingTools.querySelectorAll('.tool-indicator').length;
  if (count > 0) currentThinkingTools.classList.add('has-tools');
  const textEl = currentThinkingTools.querySelector('.thinking-summary-text');
  if (textEl && count > 0) {
    textEl.textContent = `Queried ${count} data source${count > 1 ? 's' : ''}`;
  }
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
  if (!currentThinkingTools) return;
  refreshThinkingToolsHeader();
  const count = currentThinkingTools.querySelectorAll('.tool-indicator').length;
  if (count === 0) return;
  currentThinkingTools.classList.add('collapsed');
}

function collapsePlanPanel() {
  if (!currentPlanPanel) return;
  currentPlanPanel.classList.add('collapsed');
}

function addToolIndicator(toolName, args) {
  if (!currentThinkingTools) return null;
  const ind = document.createElement('div');
  ind.className = 'tool-indicator';
  ind.innerHTML = `
    <i class="ri-tools-line tool-icon"></i>
    <div class="tool-indicator-body">
      <span class="tool-name">${escapeHtml(toolName)}</span>
      <span class="tool-args">${escapeHtml(formatArgs(args))}</span>
      <span class="tool-summary"></span>
    </div>
    <span class="tool-status">running...</span>
  `;
  currentThinkingTools.appendChild(ind);
  currentThinkingTools.classList.remove('collapsed');
  refreshThinkingToolsHeader();
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
  const status = ind.querySelector('.tool-status');
  status.textContent = success ? '✓ Done' : '✗ Error';
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

async function sendMessage() {
  const text = inputField.value.trim();
  if (!text || isStreaming) return;

  isStreaming = true;
  sendBtn.disabled = true;
  inputField.value = '';
  resizeInputField();

  addMessage('user', text);
  chatHistory.push({ role: 'user', content: text });

  const assistantContent = beginAssistantTurn();
  let fullText = '';

  try {
    const response = await fetch(CHAT_URL, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        message: text,
        session_id: sessionId,
        conversation_id: conversationId,
        history: chatHistory.slice(-10),
      }),
    });

    const newSessionId = response.headers.get('X-Session-Id');
    if (newSessionId) sessionId = newSessionId;

    const newConvId = response.headers.get('X-Conversation-Id');
    if (newConvId) persistConversationId(newConvId);

    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }

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
            fullText += data.content;
            renderStreamingContent(assistantContent, fullText);
            chatArea.scrollTop = chatArea.scrollHeight;
          } else if (currentEvent === 'plan_created') {
            showContentLoading(assistantContent, 'Querying databases...');
            addPlanPanel(data);
          } else if (currentEvent === 'step_started') {
            updatePlanStep(data);
          } else if (currentEvent === 'step_completed') {
            updatePlanStep(data);
          } else if (currentEvent === 'tool_call') {
            showContentLoading(assistantContent, 'Querying databases...');
            addToolIndicator(data.tool_name, data.arguments);
          } else if (currentEvent === 'tool_result') {
            const indicators = currentThinkingTools?.querySelectorAll('.tool-indicator') || [];
            const lastInd = indicators[indicators.length - 1];
            if (lastInd) updateToolIndicator(lastInd, data.success, data.summary);
            showContentLoading(assistantContent, 'Generating answer...');
          } else if (currentEvent === 'done') {
            collapseThinkingTools();
            collapsePlanPanel();
          } else if (currentEvent === 'error') {
            hideContentLoading(assistantContent);
            hideStreamingCursor(assistantContent);
            assistantContent.innerHTML = `<p style="color:#c0392b;">${data.message}</p>`;
            collapsePlanPanel();
          }

          currentEvent = null;
        }
      }
    }

    hideContentLoading(assistantContent);
    hideStreamingCursor(assistantContent);
    if (fullText) {
      assistantContent.innerHTML = renderMarkdown(fullText);
      chatHistory.push({ role: 'assistant', content: fullText });
      attachMessageActions(assistantContent, fullText);
    } else if (!assistantContent.querySelector('p[style*="c0392b"]')) {
      assistantContent.innerHTML = '<p style="color:var(--text-muted);">No response received.</p>';
    }
    collapseThinkingTools();
    collapsePlanPanel();
    await loadConversationList();

  } catch (err) {
    hideContentLoading(assistantContent);
    hideStreamingCursor(assistantContent);
    assistantContent.innerHTML = `<p style="color:#c0392b;">Connection error: ${err.message}</p>
      <p style="font-size:13px;color:var(--text-muted);">Make sure the qPTM Agent backend is running at ${CHAT_URL}</p>`;
    collapsePlanPanel();
  } finally {
    isStreaming = false;
    sendBtn.disabled = false;
    inputField.focus();
  }
}
</script>
</body>
</html>

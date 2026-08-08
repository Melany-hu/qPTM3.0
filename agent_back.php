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
  --welcome-content-width: 1320px;
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
  max-width: var(--welcome-content-width);
  width: 100%;
  margin: auto;
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: 40px 12px 16px;
}
.welcome-intro {
  width: 100%;
  transform: translateY(-28px);
}
@keyframes welcomeHeaderIn {
  from {
    opacity: 0;
    transform: translateY(14px) scale(0.96);
  }
  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}
@keyframes welcomeFadeUp {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
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
  animation: welcomeBadgeIn 0.55s ease 0.22s backwards;
}
@keyframes welcomeBadgeIn {
  from {
    opacity: 0;
    transform: translateX(10px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
.welcome-badge i {
  font-size: 18px;
  color: var(--primary);
  animation: welcomeSparkle 2.8s ease-in-out 0.65s infinite;
}
@keyframes welcomeSparkle {
  0%, 100% { opacity: 1; transform: scale(1); }
  50% { opacity: 0.72; transform: scale(1.08); }
}
.welcome-header {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 20px;
  padding: 12px 28px 12px 18px;
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.95) 0%, rgba(232, 242, 255, 0.88) 100%);
  border: 1px solid var(--border);
  border-radius: 48px;
  box-shadow: 0 8px 24px rgba(14, 116, 211, 0.14);
  backdrop-filter: blur(8px);
  -webkit-backdrop-filter: blur(8px);
  animation: welcomeHeaderIn 0.65s cubic-bezier(0.22, 1, 0.36, 1) backwards;
}
.welcome-logo {
  height: 58px;
  width: auto;
  display: block;
  filter: none;
  animation: welcomeLogoIn 0.7s cubic-bezier(0.22, 1, 0.36, 1) 0.08s backwards;
}
@keyframes welcomeLogoIn {
  from {
    opacity: 0;
    transform: translateX(-8px);
  }
  to {
    opacity: 1;
    transform: translateX(0);
  }
}
.welcome p {
  color: var(--text-light);
  margin-bottom: 22px;
  font-size: var(--font-size-md);
  line-height: 1.65;
  max-width: var(--agent-content-width);
  width: 100%;
  margin-left: auto;
  margin-right: auto;
  animation: welcomeFadeUp 0.55s ease 0.18s backwards;
}
.example-chips {
  width: 100%;
  max-width: var(--welcome-content-width);
  display: flex;
  flex-direction: column;
  gap: 8px;
  align-items: center;
}
.example-row {
  display: flex;
  flex-wrap: nowrap;
  justify-content: center;
  align-items: center;
  gap: 8px;
  width: 100%;
}
.example-chip {
  display: inline-flex;
  align-items: center;
  flex-shrink: 0;
  padding: 10px 18px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.94);
  color: #5E676F;
  font-size: 13px;
  line-height: 1.35;
  white-space: nowrap;
  cursor: pointer;
  box-shadow:
    0 2px 8px rgba(14, 116, 211, 0.06),
    0 1px 2px rgba(15, 23, 42, 0.04);
  transition:
    background 0.22s ease,
    color 0.22s ease,
    border-color 0.22s ease,
    box-shadow 0.22s ease,
    transform 0.22s ease;
  font-family: inherit;
  text-align: left;
  animation: exampleChipIn 0.5s ease backwards;
}
.example-row:nth-child(1) .example-chip:nth-child(1) { animation-delay: 0.04s; }
.example-row:nth-child(1) .example-chip:nth-child(2) { animation-delay: 0.1s; }
.example-row:nth-child(1) .example-chip:nth-child(3) { animation-delay: 0.16s; }
.example-row:nth-child(2) .example-chip:nth-child(1) { animation-delay: 0.12s; }
.example-row:nth-child(2) .example-chip:nth-child(2) { animation-delay: 0.18s; }
.example-row:nth-child(2) .example-chip:nth-child(3) { animation-delay: 0.24s; }
.example-row:nth-child(3) .example-chip:nth-child(1) { animation-delay: 0.2s; }
.example-row:nth-child(3) .example-chip:nth-child(2) { animation-delay: 0.26s; }
.example-row:nth-child(3) .example-chip:nth-child(3) { animation-delay: 0.32s; }
@keyframes exampleChipIn {
  from {
    opacity: 0;
    transform: translateY(10px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
.example-chip:hover {
  background: linear-gradient(135deg, rgba(255, 255, 255, 0.98) 0%, var(--primary-light) 100%);
  border-color: var(--primary-medium);
  color: var(--primary-dark);
  box-shadow: 0 8px 22px rgba(14, 116, 211, 0.16);
  transform: translateY(-2px);
}
.example-chip:focus-visible {
  outline: none;
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(14, 116, 211, 0.18);
}
.example-chip:active {
  transform: translateY(0);
  box-shadow: 0 2px 8px rgba(14, 116, 211, 0.1);
}

@media (prefers-reduced-motion: reduce) {
  .welcome-intro {
    transform: none;
  }
  .welcome-header,
  .welcome-logo,
  .welcome-badge,
  .welcome p,
  .example-chip,
  .welcome-badge i {
    animation: none;
  }
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
.message.user {
  flex-direction: row-reverse;
  justify-content: flex-start;
}
.message.user .msg-content {
  flex: 0 1 auto;
  width: fit-content;
  max-width: min(72%, 520px);
  margin-left: auto;
  align-self: flex-end;
  font-size: var(--font-size-md);
  line-height: 1.55;
}
.message.assistant .msg-content {
  font-size: var(--font-size-md);
  line-height: 1.6;
  color: var(--text);
}
.message.assistant .assistant-body {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
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
  font-size: var(--font-size-xs);
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
  padding: 14px 16px;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--border);
  border-radius: 12px;
  box-shadow: 0 2px 10px rgba(14, 116, 211, 0.08);
  font-size: var(--font-size-xs);
  color: var(--text);
  line-height: 1.5;
}
.plan-panel-summary {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
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
  padding: 9px 11px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg);
  font-size: var(--font-size-xs);
  line-height: 1.45;
  transition: all 0.2s ease;
}
.plan-step.running {
  border-color: var(--primary-medium);
  background: rgba(232, 242, 255, 0.5);
}
.plan-step.completed { opacity: 0.85; }
.plan-step.skipped { opacity: 0.5; }
.plan-step.failed { opacity: 0.75; border-color: #f5c6cb; }
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
.plan-step-title {
  font-size: var(--font-size-sm);
  font-weight: 600;
  color: var(--text);
  margin-bottom: 2px;
  line-height: 1.35;
}
.plan-step-meta {
  color: var(--text-muted);
  font-size: var(--font-size-xs);
  line-height: 1.4;
}
.plan-step-desc {
  color: var(--text-light);
  margin-top: 3px;
  font-size: var(--font-size-xs);
  line-height: 1.45;
}

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
  margin: 0 auto 30px;
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0;
  background: var(--bg-white);
  border: 1px solid var(--border);
  border-radius: 22px;
  padding: 10px 12px 8px;
  transition: border-color 0.2s, box-shadow 0.2s;
}
.input-wrapper:focus-within {
  border-color: var(--primary);
  box-shadow: 0 0 0 3px rgba(14, 116, 211, 0.12);
}
.input-field {
  display: block;
  width: 100%;
  box-sizing: border-box;
  border: none;
  border-radius: 0;
  padding: 2px 4px 8px;
  font-size: var(--font-size-md);
  line-height: 22px;
  font-family: inherit;
  resize: none;
  overflow-y: auto;
  max-height: 120px;
  min-height: 42px;
  background: transparent;
  color: var(--text);
}
.input-field:focus { outline: none; }
.input-field::placeholder { color: var(--text-muted); }
.input-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  gap: 8px;
  padding-top: 2px;
}
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

.input-pending-files {
  display: none;
  flex-wrap: wrap;
  gap: 8px;
  width: calc(100% - 64px);
  max-width: var(--agent-content-width);
  margin: 0 auto 16px;
  padding: 0 4px;
  box-sizing: border-box;
}
.input-pending-files.has-files {
  display: flex;
}
.pending-file-chip {
  display: flex;
  flex-direction: column;
  gap: 7px;
  min-width: 168px;
  max-width: 240px;
  padding: 8px 10px;
  font-size: var(--font-size-xs);
  color: var(--text);
  background: rgba(255, 255, 255, 0.98);
  border: 1px solid var(--border);
  border-radius: 10px;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.04);
}
.pending-file-chip-row {
  display: flex;
  align-items: center;
  gap: 7px;
  min-width: 0;
}
.pending-file-chip-row > i:first-child {
  font-size: 18px;
  line-height: 1;
  flex-shrink: 0;
}
.pending-file-chip.file-pdf .pending-file-chip-row > i:first-child { color: #e53935; }
.pending-file-chip.file-excel .pending-file-chip-row > i:first-child { color: #2e7d32; }
.pending-file-chip.file-table .pending-file-chip-row > i:first-child { color: #1565c0; }
.pending-file-chip.file-zip .pending-file-chip-row > i:first-child { color: #f9a825; }
.pending-file-chip.file-xml .pending-file-chip-row > i:first-child { color: #6a1b9a; }
.pending-file-meta {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 1px;
}
.pending-file-name {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
  line-height: 1.3;
}
.pending-file-sub {
  font-size: 11px;
  color: var(--text-muted);
  line-height: 1.2;
}
.pending-file-chip button {
  border: none;
  background: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0;
  font-size: 14px;
  line-height: 1;
  flex-shrink: 0;
}
.pending-file-chip.is-uploading button {
  display: none;
}
.pending-file-progress {
  display: none;
  height: 3px;
  border-radius: 999px;
  background: rgba(100, 116, 139, 0.18);
  overflow: hidden;
}
.pending-file-chip.is-uploading .pending-file-progress,
.pending-file-chip.is-done .pending-file-progress,
.pending-file-chip.is-error .pending-file-progress {
  display: block;
}
.pending-file-progress > span {
  display: block;
  height: 100%;
  width: 0%;
  border-radius: inherit;
  background: var(--primary);
  transition: width 0.18s ease-out;
}
.pending-file-chip.is-uploading .pending-file-progress > span {
  background-size: 200% 100%;
  animation: pending-progress-shine 1.2s linear infinite;
}
.pending-file-chip.is-done .pending-file-progress > span {
  background: #64748b;
  animation: none;
}
.pending-file-chip.is-error .pending-file-progress > span {
  background: #94a3b8;
  animation: none;
  width: 100% !important;
}
@keyframes pending-progress-shine {
  0% { filter: brightness(1); }
  50% { filter: brightness(1.15); }
  100% { filter: brightness(1); }
}
.msg-file-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
  justify-content: flex-end;
}
.msg-file-chip {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 10px;
  font-size: var(--font-size-xs);
  color: var(--text);
  background: rgba(255, 255, 255, 0.75);
  border: 1px solid var(--border);
  border-radius: 8px;
}
.msg-file-chip > i {
  font-size: 16px;
  line-height: 1;
  flex-shrink: 0;
}
.msg-file-chip.file-pdf > i { color: #e53935; }
.msg-file-chip.file-excel > i { color: #2e7d32; }
.msg-file-chip.file-table > i { color: #1565c0; }
.msg-file-chip.file-zip > i { color: #f9a825; }
.msg-file-chip.file-xml > i { color: #6a1b9a; }
.attach-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 40px;
  height: 40px;
  padding: 0;
  border: 1px solid var(--border);
  border-radius: 50%;
  background: var(--bg-white);
  color: var(--text-muted);
  cursor: pointer;
  transition: all 0.2s;
}
.attach-btn i {
  font-size: 20px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}
.attach-btn:hover {
  color: var(--primary-alt);
  border-color: var(--primary-medium);
  background: var(--primary-light);
}
.collection-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.collection-btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 7px 12px;
  font-size: var(--font-size-xs);
  font-weight: 600;
  font-family: inherit;
  line-height: 1.35;
  border-radius: 8px;
  border: 1px solid var(--primary-medium);
  background: var(--primary-light);
  color: var(--primary);
  cursor: pointer;
  transition: all 0.2s;
}
.collection-btn:hover {
  background: var(--primary);
  color: #fff;
}
.collection-btn.secondary {
  background: var(--bg-white);
  color: var(--text);
  border-color: var(--border);
}
.collection-btn.secondary:hover {
  background: var(--primary-light);
  color: var(--primary);
}
.collection-btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}
.collection-downloads {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}
.collection-downloads a {
  font-size: var(--font-size-xs);
  font-weight: 600;
  line-height: 1.35;
  color: var(--primary);
  text-decoration: none;
  padding: 7px 12px;
  border: 1px solid var(--primary-medium);
  border-radius: 8px;
  background: rgba(255, 255, 255, 0.9);
}
.collection-downloads a:hover {
  background: var(--primary-light);
}
.collection-contribute {
  margin-top: 12px;
  padding: 12px 14px;
  border: 1px solid rgba(14, 116, 211, 0.25);
  border-radius: 12px;
  background: rgba(14, 116, 211, 0.06);
}
.collection-contribute-title {
  font-weight: 650;
  font-size: var(--font-size-sm);
  margin-bottom: 4px;
  color: var(--primary);
  line-height: 1.4;
}
.collection-contribute-body {
  font-size: var(--font-size-xs);
  color: var(--text-muted);
  line-height: 1.5;
  margin-bottom: 10px;
}
.collection-contribute-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
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
  .input-wrapper { width: calc(100% - 32px); margin-bottom: 30px; }
  .input-pending-files { width: calc(100% - 32px); margin-bottom: 14px; }
  .example-row {
    flex-wrap: wrap;
  }
  .example-chip {
    white-space: normal;
    text-align: center;
    border-radius: 14px;
    flex-shrink: 1;
    padding: 10px 14px;
  }
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
      <div class="welcome-intro">
        <div class="welcome-header">
          <img class="welcome-logo" src="assets/img/logo.png" alt="qPTM">
          <div class="welcome-badge"><i class="ri-chat-smile-2-line"></i> AI-Powered PTM Explorer</div>
        </div>
        <p>Ask any questions about post translational modification sites — quantitative data, experimental conditions, upregulated pathways, functional context, and disease links — with evidence drawn from qPTM and integrated public databases or tools.</p>
      </div>
      <div class="example-chips">
        <div class="example-row">
          <button type="button" class="example-chip" onclick="sendExample('Which kinases phosphorylate AKT1 S473?')">Which kinases phosphorylate AKT1 S473?</button>
          <button type="button" class="example-chip" onclick="sendExample('TP53 S15 phosphorylation after DNA damage')">TP53 S15 phosphorylation after DNA damage</button>
          <button type="button" class="example-chip" onclick="sendExample('Subcellular localization of EGFR Y1173 phosphorylation')">Subcellular localization of EGFR Y1173 phosphorylation</button>
        </div>
        <div class="example-row">
          <button type="button" class="example-chip" onclick="sendExample('STAT3 Y705 phosphorylation in cancer signaling')">STAT3 Y705 phosphorylation in cancer signaling</button>
          <button type="button" class="example-chip" onclick="sendExample('Collect quantitative PTM data from PMID 39732660')">Collect quantitative PTM data from PMID 39732660</button>
          <button type="button" class="example-chip" onclick="sendExample('Drug associations for STAT3 Y705 phosphorylation')">Drug associations for STAT3 Y705 phosphorylation</button>
        </div>
        <div class="example-row">
          <button type="button" class="example-chip" onclick="sendExample('Pathways linked to NF-κB p65 S536 phosphorylation')">Pathways linked to NF-κB p65 S536 phosphorylation</button>
          <button type="button" class="example-chip" onclick="sendExample('Predicted kinases for CDK1 T14 phosphorylation')">Predicted kinases for CDK1 T14 phosphorylation</button>
          <button type="button" class="example-chip" onclick="sendExample('Quantitative PTM changes in breast cancer')">Quantitative PTM changes in breast cancer</button>
        </div>
      </div>
    </div>
  </div>

  <div class="input-pending-files" id="pendingFiles"></div>
  <div class="input-wrapper">
    <input type="file" id="fileInput" multiple accept=".pdf,.xml,.zip,.xlsx,.xls,.csv,.tsv" style="display:none">
    <textarea class="input-field" id="inputField"
      placeholder="Ask about a PTM site, or upload a pdf file for literature collection..."
      rows="1" onkeydown="handleKey(event)"></textarea>
    <div class="input-actions">
      <button class="attach-btn" type="button" id="attachBtn" title="Attach PDF/XML or supplementary tables" onclick="document.getElementById('fileInput').click()">
        <i class="ri-attachment-2"></i>
      </button>
      <button class="send-btn" id="sendBtn" onclick="sendMessage()">
        <i class="ri-send-plane-fill"></i>
      </button>
    </div>
  </div>
  </div><!-- /.agent-main -->
</div>

<script>
const CHAT_URL = '<?php echo htmlspecialchars($BACKEND_URL, ENT_QUOTES); ?>';
const CONVERSATIONS_URL = CHAT_URL.replace(/\/chat\/?$/, '/conversations');
const CLASSIFY_URL = CHAT_URL.replace(/\/chat\/?$/, '/classify');
const COLLECTION_URL = CHAT_URL.replace(/\/chat\/?$/, '/collection');
const CONV_STORAGE_KEY = 'qptm_agent_conversation_id';

const COLLECTION_STAGE_DEFS = [
  { id: 'stage1', num: 1, title: 'Screen', desc: 'PTM relevance screening' },
  { id: 'stage2', num: 2, title: 'Full text', desc: 'Repository IDs + OA fulltext' },
  { id: 'stage3', num: 3, title: 'Metadata', desc: 'Literature metadata extraction' },
  { id: 'stage4', num: 4, title: 'Supplementary', desc: 'Scout / upload quantitative tables' },
  { id: 'stage5', num: 5, title: 'Quant table', desc: 'Parse to qratio schema' },
  { id: 'stage6', num: 6, title: 'MS URLs', desc: 'PRIDE / iProX / jPOST links' },
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

function uploadFormData(url, formData, { onProgress } = {}) {
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
    xhr.onabort = () => reject(new Error('Upload aborted'));
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
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message, upload_filenames: filenames }),
  });
  if (!res.ok) throw new Error(`Classify HTTP ${res.status}`);
  return res.json();
}

function createCollectionPanelEl(jobId) {
  const panel = document.createElement('div');
  panel.className = 'plan-panel collection-panel';
  panel.dataset.jobId = jobId;
  const stepsHtml = COLLECTION_STAGE_DEFS.map((s) => `
    <div class="plan-step" data-stage="${s.id}">
      <div class="plan-step-num">${s.num}</div>
      <div class="plan-step-body">
        <div class="plan-step-title">${escapeHtml(s.title)}</div>
        <div class="plan-step-meta">${escapeHtml(s.desc)}</div>
      </div>
    </div>
  `).join('');
  panel.innerHTML = `
    <div class="plan-panel-header"><i class="ri-database-2-line"></i> Data Collection Pipeline<i class="ri-arrow-down-s-line toggle-arrow"></i></div>
    <div class="plan-panel-details">
      <div class="plan-panel-summary collection-pmid"></div>
      <div class="plan-steps">${stepsHtml}</div>
      <div class="collection-actions"></div>
      <div class="collection-downloads"></div>
      <div class="collection-contribute" style="display:none;"></div>
    </div>
  `;
  panel.querySelector('.plan-panel-header').addEventListener('click', () => {
    panel.classList.toggle('collapsed');
  });
  return panel;
}

function updateCollectionPanel(panel, data) {
  if (!panel || !data) return;
  const pmidEl = panel.querySelector('.collection-pmid');
  if (pmidEl && data.pmid) {
    pmidEl.textContent = `PMID ${data.pmid}`;
  }
  const stages = data.stages || {};
  const current = data.current_stage || data.currentStage;
  COLLECTION_STAGE_DEFS.forEach((def) => {
    const el = panel.querySelector(`.plan-step[data-stage="${def.id}"]`);
    if (!el) return;
    el.classList.remove('running', 'completed', 'skipped', 'failed');
    const status = stages[def.id];
    if (status) el.classList.add(status);
    if (data.status === 'running' && current === def.id) {
      el.classList.add('running');
    }
  });

  const actions = panel.querySelector('.collection-actions');
  const downloads = panel.querySelector('.collection-downloads');
  const contribute = panel.querySelector('.collection-contribute');
  if (!actions || !downloads) return;
  actions.innerHTML = '';
  downloads.innerHTML = '';
  if (contribute) {
    contribute.style.display = 'none';
    contribute.innerHTML = '';
  }

  const jobId = panel.dataset.jobId;
  const status = data.status;

  if (status === 'awaiting_continue') {
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'collection-btn';
    btn.innerHTML = '<i class="ri-play-line"></i> Continue';
    btn.addEventListener('click', () => resumeCollectionJob(jobId, panel));
    actions.appendChild(btn);
  }

  if (status === 'awaiting_upload') {
    const kind = data.awaiting_upload || data.awaitingUpload;
    const label = kind === 'fulltext' ? 'Upload PDF/XML' : 'Upload supplementary tables';
    const accept = kind === 'fulltext' ? '.pdf,.xml' : '.zip,.xlsx,.xls,.csv,.tsv';
    const uploadBtn = document.createElement('button');
    uploadBtn.type = 'button';
    uploadBtn.className = 'collection-btn secondary';
    uploadBtn.innerHTML = `<i class="ri-upload-2-line"></i> ${label}`;
    uploadBtn.addEventListener('click', () => {
      const input = document.createElement('input');
      input.type = 'file';
      input.accept = accept;
      input.addEventListener('change', async () => {
        const file = input.files && input.files[0];
        if (!file) return;
        await uploadCollectionFile(jobId, kind, file, panel);
      });
      input.click();
    });
    actions.appendChild(uploadBtn);

    const continueBtn = document.createElement('button');
    continueBtn.type = 'button';
    continueBtn.className = 'collection-btn';
    continueBtn.innerHTML = '<i class="ri-play-line"></i> Continue';
    continueBtn.addEventListener('click', () => resumeCollectionJob(jobId, panel));
    actions.appendChild(continueBtn);
  }

  if (status === 'completed') {
    const metaLink = document.createElement('a');
    metaLink.href = `${COLLECTION_URL}/jobs/${jobId}/download/literature_info`;
    metaLink.textContent = 'Download literature_info.csv';
    metaLink.target = '_blank';
    downloads.appendChild(metaLink);

    const qratioLink = document.createElement('a');
    qratioLink.href = `${COLLECTION_URL}/jobs/${jobId}/download/qratio`;
    qratioLink.textContent = 'Download qratio.csv';
    qratioLink.target = '_blank';
    downloads.appendChild(qratioLink);

    renderContributeOffer(panel, data);
  }

  if (status === 'rejected') {
    const tip = document.createElement('button');
    tip.type = 'button';
    tip.className = 'collection-btn secondary';
    tip.innerHTML = '<i class="ri-chat-1-line"></i> Try another paper';
    tip.addEventListener('click', () => {
      const field = document.getElementById('inputField');
      if (field) {
        field.focus();
        field.placeholder = 'Enter a new PMID, or upload a PDF / quant table…';
      }
    });
    actions.appendChild(tip);
  }
}

function renderContributeOffer(panel, data) {
  const box = panel.querySelector('.collection-contribute');
  if (!box) return;
  const offer = data.offer_contribute || data.offerContribute || (data.summary && data.summary.offerContribute);
  const contribution = data.contribution || {};
  const rowCount = (data.summary && data.summary.qratioRowCount) || 0;
  const already = contribution.willing === true || contribution.willing === false;

  if (already) {
    box.style.display = 'block';
    box.innerHTML = contribution.willing
      ? `<div class="collection-contribute-title">Contribution intent recorded</div>
         <div class="collection-contribute-body">Thank you for supporting qPTM.</div>`
      : `<div class="collection-contribute-title">Contribution skipped</div>
         <div class="collection-contribute-body">No problem. You can still download the CSV files. </div>`;
    return;
  }

  if (!offer || rowCount <= 0) {
    box.style.display = 'none';
    box.innerHTML = '';
    return;
  }

  box.style.display = 'block';
  box.innerHTML = `
    <div class="collection-contribute-title">Contribute to the qPTM database?</div>
    <div class="collection-contribute-body">
      This run curated ${escapeHtml(String(rowCount))} site-level quantitative record(s).
      Sharing them helps other researchers. Choosing “Yes, contribute” only records your intent — it does not write to the live database immediately.
    </div>
    <div class="collection-contribute-actions"></div>
  `;
  const actions = box.querySelector('.collection-contribute-actions');
  const yesBtn = document.createElement('button');
  yesBtn.type = 'button';
  yesBtn.className = 'collection-btn';
  yesBtn.innerHTML = '<i class="ri-heart-3-line"></i> Yes, contribute';
  yesBtn.addEventListener('click', () => submitContribute(panel, true));
  const noBtn = document.createElement('button');
  noBtn.type = 'button';
  noBtn.className = 'collection-btn secondary';
  noBtn.innerHTML = 'Not now';
  noBtn.addEventListener('click', () => submitContribute(panel, false));
  actions.appendChild(yesBtn);
  actions.appendChild(noBtn);
}

async function submitContribute(panel, willing) {
  const jobId = panel.dataset.jobId;
  if (!jobId) return;
  const buttons = panel.querySelectorAll('.collection-contribute button');
  buttons.forEach((b) => { b.disabled = true; });
  try {
    const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/contribute`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ willing }),
    });
    if (!res.ok) throw new Error(`Contribute HTTP ${res.status}`);
    const data = await res.json();
    updateCollectionPanel(panel, data);
    const contentDiv = panel.parentElement?.querySelector('.msg-content');
    if (contentDiv) {
      contentDiv.innerHTML = `<p style="white-space:pre-wrap;">${escapeHtml(data.message || (willing ? 'Thank you for offering to contribute.' : 'Contribution skipped.'))}</p>`;
    }
  } catch (err) {
    buttons.forEach((b) => { b.disabled = false; });
    alert(err.message || 'Submit failed');
  }
}

function beginCollectionTurn(jobId, pmid) {
  if (welcome) welcome.style.display = 'none';
  const msg = document.createElement('div');
  msg.className = 'message assistant';
  const body = document.createElement('div');
  body.className = 'assistant-body';
  const panel = createCollectionPanelEl(jobId);
  if (pmid) {
    const pmidEl = panel.querySelector('.collection-pmid');
    if (pmidEl) pmidEl.textContent = `PMID ${pmid}`;
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

async function parseSseStream(response, onEvent) {
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
        await onEvent(currentEvent, data);
        currentEvent = null;
      }
    }
  }
}

async function streamCollectionJob(jobId, panel, contentDiv) {
  const response = await fetch(`${COLLECTION_URL}/jobs/${jobId}/stream`);
  if (!response.ok) throw new Error(`Stream HTTP ${response.status}`);
  let terminal = false;
  await parseSseStream(response, async (event, data) => {
    updateCollectionPanel(panel, data);
    if (event === 'status') return;
    if (['awaiting_continue', 'awaiting_upload', 'done', 'rejected', 'error'].includes(event)) {
      terminal = true;
      hideContentLoading(contentDiv);
      if (event === 'error' || data.status === 'error') {
        contentDiv.innerHTML = `<p style="color:#c0392b;white-space:pre-wrap;">${escapeHtml(data.message || data.error || 'Collection failed')}</p>`;
      } else if (event === 'rejected') {
        contentDiv.innerHTML = `<p style="white-space:pre-wrap;">${escapeHtml(data.message || 'This paper did not pass quantitative PTM screening.')}</p>`;
      } else if (event === 'done' || data.status === 'completed') {
        contentDiv.innerHTML = `<p style="white-space:pre-wrap;">${escapeHtml(data.message || 'Collection complete. Download the CSV files below, and optionally contribute to qPTM.')}</p>`;
      } else if (event === 'awaiting_upload') {
        contentDiv.innerHTML = `<p style="white-space:pre-wrap;">${escapeHtml(data.message || 'Please upload a file to continue.')}</p>`;
      } else {
        contentDiv.innerHTML = `<p style="white-space:pre-wrap;">${escapeHtml(data.message || 'Please continue from the panel above.')}</p>`;
      }
      chatArea.scrollTop = chatArea.scrollHeight;
    }
  });
  if (!terminal) {
    hideContentLoading(contentDiv);
    contentDiv.innerHTML = '<p style="color:var(--text-muted);">Collection stream ended unexpectedly.</p>';
  }
}

async function resumeCollectionJob(jobId, panel) {
  if (isStreaming) return;
  isStreaming = true;
  sendBtn.disabled = true;
  const contentDiv = panel.parentElement?.querySelector('.msg-content');
  if (contentDiv) showContentLoading(contentDiv, 'Continuing collection...');
  try {
    const res = await fetch(`${COLLECTION_URL}/jobs/${jobId}/resume`, { method: 'POST' });
    if (!res.ok) throw new Error(`Resume HTTP ${res.status}`);
    const data = await res.json();
    updateCollectionPanel(panel, data);
    await streamCollectionJob(jobId, panel, contentDiv);
  } catch (err) {
    if (contentDiv) {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = `<p style="color:#c0392b;">${escapeHtml(err.message)}</p>`;
    }
  } finally {
    isStreaming = false;
    sendBtn.disabled = false;
  }
}

async function uploadCollectionFile(jobId, uploadType, file, panel) {
  if (isStreaming) return;
  isStreaming = true;
  sendBtn.disabled = true;
  const userMsgEl = addMessage('user', 'Uploaded file');
  userMsgEl.insertAdjacentHTML('beforeend', renderUploadedFilesHtml([file]));
  const contentDiv = panel.parentElement?.querySelector('.msg-content');
  if (contentDiv) showContentLoading(contentDiv, 'Uploading file...');

  // Show upload progress above the composer
  if (!pendingFiles.some((f) => pendingFileKey(f) === pendingFileKey(file))) {
    pendingFiles.push(file);
  }
  setPendingFilesUploadState([file], 'uploading', 0);

  try {
    const fd = new FormData();
    fd.append('upload_type', uploadType);
    fd.append('file', file);
    const data = await uploadFormData(`${COLLECTION_URL}/jobs/${jobId}/upload`, fd, {
      onProgress: (ratio) => setPendingFilesUploadState([file], 'uploading', ratio * 100),
    });
    setPendingFilesUploadState([file], 'done', 100);
    updateCollectionPanel(panel, data);
    if (contentDiv) {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = `<p style="white-space:pre-wrap;">${escapeHtml(data.message || 'Upload complete. Click Continue to proceed.')}</p>`;
    }
  } catch (err) {
    setPendingFilesUploadState([file], 'error', 100);
    if (contentDiv) {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = `<p style="color:#c0392b;">${escapeHtml(err.message)}</p>`;
    }
  } finally {
    setTimeout(clearPendingFiles, 450);
    isStreaming = false;
    sendBtn.disabled = false;
  }
}

async function startCollectionFlow(message, files) {
  isStreaming = true;
  sendBtn.disabled = true;
  const userMsgEl = addMessage('user', message || (files.length ? 'Uploaded files' : 'Data collection'));
  if (files.length) {
    userMsgEl.insertAdjacentHTML('beforeend', renderUploadedFilesHtml(files));
  }

  const { panel, contentDiv } = beginCollectionTurn('pending', null);

  try {
    const fd = new FormData();
    if (message) fd.append('message', message);
    let fulltextAdded = false;
    let suppAdded = false;
    const uploadingFiles = [];
    files.forEach((file) => {
      const kind = classifyUploadKind(file.name);
      if (kind === 'fulltext' && !fulltextAdded) {
        fd.append('fulltext', file);
        fulltextAdded = true;
        uploadingFiles.push(file);
      } else if (kind === 'supplementary' && !suppAdded) {
        fd.append('supplementary', file);
        suppAdded = true;
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
    });

    if (uploadingFiles.length) {
      setPendingFilesUploadState(uploadingFiles, 'done', 100);
    }

    panel.dataset.jobId = data.job_id;
    updateCollectionPanel(panel, data);

    if (data.needs_pmid) {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = `<p style="color:#c0392b;">${escapeHtml(data.message || 'Could not resolve PMID.')}</p>`;
      return;
    }

    if (data.status === 'error') {
      hideContentLoading(contentDiv);
      contentDiv.innerHTML = `<p style="color:#c0392b;">${escapeHtml(data.message || data.error || 'Collection failed')}</p>`;
      return;
    }

    if (['awaiting_continue', 'awaiting_upload', 'completed', 'rejected'].includes(data.status)) {
      hideContentLoading(contentDiv);
      if (data.status === 'completed') {
        contentDiv.innerHTML = '<p>Collection complete. Download curated tables below.</p>';
      } else if (data.status === 'rejected') {
        contentDiv.innerHTML = `<p>${escapeHtml(data.message || 'Paper rejected.')}</p>`;
      } else {
        contentDiv.innerHTML = `<p>${escapeHtml(data.message || 'Waiting for your action above.')}</p>`;
      }
      return;
    }

    await streamCollectionJob(data.job_id, panel, contentDiv);
  } catch (err) {
    if (files.length) setPendingFilesUploadState(files, 'error', 100);
    hideContentLoading(contentDiv);
    contentDiv.innerHTML = `<p style="color:#c0392b;">Collection error: ${escapeHtml(err.message)}</p>
      <p style="font-size:13px;color:var(--text-muted);">Make sure the qPTM Agent backend is running.</p>`;
  } finally {
    setTimeout(clearPendingFiles, 450);
    isStreaming = false;
    sendBtn.disabled = false;
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
  const files = [...pendingFiles];
  if ((!text && !files.length) || isStreaming) return;

  inputField.value = '';
  resizeInputField();

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

  isStreaming = true;
  sendBtn.disabled = true;
  clearPendingFiles();

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

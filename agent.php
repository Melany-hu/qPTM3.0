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
<link rel="stylesheet" href="assets/css/agent.css?v=20260831-ts-agent">

</head>
<body class="agent-page">
<div id="preloader">
  <div class="preloader-inner">
    <div class="typing-dots typing-dots-lg" aria-hidden="true"><span></span><span></span><span></span></div>
    <span class="preloader-text">Loading...</span>
  </div>
</div>

<div id="site-header"></div>

<div class="agent-shell">
  <aside class="agent-sidebar" id="agentSidebar">
    <button class="sidebar-toggle" type="button" id="sidebarToggle" aria-label="Toggle sidebar">
      <i class="ri-sidebar-unfold-line"></i>
    </button>
    <button class="sidebar-new-btn" type="button" onclick="startNewConversation()">
      <i class="ri-add-line"></i> New chat
    </button>
    <div class="sidebar-history-label">History</div>
    <div class="sidebar-history" id="sidebarHistory"></div>
  </aside>

  <div class="agent-main">
    <div class="workflow-sidebar-backdrop" id="workflowSidebarBackdrop" aria-hidden="true"></div>
    <div class="chat-column">
      <div class="chat-toolbar">
        <button type="button" class="workflow-sidebar-toggle" id="workflowSidebarToggle" title="Agent Studio" aria-label="Open Agent Studio">
          <i class="ri-node-tree"></i>
          <span>Agent Studio</span>
        </button>
      </div>
      <div class="chat-area" id="chatArea">
        <div class="welcome" id="welcome">
          <div class="welcome-intro">
            <div class="welcome-header">
              <img class="welcome-logo" src="assets/img/logo.png" alt="qPTM">
              <div class="welcome-badge"><i class="ri-chat-smile-2-line"></i> AI-Powered PTM Explorer</div>
            </div>
            <p class="welcome-tagline">生物学问答助手 — 翻译后修饰、激酶底物、定量数据与文献。点击 <strong>Deep Research</strong> 进行深度调研。</p>
          </div>
          <div class="example-cards">
            <button type="button" class="example-card" onclick="sendExample('Which kinases phosphorylate AKT1 S473?')">
              <i class="ri-git-branch-line"></i>
              <span class="example-card-title">Upstream regulators</span>
              <span class="example-card-desc">Which kinases phosphorylate AKT1 S473?</span>
            </button>
            <button type="button" class="example-card" onclick="sendExample('TP53 S15 phosphorylation after DNA damage')">
              <i class="ri-line-chart-line"></i>
              <span class="example-card-title">Quantitative dynamics</span>
              <span class="example-card-desc">TP53 S15 after DNA damage</span>
            </button>
            <button type="button" class="example-card" onclick="sendExample('STAT3 Y705 phosphorylation in cancer signaling')">
              <i class="ri-heart-pulse-line"></i>
              <span class="example-card-title">Function &amp; disease</span>
              <span class="example-card-desc">STAT3 Y705 in cancer signaling</span>
            </button>
            <button type="button" class="example-card" onclick="sendExample('Comprehensive deep research on TP53 S15 phosphorylation', 'deep_research')">
              <i class="ri-telescope-line"></i>
              <span class="example-card-title">Deep Research</span>
              <span class="example-card-desc">Full investigation on TP53 S15</span>
            </button>
            <button type="button" class="example-card" onclick="sendExample('Collect quantitative PTM data from PMID 39732660')">
              <i class="ri-file-paper-2-line"></i>
              <span class="example-card-title">Literature collection</span>
              <span class="example-card-desc">Collect PTM data from a PMID</span>
            </button>
          </div>
        </div>
      </div>

      <div class="input-pending-files" id="pendingFiles"></div>
      <button class="scroll-bottom-btn" id="scrollBottomBtn" type="button" title="Scroll to bottom" aria-label="Scroll to bottom">
        <i class="ri-arrow-down-line"></i>
      </button>
      <div class="input-wrapper composer-card">
        <input type="file" id="fileInput" multiple accept=".pdf,.xml,.zip,.xlsx,.xls,.csv,.tsv" style="display:none">
        <textarea class="input-field" id="inputField"
          placeholder="Ask about a PTM site, or upload a PDF for literature collection…"
          rows="1" onkeydown="handleKey(event)"></textarea>
        <div class="input-actions">
          <button class="attach-btn" type="button" id="attachBtn" title="Attach PDF/XML or supplementary tables" onclick="document.getElementById('fileInput').click()">
            <i class="ri-attachment-2"></i>
          </button>
          <button class="dr-toggle-btn" type="button" id="deepResearchBtn" title="Deep Research — comprehensive PTM investigation" aria-pressed="false">
            <i class="ri-telescope-line"></i>
            <span class="dr-toggle-label">Deep Research</span>
          </button>
          <button class="send-btn" id="sendBtn" onclick="sendMessage()">
            <i class="ri-send-plane-fill"></i>
          </button>
        </div>
        <div class="composer-hint">Enter to send · Shift+Enter for new line</div>
      </div>
    </div><!-- /.chat-column -->

    <aside class="agent-workflow-sidebar" id="workflowSidebar" aria-hidden="true">
      <div class="workflow-sidebar-header">
        <div class="workflow-sidebar-title">
          <i class="ri-node-tree"></i>
          <span id="workflowSidebarTitle">Agent Studio</span>
        </div>
        <button type="button" class="workflow-sidebar-close" id="workflowSidebarClose" aria-label="Close workflow panel">
          <i class="ri-close-line"></i>
        </button>
      </div>
      <div class="workflow-sidebar-body" id="workflowSidebarBody">
        <div class="workflow-sidebar-empty">
          <i class="ri-git-branch-line"></i>
          <p>单 Agent 调研活动将在此展示（计划、工具调用、文献检索）。</p>
          <p class="workflow-sidebar-empty-hint">发起问题后，点击消息中的「Agent Studio」或顶部按钮可打开本面板。</p>
        </div>
      </div>
    </aside>
  </div><!-- /.agent-main -->
</div>

<div class="clarify-modal" id="clarificationModal" hidden>
  <div class="clarify-backdrop" data-clarify-dismiss></div>
  <div class="clarify-card" role="dialog" aria-modal="true" aria-labelledby="clarifyTitle">
    <div class="clarify-header">
      <h2 class="clarify-title" id="clarifyTitle">补充研究信息</h2>
      <p class="clarify-intro"></p>
    </div>
    <div class="clarify-fields"></div>
    <div class="clarify-free-text">
      <label class="clarify-free-label"></label>
      <textarea class="clarify-free-input" rows="2"></textarea>
    </div>
    <div class="clarify-actions">
      <button type="button" class="clarify-skip-btn">跳过，直接执行</button>
      <button type="button" class="clarify-submit-btn">开始研究</button>
    </div>
  </div>
</div>

<script>
window.QPTM_AGENT_CONFIG = {
  chatUrl: <?php echo json_encode($BACKEND_URL, JSON_UNESCAPED_SLASHES); ?>
};
</script>
<script src="assets/js/agent.js?v=20260831-ts-agent"></script>
</body>
</html>

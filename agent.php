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
<link rel="stylesheet" href="assets/css/agent.css?v=20260906-sidebar-rail">

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
    <div class="sidebar-header">
      <span class="sidebar-brand">PTM Agent</span>
      <button type="button" class="sidebar-icon-btn sidebar-collapse-btn" id="sidebarCollapseBtn" title="Collapse sidebar" aria-label="Collapse sidebar">
        <i class="ri-side-bar-line"></i>
      </button>
    </div>
    <div class="sidebar-rail" aria-hidden="true">
      <button type="button" class="sidebar-rail-btn" id="sidebarExpandBtn" title="Open sidebar" aria-label="Open sidebar">
        <i class="ri-side-bar-line"></i>
      </button>
      <button type="button" class="sidebar-rail-btn" id="sidebarRailNewBtn" title="New chat" aria-label="New chat">
        <i class="ri-edit-2-line"></i>
      </button>
    </div>
    <div class="sidebar-body">
      <button class="sidebar-new-btn" type="button" id="sidebarNewBtn">
        <i class="ri-edit-2-line"></i>
        <span>New chat</span>
      </button>
      <div class="sidebar-history" id="sidebarHistory"></div>
    </div>
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
              <img class="welcome-logo" src="assets/img/logo.gif" alt="qPTM">
              <div class="welcome-badge"><i class="ri-chat-smile-2-line"></i> AI-Powered PTM Explorer</div>
            </div>
          </div>
          <div class="example-chips">
            <div class="example-row">
              <button type="button" class="example-chip" onclick="sendExample('Which kinases phosphorylate AKT1 S473?')">Which kinases phosphorylate AKT1 S473?</button>
              <button type="button" class="example-chip" onclick="sendExample('TP53 S15 phosphorylation after DNA damage')">TP53 S15 phosphorylation after DNA damage</button>
              <button type="button" class="example-chip" onclick="sendExample('STAT3 Y705 phosphorylation in cancer signaling')">STAT3 Y705 phosphorylation in cancer signaling</button>
            </div>
            <div class="example-row">
              <button type="button" class="example-chip" onclick="sendExample('Where is EGFR Y1173 phosphorylated in the cell?')">Where is EGFR Y1173 phosphorylated in the cell?</button>
              <button type="button" class="example-chip" onclick="sendExample('Which conditions regulate MDM2 S166 acetylation?')">Which conditions regulate MDM2 S166 acetylation?</button>
              <button type="button" class="example-chip" onclick="sendExample('What is the role of PTEN K289 ubiquitination in signaling?')">What is the role of PTEN K289 ubiquitination in signaling?</button>
            </div>
            <div class="example-row">
              <button type="button" class="example-chip" onclick="sendExample('What drugs affect EGFR Y1068 phosphorylation?')">What drugs affect EGFR Y1068 phosphorylation?</button>
              <button type="button" class="example-chip example-chip-dr" onclick="sendExample('Comprehensive deep research on TP53 S15 phosphorylation', 'deep_research')"><i class="ri-microscope-line" aria-hidden="true"></i> Deep research on TP53 S15 phosphorylation</button>
              <button type="button" class="example-chip example-chip-collection" onclick="sendExample('Collect quantitative PTM data from PMID 39732660')">Collect quantitative PTM data from PMID 39732660</button>
            </div>
          </div>
        </div>
      </div>

      <div class="input-pending-files" id="pendingFiles"></div>
      <button class="scroll-bottom-btn" id="scrollBottomBtn" type="button" title="Scroll to bottom" aria-label="Scroll to bottom">
        <i class="ri-arrow-down-line"></i>
      </button>
      <div class="input-wrapper composer-card">
        <input type="file" id="fileInput" multiple accept=".pdf,.xml,.zip,.xlsx,.xls,.csv,.tsv" style="display:none">
        <div class="composer-bar">
          <button class="attach-btn" type="button" id="attachBtn" title="Attach PDF/XML or supplementary tables" onclick="document.getElementById('fileInput').click()">
            <i class="ri-attachment-2"></i>
          </button>
          <textarea class="input-field" id="inputField"
            placeholder="Ask about a PTM site, or upload a PDF for literature collection."
            rows="1" onkeydown="handleKey(event)"></textarea>
          <div class="composer-end">
            <button class="dr-toggle-btn" type="button" id="deepResearchBtn" title="Deep Research — comprehensive PTM investigation" aria-pressed="false">
              <i class="ri-microscope-line"></i>
              <span class="dr-toggle-label">Deep Research</span>
            </button>
            <button class="send-btn" id="sendBtn" onclick="sendMessage()">
              <i class="ri-arrow-up-line"></i>
            </button>
          </div>
        </div>
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
          <p>此处展示 Agent 的思考、计划与工作流（阶段、工具、文献）。</p>
          <p class="workflow-sidebar-empty-hint">发起问题后，点击消息中的「Agent Studio」或顶部按钮可打开本面板。</p>
        </div>
      </div>
    </aside>
  </div><!-- /.agent-main -->
</div>

<script>
window.QPTM_AGENT_CONFIG = {
  chatUrl: <?php echo json_encode($BACKEND_URL, JSON_UNESCAPED_SLASHES); ?>
};
</script>
<script src="assets/js/agent.js?v=20260906-sidebar-rail"></script>
</body>
</html>

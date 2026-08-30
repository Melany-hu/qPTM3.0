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
<link rel="stylesheet" href="assets/css/agent.css?v=20260824-preview-fetch">

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
  <button class="scroll-bottom-btn" id="scrollBottomBtn" type="button" title="Scroll to bottom" aria-label="Scroll to bottom">
    <i class="ri-arrow-down-line"></i>
  </button>
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
window.QPTM_AGENT_CONFIG = {
  chatUrl: <?php echo json_encode($BACKEND_URL, JSON_UNESCAPED_SLASHES); ?>
};
</script>
<script src="assets/js/agent.js?v=20260824-preview-fetch"></script>
</body>
</html>

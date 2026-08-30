(function () {
  'use strict';

  document.documentElement.classList.add('preloader-active');
  if (!document.getElementById('preloader-critical')) {
    var critical = document.createElement('style');
    critical.id = 'preloader-critical';
    critical.textContent =
      'html.preloader-active body{overflow:hidden}' +
      'html.preloader-active body>*:not(#preloader){visibility:hidden}' +
      '#preloader{position:fixed;inset:0;z-index:999999;display:flex;align-items:center;justify-content:center;background:#f5f7fa}' +
      '#preloader.preloader-hidden{opacity:0;visibility:hidden;pointer-events:none;transition:opacity .45s ease,visibility .45s ease}' +
      '.preloader-inner{display:flex;flex-direction:column;align-items:center;gap:16px}' +
      '.typing-dots{display:inline-flex;align-items:center;gap:4px;padding:4px 0;line-height:1}' +
      '.typing-dots span{width:8px;height:8px;border-radius:50%;background:#8e97a0;animation:qptmBounce 1.4s ease-in-out infinite}' +
      '.typing-dots span:nth-child(2){animation-delay:.2s}' +
      '.typing-dots span:nth-child(3){animation-delay:.4s}' +
      '.typing-dots-lg{gap:6px}' +
      '.typing-dots-lg span{width:12px;height:12px;background:#0e74d3}' +
      '.preloader-text{font:14px/1.4 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;color:#8e97a0}' +
      '@keyframes qptmBounce{0%,60%,100%{transform:translateY(0);opacity:.4}30%{transform:translateY(-6px);opacity:1}}';
    (document.head || document.documentElement).appendChild(critical);
  }

  function hidePreloader() {
    var preloader = document.getElementById('preloader');
    document.documentElement.classList.remove('preloader-active');
    document.body.classList.remove('preloader-active');
    if (!preloader || preloader.classList.contains('preloader-hidden')) return;
    preloader.classList.add('preloader-hidden');
    setTimeout(function () {
      if (preloader.parentNode) preloader.parentNode.removeChild(preloader);
    }, 500);
  }
  window.hideQptmPreloader = hidePreloader;

  function isDeferredPreloaderPage() {
    var page = window.location.pathname.split('/').pop() || 'index.html';
    return page === 'result.html';
  }

  if (!isDeferredPreloaderPage()) {
    if (document.readyState === 'complete') {
      hidePreloader();
    } else {
      window.addEventListener('load', hidePreloader);
    }
  }

  function loadSync(url) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', url, false);
    xhr.send(null);
    if (xhr.status >= 200 && xhr.status < 300) return xhr.responseText;
    return '';
  }

  function extractSection(html, name) {
    var re = new RegExp('<!-- ' + name + ' -->([\\s\\S]*?)<!-- END-' + name + ' -->');
    var match = html.match(re);
    return match ? match[1].trim() : '';
  }

  function injectHead(html) {
    var content = extractSection(html, 'COMMON-HEAD');
    if (!content) return;
    var wrap = document.createElement('div');
    wrap.innerHTML = content;
    while (wrap.firstChild) document.head.appendChild(wrap.firstChild);
  }

  function setActiveNav() {
    var page = window.location.pathname.split('/').pop() || 'index.html';
    document.querySelectorAll('.nav-menu a[href]').forEach(function (link) {
      if (link.getAttribute('href') === page) link.classList.add('active');
    });
  }

  function initTooltips() {
    if (!window.jQuery || !jQuery.fn.tooltip) return;
    jQuery('[data-toggle="tooltip"]').tooltip({
      template: '<div class="tooltip qptm-tooltip" role="tooltip"><div class="arrow"></div><div class="tooltip-inner"></div></div>',
      delay: { show: 280, hide: 80 },
      container: 'body',
      boundary: 'window'
    });
  }
  window.initQptmTooltips = initTooltips;

  var headerHtml = loadSync('header.html');
  injectHead(headerHtml);

  document.addEventListener('DOMContentLoaded', function () {
    document.body.classList.add('preloader-active');

    var nav = extractSection(headerHtml, 'SITE-NAV');
    var headerEl = document.getElementById('site-header');
    if (headerEl && nav) headerEl.outerHTML = nav;

    var footerHtml = loadSync('footer.html');
    var footerEl = document.getElementById('site-footer');
    if (footerEl && footerHtml) footerEl.outerHTML = footerHtml.trim();

    setActiveNav();
    setTimeout(initTooltips, 0);
  });
})();

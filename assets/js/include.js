(function () {
  'use strict';

  document.documentElement.classList.add('preloader-active');
  if (!document.getElementById('preloader-critical')) {
    var critical = document.createElement('style');
    critical.id = 'preloader-critical';
    critical.textContent =
      'html.preloader-active,html.preloader-active body{overflow:hidden}' +
      /* Cover only — do not toggle visibility on page content.
         Toggling visibility re-triggers CSS transitions (e.g. adv-search
         drawer translateX), which looks like a left slide on reveal. */
      '#preloader{position:fixed;inset:0;z-index:999999;display:flex;align-items:center;justify-content:center;background:#f5f7fa}' +
      '#preloader.preloader-hidden{opacity:0;visibility:hidden;pointer-events:none;transition:opacity .25s ease,visibility .25s ease}' +
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

  function whenStylesAndFontsReady(callback) {
    var done = false;
    function finish() {
      if (done) return;
      done = true;
      callback();
    }

    function linkLooksReady(link) {
      try {
        // Same-origin or CORS-enabled: sheet is set once loaded.
        // Cross-origin without CORS: sheet is still non-null after load in modern browsers.
        if (link.sheet) return true;
      } catch (e) {
        // Some browsers throw on access; treat as ready enough to reveal.
        return true;
      }
      return false;
    }

    function waitStylesheets() {
      var links = Array.prototype.slice.call(document.querySelectorAll('link[rel="stylesheet"]'));
      if (!links.length) {
        finishFonts();
        return;
      }

      var pending = links.length;
      function oneDone() {
        pending -= 1;
        if (pending <= 0) finishFonts();
      }

      links.forEach(function (link) {
        if (linkLooksReady(link)) {
          oneDone();
          return;
        }
        var settled = false;
        function settle() {
          if (settled) return;
          settled = true;
          oneDone();
        }
        link.addEventListener('load', settle);
        link.addEventListener('error', settle);
        // If load already fired before listeners attached, poll briefly.
        var tries = 0;
        (function poll() {
          if (settled) return;
          if (linkLooksReady(link) || tries++ > 40) {
            settle();
            return;
          }
          setTimeout(poll, 50);
        })();
      });
    }

    function finishFonts() {
      if (document.fonts && document.fonts.ready) {
        var finished = false;
        function doneFonts() {
          if (finished) return;
          finished = true;
          finish();
        }
        document.fonts.ready.then(doneFonts).catch(doneFonts);
        // Don't block forever on slow CDN icon fonts.
        setTimeout(doneFonts, 1500);
      } else {
        finish();
      }
    }

    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', waitStylesheets);
    } else {
      waitStylesheets();
    }
  }

  if (!isDeferredPreloaderPage()) {
    // Wait for CSS + icon fonts so Remix Icon glyphs are not briefly garbled,
    // but do not wait for window.load / images.
    whenStylesAndFontsReady(function () {
      requestAnimationFrame(function () {
        hidePreloader();
      });
    });
    // Absolute safety net
    setTimeout(hidePreloader, 4000);
  }

  function isDeferredPreloaderPage() {
    var page = window.location.pathname.split('/').pop() || 'index.html';
    return page === 'result.html';
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

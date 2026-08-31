(function(window, $) {
  'use strict';

  var HIGHLIGHT_COLOR = '#0e74d3';

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function resolveSlsId(name, slsMap) {
    if (!name) {
      return undefined;
    }
    var trimmed = String(name).trim();
    if (!trimmed) {
      return undefined;
    }

    var slMatch = trimmed.match(/^SL-?0*(\d+)$/i);
    if (slMatch) {
      return parseInt(slMatch[1], 10);
    }
    if (/^\d+$/.test(trimmed)) {
      return parseInt(trimmed, 10);
    }
    if (slsMap[trimmed] !== undefined) {
      return slsMap[trimmed];
    }

    // UniProt sometimes stores hierarchical paths: "Nucleus, PML body"
    if (trimmed.indexOf(',') !== -1) {
      var parts = trimmed.split(',').map(function(part) {
        return part.trim();
      }).filter(Boolean);
      for (var i = parts.length - 1; i >= 0; i--) {
        if (slsMap[parts[i]] !== undefined) {
          return slsMap[parts[i]];
        }
      }
    }
    return undefined;
  }

  function displayLocationLabel(name) {
    var trimmed = String(name).trim();
    if (trimmed.indexOf(',') === -1) {
      return trimmed;
    }
    var parts = trimmed.split(',').map(function(part) {
      return part.trim();
    }).filter(Boolean);
    return parts.length ? parts[parts.length - 1] : trimmed;
  }

  function injectSwissBioPicsLayoutFix(el) {
    if (!el || !el.shadowRoot) {
      return;
    }
    var styleId = 'swissbiopics-layout-fix';
    if (el.shadowRoot.getElementById(styleId)) {
      return;
    }
    var style = document.createElement('style');
    style.id = styleId;
    style.textContent = [
      '#swissbiopic {',
      '  display: block !important;',
      '  width: 100% !important;',
      '  height: auto !important;',
      '  max-width: 100% !important;',
      '  grid-template-columns: 1fr !important;',
      '  grid-template-areas: "picture" !important;',
      '}',
      '#swissbiopic .terms {',
      '  display: none !important;',
      '  width: 0 !important;',
      '  height: 0 !important;',
      '  overflow: hidden !important;',
      '  margin: 0 !important;',
      '  padding: 0 !important;',
      '  visibility: hidden !important;',
      '  position: absolute !important;',
      '  pointer-events: none !important;',
      '}',
      '#swissbiopic .svg,',
      '#swissbiopic svg {',
      '  width: 100% !important;',
      '  max-width: 280px !important;',
      '  height: auto !important;',
      '  display: block !important;',
      '}'
    ].join('\n');
    el.shadowRoot.appendChild(style);
  }

  function injectHighlightStyle(rootEl, slsId) {
    var el = rootEl.querySelector('sib-swissbiopics-sl');
    if (!el || !el.shadowRoot) {
      return;
    }
    var oldStyle = el.shadowRoot.getElementById('dynamic-swissbiopics-style');
    if (oldStyle) {
      oldStyle.remove();
    }
    if (slsId === undefined || slsId === null || slsId === '') {
      return;
    }
    var padded = String(slsId).padStart(4, '0');
    var style = document.createElement('style');
    style.id = 'dynamic-swissbiopics-style';
    style.textContent = [
      '#SL' + padded + ' *:not(text) {fill:' + HIGHLIGHT_COLOR + ' !important;}',
      '#SL' + padded + ' *:not(path, .coloured) {opacity:0.8 !important;}',
      '#SL' + padded + ' .coloured {stroke:black !important;}'
    ].join('\n');
    el.shadowRoot.appendChild(style);
  }

  function waitForSVGAndBindHover($root) {
    var rootEl = $root[0];
    var el = rootEl.querySelector('sib-swissbiopics-sl');
    if (el && el.shadowRoot && el.shadowRoot.querySelector('svg')) {
      injectSwissBioPicsLayoutFix(el);
      $root.find('.location-item').off('.swissloc');
      $root.find('.location-item').on('mouseenter.swissloc', function() {
        injectHighlightStyle(rootEl, $(this).data('slsid'));
      });
      $root.find('.location-item').on('mouseleave.swissloc', function() {
        injectHighlightStyle(rootEl);
      });
      return;
    }
    setTimeout(function() {
      waitForSVGAndBindHover($root);
    }, 100);
  }

  function renderKnownLocalization($root) {
    if (!$root || !$root.length) {
      return;
    }
    if ($root.attr('data-rendered') === '1') {
      return;
    }

    var locationStr = $root.attr('data-locations') || '';
    var taxid = $root.attr('data-taxid') || '9606';
    var slsMap = window.QPTM_SLS_MAP || {};
    var locationNames = locationStr.split(';').map(function(s) {
      return s.trim();
    }).filter(Boolean);

    // de-duplicate while preserving order
    var seen = {};
    locationNames = locationNames.filter(function(name) {
      var key = name.toLowerCase();
      if (seen[key]) {
        return false;
      }
      seen[key] = true;
      return true;
    });

    if (!locationNames.length) {
      $root.html('<span class="known-localization-empty">-</span>');
      $root.attr('data-rendered', '1');
      return;
    }

    var slsIds = [];
    var idSeen = {};
    locationNames.forEach(function(name) {
      var id = resolveSlsId(name, slsMap);
      if (id !== undefined && !idSeen[id]) {
        idSeen[id] = true;
        slsIds.push(id);
      }
    });

    var component = [
      '<sib-swissbiopics-sl taxid="', escapeHtml(taxid), '" sls="', escapeHtml(slsIds.join(',')), '">',
      '<style>',
      'text.subcell_description, text.subcell_name,',
      'text[property="description"], text[property="name"] {',
      'display:none !important; visibility:hidden !important; opacity:0 !important;',
      '}',
      '</style>',
      '</sib-swissbiopics-sl>'
    ].join('');

    $root.find('.cell-figure').html(component);

    var listHtml = locationNames.map(function(name) {
      var slsId = resolveSlsId(name, slsMap);
      var label = displayLocationLabel(name);
      return [
        '<div class="location-item" data-slsid="', slsId === undefined ? '' : slsId, '">',
        '<span class="location-item-icon" aria-hidden="true">',
        '<svg width="18" height="18" viewBox="0 0 24 24" fill="none">',
        '<path d="M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z" fill="currentColor"/>',
        '</svg>',
        '</span>',
        '<span class="location-item-label">', escapeHtml(label), '</span>',
        '</div>'
      ].join('');
    }).join('');

    $root.find('.cell-location-list').html(listHtml);
    $root.attr('data-rendered', '1');
    waitForSVGAndBindHover($root);
  }

  function initKnownLocalizations($container) {
    var $scope = $container && $container.length ? $container : $(document);
    $scope.find('.known-localization').each(function() {
      renderKnownLocalization($(this));
    });
  }

  window.initKnownLocalizations = initKnownLocalizations;
  window.renderKnownLocalization = renderKnownLocalization;
})(window, jQuery);

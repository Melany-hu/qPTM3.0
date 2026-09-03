(function ($) {
  'use strict';

  var EXAMPLE_GENE = 'TP53';
  var EXAMPLE_UNIPROT = 'P04637';
  var EXAMPLE_POS = 392;
  var EXAMPLE_CONDITION = 'UCEC';
  var EXAMPLE_ONTOLOGY = 'endometrial carcinoma';
  var CONTRAST_TYPES = {
    pharmacological: true,
    genetic: true,
    physical: true,
    disease: true,
    cell_state: true,
    other: true
  };
  var uniprotResolveCache = {};

  function apiBase() {
    return window.location.origin.replace(/\/$/, '') + '/api';
  }

  function isUniprotAc(value) {
    return /^[OPQ][0-9][A-Z0-9]{3}[0-9](-[0-9]+)?$/i.test(value)
      || /^[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](-[0-9]+)?$/i.test(value);
  }

  function initHelpNav() {
    var $links = $('.help-nav-link');
    var sections = $links.map(function () {
      var $target = $($(this).attr('href'));
      return $target.length ? $target[0] : null;
    }).get().filter(Boolean);

    if (!sections.length) return;

    var offset = 80;

    function setActive(id) {
      $links.removeClass('active');
      $links.filter('[href="' + id + '"]').addClass('active');
    }

    function currentSectionId() {
      var scrollTop = $(window).scrollTop() + offset;
      var current = sections[0];
      sections.forEach(function (section) {
        if ($(section).offset().top <= scrollTop) {
          current = section;
        }
      });
      return '#' + current.id;
    }

    $links.on('click', function (e) {
      e.preventDefault();
      var id = $(this).attr('href');
      var $target = $(id);
      if (!$target.length) return;
      $('html, body').stop().animate({
        scrollTop: $target.offset().top - offset + 1
      }, 350, 'swing');
      setActive(id);
      if (history.replaceState) history.replaceState(null, '', id);
    });

    $(window).on('scroll.apiNav', function () {
      setActive(currentSectionId());
    });

    if (window.location.hash) {
      setActive(window.location.hash);
    } else {
      setActive(currentSectionId());
    }
  }

  function currentKind() {
    return $('#api-try-endpoint').val();
  }

  /** site: required; protein: optional site filter; others: unused */
  function positionMode(kind) {
    if (kind === 'site') return 'required';
    if (kind === 'protein') return 'optional';
    return 'none';
  }

  function readPosition() {
    var raw = $.trim($('#api-try-pos').val());
    if (!raw) return null;
    var pos = parseInt(raw, 10);
    return (pos > 0) ? pos : null;
  }

  function syncTryUi() {
    var kind = currentKind();
    var $qLabel = $('#api-try-q-label');
    var $posLabel = $('#api-try-pos-label');
    var $q = $('#api-try-q');
    var $pos = $('#api-try-pos');
    var posMode = positionMode(kind);

    if (kind === 'browse') {
      $qLabel.text('Type / ontology');
      $q.attr('placeholder', 'pharmacological · endometrial carcinoma');
    } else if (kind === 'conditions') {
      $qLabel.text('Condition / type');
      $q.attr('placeholder', 'UCEC or pharmacological');
    } else if (kind === 'protein' || kind === 'site') {
      $qLabel.text('UniProt');
      $q.attr('placeholder', EXAMPLE_UNIPROT);
    } else {
      $qLabel.text('Keyword');
      $q.attr('placeholder', EXAMPLE_GENE);
    }

    var posEnabled = posMode !== 'none';
    $posLabel.toggleClass('is-disabled', !posEnabled);
    $pos.prop('disabled', !posEnabled);
    $pos.toggleClass('is-disabled', !posEnabled);
    if (posMode === 'required' && !readPosition()) {
      $pos.val(String(EXAMPLE_POS));
    }
  }

  function resolveUniprotAsync(raw) {
    var q = $.trim(raw || '');
    var deferred = $.Deferred();
    if (!q) {
      return deferred.resolve(EXAMPLE_UNIPROT).promise();
    }
    if (isUniprotAc(q)) {
      return deferred.resolve(q.toUpperCase()).promise();
    }
    if (/^tp53$/i.test(q)) {
      return deferred.resolve(EXAMPLE_UNIPROT).promise();
    }
    var cacheKey = q.toUpperCase();
    if (uniprotResolveCache[cacheKey]) {
      return deferred.resolve(uniprotResolveCache[cacheKey]).promise();
    }
    $.ajax({
      url: apiBase() + '/search.php',
      dataType: 'json',
      data: { q: q, field: 'gene', organism: 'human', per_page: 1 },
      timeout: 15000
    }).done(function (data) {
      var ac = (data.events && data.events[0] && data.events[0].uniprot_ac) || '';
      if (ac) {
        uniprotResolveCache[cacheKey] = ac;
        deferred.resolve(ac);
      } else {
        deferred.resolve(q);
      }
    }).fail(function () {
      deferred.resolve(q);
    });
    return deferred.promise();
  }

  function buildBrowseUrl(raw) {
    var q = $.trim(raw || '') || EXAMPLE_ONTOLOGY;
    var base = apiBase() + '/browse.php?type=condition&per_page=20';
    var key = q.toLowerCase().replace(/\s+/g, '_');
    if (CONTRAST_TYPES[key] || CONTRAST_TYPES[q.toLowerCase()]) {
      var ct = CONTRAST_TYPES[key] ? key : q.toLowerCase();
      return base + '&contrast_type=' + encodeURIComponent(ct);
    }
    return base + '&ontology=' + encodeURIComponent(q);
  }

  function buildConditionsUrl(raw) {
    var q = $.trim(raw || '') || EXAMPLE_CONDITION;
    var base = apiBase() + '/conditions.php';
    var key = q.toLowerCase().replace(/\s+/g, '_');
    if (CONTRAST_TYPES[key] || CONTRAST_TYPES[q.toLowerCase()]) {
      var ct = CONTRAST_TYPES[key] ? key : q.toLowerCase();
      return base + '?contrast_type=' + encodeURIComponent(ct) + '&per_page=20';
    }
    return base + '?q=' + encodeURIComponent(q) + '&per_page=20';
  }

  function buildUrlWithAc(kind, ac, pos) {
    var base = apiBase();
    switch (kind) {
      case 'protein': {
        var url = base + '/protein.php?uniprot_ac=' + encodeURIComponent(ac);
        if (pos) url += '&position=' + pos;
        return url;
      }
      case 'site':
        return base + '/site.php?uniprot_ac=' + encodeURIComponent(ac)
          + '&position=' + (pos || EXAMPLE_POS);
      case 'conditions':
        return buildConditionsUrl(ac);
      case 'browse':
        return buildBrowseUrl(ac);
      default:
        return base + '/search.php?q=' + encodeURIComponent(ac || EXAMPLE_GENE)
          + '&field=gene&organism=human&per_page=5';
    }
  }

  function previewAc(q) {
    if (!q) return EXAMPLE_UNIPROT;
    if (isUniprotAc(q)) return q.toUpperCase();
    if (/^tp53$/i.test(q)) return EXAMPLE_UNIPROT;
    if (uniprotResolveCache[q.toUpperCase()]) return uniprotResolveCache[q.toUpperCase()];
    return q;
  }

  function buildUrlPreviewSync() {
    var kind = currentKind();
    var q = $.trim($('#api-try-q').val());
    var pos = readPosition();
    if (kind === 'search') {
      return buildUrlWithAc('search', q || EXAMPLE_GENE, null);
    }
    if (kind === 'browse') {
      return buildBrowseUrl(q);
    }
    if (kind === 'conditions') {
      return buildConditionsUrl(q);
    }
    var ac = previewAc(q);
    if (kind === 'site' && !pos) pos = EXAMPLE_POS;
    return buildUrlWithAc(kind, ac, kind === 'protein' ? pos : pos);
  }

  function updateUrlPreview() {
    $('#api-try-url').text(buildUrlPreviewSync());
  }

  function runRequest() {
    var kind = currentKind();
    var q = $.trim($('#api-try-q').val());
    var pos = readPosition();

    setTextKeepCopy($('#api-try-output'), 'Loading…');

    function send(url) {
      $('#api-try-url').text(url);
      $.ajax({
        url: url,
        dataType: 'json',
        timeout: 30000
      }).done(function (data) {
        setTextKeepCopy($('#api-try-output'), JSON.stringify(data, null, 2));
      }).fail(function (xhr) {
        var msg = xhr.responseJSON && xhr.responseJSON.error
          ? xhr.responseJSON.error
          : (xhr.statusText || 'Request failed');
        setTextKeepCopy($('#api-try-output'), 'Error ' + xhr.status + ': ' + msg);
      });
    }

    if (kind === 'search') {
      send(buildUrlWithAc('search', q || EXAMPLE_GENE, null));
      return;
    }
    if (kind === 'browse') {
      send(buildBrowseUrl(q));
      return;
    }
    if (kind === 'conditions') {
      send(buildConditionsUrl(q));
      return;
    }

    resolveUniprotAsync(q).done(function (ac) {
      if (ac !== q && isUniprotAc(ac)) {
        $('#api-try-q').val(ac);
      }
      if (kind === 'site') {
        if (!pos) {
          pos = EXAMPLE_POS;
          $('#api-try-pos').val(String(EXAMPLE_POS));
        }
        send(buildUrlWithAc('site', ac, pos));
      } else {
        send(buildUrlWithAc('protein', ac, pos));
      }
      syncTryUi();
    });
  }

  function onEndpointChange() {
    var kind = currentKind();
    if (kind === 'search') {
      $('#api-try-q').val(EXAMPLE_GENE);
      $('#api-try-pos').val('');
    } else if (kind === 'protein') {
      $('#api-try-q').val(EXAMPLE_UNIPROT);
      $('#api-try-pos').val(''); // optional filter
    } else if (kind === 'site') {
      $('#api-try-q').val(EXAMPLE_UNIPROT);
      $('#api-try-pos').val(String(EXAMPLE_POS));
    } else if (kind === 'conditions') {
      $('#api-try-q').val(EXAMPLE_CONDITION);
      $('#api-try-pos').val('');
    } else if (kind === 'browse') {
      $('#api-try-q').val(EXAMPLE_ONTOLOGY);
      $('#api-try-pos').val('');
    }
    syncTryUi();
    updateUrlPreview();
  }

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    var $ta = $('<textarea>').val(text).css({
      position: 'fixed',
      left: '-9999px',
      top: '0'
    }).appendTo(document.body);
    $ta[0].select();
    try {
      document.execCommand('copy');
      return $.Deferred().resolve().promise();
    } catch (err) {
      return $.Deferred().reject(err).promise();
    } finally {
      $ta.remove();
    }
  }

  function flashCopied($btn) {
    $btn.html('<i class="ri-check-line"></i>').attr('title', 'Copied');
    setTimeout(function () {
      $btn.html('<i class="ri-file-copy-line"></i>').attr('title', 'Copy');
    }, 1500);
  }

  function getCopyableText($el) {
    var $clone = $el.clone();
    $clone.find('.api-code-copy').remove();
    return $.trim($clone.text());
  }

  function attachCopyButton($el, ariaLabel) {
    if ($el.find('> .api-code-copy').length) return;
    var $btn = $('<button type="button" class="api-code-copy" title="Copy" aria-label="'
      + (ariaLabel || 'Copy') + '"><i class="ri-file-copy-line"></i></button>');
    $btn.on('click', function (e) {
      e.preventDefault();
      e.stopPropagation();
      var text = getCopyableText($el);
      if (!text) return;
      copyText(text).done(function () {
        flashCopied($btn);
      });
    });
    $el.css('position', 'relative');
    $el.append($btn);
  }

  /** Set text without removing an attached copy button. */
  function setTextKeepCopy($el, text) {
    var $btn = $el.children('.api-code-copy').detach();
    $el.text(text);
    if ($btn.length) {
      $el.append($btn);
    } else {
      attachCopyButton($el);
    }
  }

  function initCodeCopy() {
    $('.api-code').each(function () {
      attachCopyButton($(this), 'Copy code');
    });
  }

  $(function () {
    $('#api-base-url').text(apiBase());
    initHelpNav();
    initCodeCopy();
    $('#api-try-q').val(EXAMPLE_GENE);
    $('#api-try-pos').val('');
    syncTryUi();
    updateUrlPreview();
    $('#api-try-endpoint').on('change', onEndpointChange);
    $('#api-try-q, #api-try-pos').on('input', updateUrlPreview);
    $('#api-try-run').on('click', runRequest);
  });
})(jQuery);

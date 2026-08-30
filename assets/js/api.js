(function ($) {
  'use strict';

  function apiBase() {
    return window.location.origin.replace(/\/$/, '') + '/api';
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

  function buildUrl() {
    var kind = $('#api-try-endpoint').val();
    var q = $.trim($('#api-try-q').val()) || 'TP53';
    var pos = parseInt($('#api-try-pos').val(), 10) || 15;
    var base = apiBase();

    switch (kind) {
      case 'protein':
        return base + '/protein.php?uniprot_ac=' + encodeURIComponent(q);
      case 'site':
        return base + '/site.php?uniprot_ac=' + encodeURIComponent(q) + '&position=' + pos;
      case 'conditions':
        return base + '/conditions.php?uniprot_ac=' + encodeURIComponent(q) + '&position=' + pos;
      case 'kinases':
        return base + '/kinases.php?uniprot_ac=' + encodeURIComponent(q) + '&position=' + pos;
      case 'browse':
        return base + '/browse.php?type=gene&organism=human&letter=T&per_page=10';
      default:
        return base + '/search.php?q=' + encodeURIComponent(q) + '&field=gene&per_page=5';
    }
  }

  function updateUrlPreview() {
    $('#api-try-url').text(buildUrl());
  }

  function runRequest() {
    var url = buildUrl();
    updateUrlPreview();
    $('#api-try-output').text('Loading…');
    $.ajax({
      url: url,
      dataType: 'json',
      timeout: 30000
    }).done(function (data) {
      $('#api-try-output').text(JSON.stringify(data, null, 2));
    }).fail(function (xhr) {
      var msg = xhr.responseJSON && xhr.responseJSON.error
        ? xhr.responseJSON.error
        : (xhr.statusText || 'Request failed');
      $('#api-try-output').text('Error ' + xhr.status + ': ' + msg);
    });
  }

  function onEndpointChange() {
    var kind = $('#api-try-endpoint').val();
    if (kind === 'search') {
      $('#api-try-q').val('TP53');
    } else if (kind === 'protein' || kind === 'site' || kind === 'conditions' || kind === 'kinases') {
      $('#api-try-q').val('P04637');
    }
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

  function initCodeCopy() {
    $('.api-code').each(function () {
      var $pre = $(this);
      if ($pre.hasClass('api-try-output')) return;
      if ($pre.find('.api-code-copy').length) return;

      var codeText = $pre.text();
      var $btn = $('<button type="button" class="api-code-copy" title="Copy" aria-label="Copy code"><i class="ri-file-copy-line"></i></button>');
      $btn.on('click', function (e) {
        e.preventDefault();
        e.stopPropagation();
        copyText(codeText).done(function () {
          $btn.html('<i class="ri-check-line"></i>').attr('title', 'Copied');
          setTimeout(function () {
            $btn.html('<i class="ri-file-copy-line"></i>').attr('title', 'Copy');
          }, 1500);
        });
      });
      $pre.append($btn);
    });
  }

  $(function () {
    $('#api-base-url').text(apiBase());
    initHelpNav();
    initCodeCopy();
    updateUrlPreview();
    $('#api-try-endpoint').on('change', onEndpointChange);
    $('#api-try-q, #api-try-pos').on('input', updateUrlPreview);
    $('#api-try-run').on('click', runRequest);
  });
})(jQuery);

(function ($) {
  'use strict';

  var DATA_URL = 'resource/data/0_help_new_and_old.curated_summary.txt';

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatNumber(value) {
    var num = Number(value);
    if (!isFinite(num)) return escapeHtml(value);
    return num.toLocaleString('en-US');
  }

  function pmidLink(pmid) {
    var id = String(pmid).trim();
    return '<a href="https://pubmed.ncbi.nlm.nih.gov/' + escapeHtml(id) + '/" target="_blank" rel="noopener">' +
      escapeHtml(id) + '</a>';
  }

  function parseCuratedSummary(text) {
    var datasets = [];
    var literatures = [];
    var mode = null;

    text.split(/\r?\n/).forEach(function (line) {
      if (/^=+$/.test(line)) return;

      if (line === 'Summary of curated datasets') {
        mode = 'datasets_header';
        return;
      }
      if (line === 'Summary of curated literatures') {
        mode = 'literatures_header';
        return;
      }
      if (!line.trim()) return;

      if (mode === 'datasets_header') {
        mode = 'datasets';
        return;
      }
      if (mode === 'literatures_header') {
        mode = 'literatures';
        return;
      }

      var cols = line.split('\t');
      if (mode === 'datasets' && cols.length >= 4) {
        datasets.push(cols.slice(0, 4));
      } else if (mode === 'literatures' && cols.length >= 7) {
        literatures.push(cols.slice(0, 7));
      }
    });

    return { datasets: datasets, literatures: literatures };
  }

  function renderDatasetRows(rows) {
    return rows.map(function (row) {
      return '<tr>' +
        '<td>' + pmidLink(row[0]) + '</td>' +
        '<td>' + formatNumber(row[1]) + '</td>' +
        '<td>' + formatNumber(row[2]) + '</td>' +
        '<td>' + formatNumber(row[3]) + '</td>' +
        '</tr>';
    }).join('');
  }

  function renderLiteratureRows(rows) {
    // Data file: PMID, Sample, PTMs, Quantification, Condition, Enrichment, Mass Spec
    // Display:   PMID, PTMs, Sample, Condition, Quantification, Enrichment, Mass Spec
    return rows.map(function (row) {
      return '<tr>' +
        '<td>' + pmidLink(row[0]) + '</td>' +
        '<td>' + escapeHtml(row[2]) + '</td>' +
        '<td>' + escapeHtml(row[1]) + '</td>' +
        '<td>' + escapeHtml(row[4]) + '</td>' +
        '<td>' + escapeHtml(row[3]) + '</td>' +
        '<td>' + escapeHtml(row[5]) + '</td>' +
        '<td>' + escapeHtml(row[6]) + '</td>' +
        '</tr>';
    }).join('');
  }

  function showError(message) {
    $('#curated-datasets-body').html(
      '<tr><td colspan="4" class="text-muted">' + escapeHtml(message) + '</td></tr>'
    );
    $('#curated-literatures-body').html(
      '<tr><td colspan="7" class="text-muted">' + escapeHtml(message) + '</td></tr>'
    );
  }

  $(function () {
    $.get(DATA_URL)
      .done(function (text) {
        var data = parseCuratedSummary(text);
        $('#curated-datasets-body').html(renderDatasetRows(data.datasets));
        $('#curated-literatures-body').html(renderLiteratureRows(data.literatures));
      })
      .fail(function () {
        showError('Unable to load curated summary data.');
      });

    initHelpNav();
  });

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
      if (history.replaceState) {
        history.replaceState(null, '', id);
      }
    });

    $(window).on('scroll.helpNav', function () {
      setActive(currentSectionId());
    });

    if (window.location.hash) {
      setActive(window.location.hash);
    } else {
      setActive(currentSectionId());
    }
  }
})(jQuery);

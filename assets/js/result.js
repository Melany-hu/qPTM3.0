(function($) {
  'use strict';

  var RESULT_ROOT = '#main';

  var FILTER_CONFIG = {
    gene: { label: 'Gene Name' },
    pos: { label: 'Position' },
    mods: { label: 'Modification' },
    sample: { label: 'Sample' },
    samplecondition: { label: 'Condition' },
    qptmscore: { label: 'Reliability', formatLabel: function(value) { return value + ' Stars'; } }
  };

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function escapeSqlValue(text) {
    return String(text).replace(/'/g, "''");
  }

  function getAppliedValues($div) {
    var applied = $div.data('applied');
    return Array.isArray(applied) ? applied.slice() : [];
  }

  function setAppliedValues($div, values) {
    $div.data('applied', values.slice());
  }

  function getPendingValues($div) {
    var pending = [];
    $div.find('.rf-option.is-checked').each(function() {
      pending.push($(this).attr('data-value'));
    });
    return pending;
  }

  function setPendingValues($div, values) {
    var valueSet = {};
    values.forEach(function(value) {
      valueSet[value] = true;
    });
    $div.find('.rf-option').each(function() {
      var value = $(this).attr('data-value');
      $(this).toggleClass('is-checked', !!valueSet[value]);
    });
  }

  function updateFilterLabel($div) {
    var configKey = $div.attr('value');
    var config = FILTER_CONFIG[configKey];
    var applied = getAppliedValues($div);
    var $label = $div.find('.rf-select-label');

    if (!applied.length) {
      $label.text('All');
      $div.removeClass('has-filter');
      return;
    }

    var labels = applied.map(function(value) {
      if (config.formatLabel) {
        return config.formatLabel(value);
      }
      var optionLabel = '';
      $div.find('.rf-option').each(function() {
        if (String($(this).attr('data-value')) === String(value)) {
          optionLabel = $(this).find('.rf-option-label').text();
          return false;
        }
      });
      return optionLabel || value;
    });
    $label.text(labels.length > 1 ? labels.length + ' selected' : labels[0]);
    $div.addClass('has-filter');
  }

  function closeFilterPanels() {
    $(RESULT_ROOT + ' .rf-select').removeClass('is-open');
  }

  function openFilterPanel($div) {
    closeFilterPanels();
    setPendingValues($div, getAppliedValues($div));
    $div.find('.rf-select').addClass('is-open');
    var $panel = $div.find('.rf-select-panel');
    $panel.find('.rf-select-search input').val('').trigger('input');
    setTimeout(function() {
      $panel.find('.rf-select-search input').trigger('focus');
    }, 0);
  }

  function collectAppliedFiltersMap() {
    var map = {};
    $(RESULT_ROOT + ' .filter-div').each(function() {
      var key = $(this).attr('value');
      var applied = getAppliedValues($(this));
      if (key && applied.length) {
        map[key] = applied;
      }
    });
    return map;
  }

  function applyFilterDropdown($div, refreshTable) {
    setAppliedValues($div, getPendingValues($div));
    updateFilterLabel($div);
    closeFilterPanels();
    if (refreshTable === false) {
      return;
    }
    reloadFilterOptions(function() {
      changeResultTable(1);
    });
  }

  function clearFilterDropdown($div, refreshTable) {
    setAppliedValues($div, []);
    setPendingValues($div, []);
    updateFilterLabel($div);
    closeFilterPanels();
    if (refreshTable === false) {
      return;
    }
    reloadFilterOptions(function() {
      changeResultTable(1);
    });
  }

  function populateFilterSelects(filterOptions) {
    var previousApplied = collectAppliedFiltersMap();
    var $row = $(RESULT_ROOT + ' .filter-dropdowns');
    $row.empty();

    Object.keys(FILTER_CONFIG).forEach(function(key) {
      var values = (filterOptions && filterOptions[key]) ? filterOptions[key] : [];
      if (!values.length) {
        return;
      }

      var config = FILTER_CONFIG[key];
      var available = {};
      var html = '<div class="filter-div" value="' + key + '">';
      html += '<span class="filter-label">' + config.label + '</span>';
      html += '<div class="rf-select">';
      html += '<button type="button" class="rf-select-toggle" aria-haspopup="listbox">';
      html += '<span class="rf-select-label">All</span>';
      html += '<i class="ri-arrow-down-s-line rf-select-arrow"></i>';
      html += '</button>';
      html += '<div class="rf-select-panel">';
      html += '<div class="rf-select-search"><input type="search" class="form-control form-control-sm" placeholder="Search..."></div>';
      html += '<div class="rf-select-options" role="listbox">';
      values.forEach(function(value) {
        var rawValue = (value && typeof value === 'object') ? value.value : value;
        var label = (value && typeof value === 'object' && value.label)
          ? value.label
          : (config.formatLabel ? config.formatLabel(value) : value);
        available[String(rawValue)] = true;
        html += '<button type="button" class="rf-option" data-value="' + escapeHtml(rawValue) + '">';
        html += '<span class="rf-checkbox"><i class="ri-check-line"></i></span>';
        html += '<span class="rf-option-label">' + escapeHtml(label) + '</span>';
        html += '</button>';
      });
      html += '</div>';
      html += '<div class="rf-select-actions">';
      html += '<button type="button" class="btn btn-sm btn-primary rf-apply-btn">Apply</button>';
      html += '<button type="button" class="btn btn-sm rf-clear-btn">Clear</button>';
      html += '</div></div></div></div>';
      var $div = $(html);
      $row.append($div);

      var kept = (previousApplied[key] || []).filter(function(value) {
        return !!available[String(value)];
      });
      setAppliedValues($div, kept);
      updateFilterLabel($div);
    });
  }

  var PAGE_SIZE_OPTIONS = [10, 20, 50];
  var lastQueryContent = '';
  var initialLoadPending = true;
  var sortState = { field: null, dir: 'desc' };

  function getOrderInfo() {
    if (!sortState.field) {
      return 'timetype desc, qptmscore desc, up, pos';
    }
    return sortState.field + ' ' + sortState.dir;
  }

  function updateSortIndicators() {
    $(RESULT_ROOT + ' .result-table th.th-sortable').each(function() {
      var field = $(this).data('sort');
      var isActive = field === sortState.field;
      var $indicator = $(this).find('.th-sort-indicator');

      $(this).toggleClass('is-sorted', isActive);
      $indicator.removeClass('is-asc is-desc');
      if (isActive) {
        $indicator.addClass(sortState.dir === 'asc' ? 'is-asc' : 'is-desc');
      }
    });
  }

  function handleSortClick(field) {
    if (sortState.field === field) {
      sortState.dir = sortState.dir === 'desc' ? 'asc' : 'desc';
    } else {
      sortState.field = field;
      sortState.dir = 'desc';
    }
    updateSortIndicators();
    changeResultTable(1);
  }

  function hidePagePreloader() {
    if (!initialLoadPending) {
      return;
    }
    initialLoadPending = false;
    if (window.hideQptmPreloader) {
      window.hideQptmPreloader();
    }
  }

  function renderQuerySummary(total) {
    if (!lastQueryContent && total === undefined) {
      return;
    }

    var parts = [];
    if (lastQueryContent) {
      var detail = escapeHtml(lastQueryContent);
      if (!/\.\s*$/.test(lastQueryContent)) {
        detail += '.';
      }
      parts.push('<span class="query-summary-detail">' + detail + '</span>');
    }
    if (total !== undefined) {
      parts.push('<span class="query-summary-count">There are ' + total + ' records with your keywords.</span>');
    }

    if (parts.length) {
      $('#querySummary').html(parts.join(' ')).show();
    }
  }

  function getRowNumber() {
    var $select = $('#selectRowNumber');
    return $select.length ? Number($select.val()) || 20 : 20;
  }

  function renderPageInfo(total, nowPage) {
    var rowNumber = getRowNumber();
    var start = total === 0 ? 0 : (nowPage - 1) * rowNumber + 1;
    var optionsHtml = PAGE_SIZE_OPTIONS.map(function(size) {
      var selected = size === rowNumber ? ' selected' : '';
      return '<option value="' + size + '"' + selected + '>' + size + '</option>';
    }).join('');
    var selectHtml = '<select id="selectRowNumber" class="page-size-select" aria-label="Rows per page">' + optionsHtml + '</select>';
    $('#pageInfo').html('Showing ' + start + ' to ' + selectHtml + ' of ' + total + ' entries');
  }

  function collectSearchParams() {
    var params = new URLSearchParams(window.location.search);
    var postData = {};
    params.forEach(function(value, key) {
      if (key !== 'type') {
        postData[key] = value;
      }
    });
    postData.type = 'buildquery';
    if (!postData.simple_search_mod) {
      postData.simple_search_mod = 'All';
    }
    if (!postData.simple_search_org) {
      postData.simple_search_org = 'All';
    }
    if (!postData.simple_search_tag0) {
      postData.simple_search_tag0 = 'Context';
    }
    return postData;
  }

  function renderResultError(message) {
    $('#tableChange').html(
      '<tr><td colspan="10"><div class="status-msg status-error"><i class="ri-error-warning-line"></i> ' + message + '</div></td></tr>'
    );
  }

  function showResultsLoading(message) {
    var text = message || 'Loading results...';
    $('#pageInfo').text('Loading...');
    $('#pageButton').empty();
    $('#tableChange').html(
      '<tr><td colspan="10"><div class="status-msg">'
      + '<div class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></div> '
      + escapeHtml(text)
      + '</div></td></tr>'
    );
  }

  function getFilterInfo() {
    var filterInfos = [];
    $(RESULT_ROOT + ' .filter-div').each(function() {
      var tag = $(this).attr('value');
      var applied = getAppliedValues($(this));
      if (!applied.length) {
        return;
      }

      var selected = applied.map(function(value) {
        return tag + " = '" + escapeSqlValue(value) + "'";
      });
      filterInfos.push('(' + selected.join(' or ') + ')');
    });
    return filterInfos;
  }

  function getInlineSearchInfo() {
    var searchInfos = [];
    $(RESULT_ROOT + " input[name='genename']").each(function() {
      if ($(this).val() !== '') {
        searchInfos.push("gene like '%" + $(this).val() + "%'");
      }
    });
    $(RESULT_ROOT + " input[name='uniprotaccs']").each(function() {
      if ($(this).val() !== '') {
        searchInfos.push("up like '%" + $(this).val() + "%'");
      }
    });
    return searchInfos;
  }

  function changeResultTable(nowPage) {
    var rawQueryInfo = $('#rawQueryInfo').text();
    if (!rawQueryInfo) {
      renderResultError('Search query is not ready yet.');
      return;
    }

    showResultsLoading('Loading results...');

    var newQueryInfo = [rawQueryInfo]
      .concat(getFilterInfo(), getInlineSearchInfo())
      .join(' and ');
    var rowNumber = getRowNumber();

    $.ajax({
      url: './resource/functions.php',
      method: 'POST',
      dataType: 'json',
      data: {
        type: 'change',
        newQueryInfo: newQueryInfo,
        nowPage: nowPage,
        rowNumber: rowNumber,
        orderInfo: getOrderInfo()
      },
      success: function(returnInfo) {
        $('#tableChange').html(returnInfo.tableChange);
        if (returnInfo.queryResNum !== undefined && returnInfo.nowPage !== undefined) {
          renderPageInfo(returnInfo.queryResNum, returnInfo.nowPage);
          renderQuerySummary(returnInfo.queryResNum);
        } else {
          $('#pageInfo').html(returnInfo.pageInfoChange);
        }
        $('#pageButton').html(returnInfo.pageButtonChange);
        hidePagePreloader();
      },
      error: function(jqXHR, textStatus, errorThrown) {
        renderResultError('Failed to load results: ' + textStatus);
        console.error('AJAX error:', textStatus, errorThrown);
        hidePagePreloader();
      }
    });
  }

  function downloadResultTable() {
    var rawQueryInfo = $('#rawQueryInfo').text();
    if (!rawQueryInfo) {
      alert('Search query is not ready yet.');
      return;
    }

    var newQueryInfo = [rawQueryInfo]
      .concat(getFilterInfo(), getInlineSearchInfo())
      .join(' and ');

    $.post('./resource/functions.php', { type: 'download', newQueryInfo: newQueryInfo }, function(filename, status) {
      if (status === 'success' && filename) {
        var alink = document.createElement('a');
        alink.download = 'qPTM.result.txt';
        alink.href = './resource/download/' + filename;
        alink.click();
      } else {
        alert('Failed, please try again!');
      }
    }).fail(function() {
      alert('Failed to generate download file, please try again!');
    });
  }

  function updateDetailPanelCaret($wrap) {
    if (!$wrap || !$wrap.length) {
      return;
    }
    var $active = $wrap.find('.detail-tab.active').first();
    var $panel = $wrap.find('.detail-panel').first();
    var $caret = $panel.find('.detail-panel-caret').first();
    if (!$active.length || !$panel.length || !$caret.length) {
      return;
    }
    var wrapOffset = $wrap.offset();
    var tabOffset = $active.offset();
    if (!wrapOffset || !tabOffset) {
      return;
    }
    var left = tabOffset.left - wrapOffset.left + ($active.outerWidth() / 2);
    var minLeft = 18;
    var maxLeft = Math.max(minLeft, $panel.outerWidth() - 18);
    if (left < minLeft) left = minLeft;
    if (left > maxLeft) left = maxLeft;
    $caret.css('left', left + 'px');
  }

  function initDetailPanel($container) {
    if (window.drawTimeCourse && $container.find('.timeCourseShow').length > 0) {
      $container.find('.timeCourseShow').each(function() {
        drawTimeCourse($(this).attr('id'));
      });
    }
    $container.find('[data-toggle="popover"]').popover();
    var $wrap = $container.find('.detail-wrap').first();
    if ($wrap.length) {
      window.requestAnimationFrame(function() {
        updateDetailPanelCaret($wrap);
      });
    }
  }

  function renderStructureCharts(line) {
    if (!window.get_mordetail) {
      return;
    }
    window.requestAnimationFrame(function() {
      window.requestAnimationFrame(function() {
        get_mordetail(line);
      });
    });
  }

  function ensureStructureData($proPanel, lineId, done) {
    var $block = $proPanel.find('.sequence-properties-block').first();
    if (!$block.length) {
      if (typeof done === 'function') done();
      return;
    }
    if ($block.attr('data-structure-loaded') === '1') {
      if (typeof done === 'function') done();
      return;
    }
    if ($block.data('structureLoading')) {
      $block.data('structurePending', done);
      return;
    }
    var up = $block.attr('data-up') || '';
    var org = $block.attr('data-org') || '';
    if (!up) {
      if (typeof done === 'function') done();
      return;
    }
    $block.data('structureLoading', true);
    $.ajax({
      url: './resource/functions.php',
      method: 'POST',
      dataType: 'json',
      data: {
        type: 'detail_structure',
        uniprot: up,
        organism: org
      }
    }).done(function(data) {
      if (typeof data === 'string') {
        try {
          data = JSON.parse(data);
        } catch (e) {
          data = null;
        }
      }
      if (!data || typeof data !== 'object') {
        return;
      }
      var $data = $block.find('.data').first().empty();
      var fields = [
        ['sequence', 'sequence'],
        ['ptminfo', 'ptminfo'],
        ['disorder', 'disorder'],
        ['exposeburied', 'exposeburied'],
        ['polar', 'polar'],
        ['charge', 'charge'],
        ['secondstr', 'secondstr'],
        ['surface', 'surface'],
        ['hydropathy', 'hydropathy']
      ];
      fields.forEach(function(pair) {
        $('<input>', {
          type: 'hidden',
          id: pair[0] + '-' + lineId
        }).val(data[pair[1]] == null ? '' : String(data[pair[1]])).appendTo($data);
      });
      $block.attr('data-structure-loaded', '1');
    }).always(function() {
      $block.data('structureLoading', false);
      var pending = $block.data('structurePending');
      $block.removeData('structurePending');
      if (typeof done === 'function') done();
      if (typeof pending === 'function' && pending !== done) pending();
    });
  }

  function loadLazyDetailTable($lazy, done) {
    if (!$lazy || !$lazy.length) {
      if (typeof done === 'function') done(null);
      return;
    }
    if ($lazy.attr('data-loaded') === '1' || !$lazy.hasClass('lazy-detail-table')) {
      if (typeof done === 'function') done($lazy);
      return;
    }
    if ($lazy.data('loading')) {
      $lazy.data('pendingDone', done);
      return;
    }
    var kind = $lazy.attr('data-lazy') || '';
    var up = $lazy.attr('data-up') || '';
    var typeMap = { ptms: 'detail_ptms', ptmd: 'detail_ptmd' };
    var type = typeMap[kind];
    if (!type || !up) {
      if (typeof done === 'function') done($lazy);
      return;
    }
    $lazy.data('loading', true);
    $lazy.addClass('is-loading').html(
      '<div class="structure-viewer-loading detail-table-loading">'
      + '<span class="structure-spinner" aria-hidden="true"></span>'
      + '<span>Loading table...</span>'
      + '</div>'
    );
    $.ajax({
      url: './resource/functions.php',
      method: 'POST',
      dataType: 'html',
      data: { type: type, uniprot: up }
    }).done(function(html) {
      var $new = $('<div>').html(html).children().first();
      if (!$new.length) {
        // Response may be a bare "-" for empty tables.
        $lazy.removeClass('lazy-detail-table is-loading').attr('data-loaded', '1').html(html || '-');
        if (typeof done === 'function') done($lazy);
        return;
      }
      $new.attr('data-loaded', '1').removeClass('is-loading');
      $lazy.replaceWith($new);
      if (typeof done === 'function') done($new);
      var pending = $lazy.data('pendingDone');
      if (typeof pending === 'function' && pending !== done) pending($new);
    }).fail(function() {
      $lazy.removeClass('is-loading').html(
        '<div class="structure-viewer-error detail-table-loading">'
        + '<i class="ri-information-line" aria-hidden="true"></i>'
        + '<span>Failed to load table.</span>'
        + '</div>'
      );
      if (typeof done === 'function') done($lazy);
    }).always(function() {
      $lazy.data('loading', false);
    });
  }

  function prefetchLazyTables($panel) {
    if (!$panel || !$panel.length) {
      return;
    }
    $panel.find('.lazy-detail-table').each(function() {
      var $lazy = $(this);
      if ($lazy.attr('data-loaded') === '1' || $lazy.data('loading')) {
        return;
      }
      loadLazyDetailTable($lazy, function($new) {
        // Keep collapsed peek (hide-more) after prefetch.
        if ($new && $new.length) {
          $new.addClass('hide-more');
        }
      });
    });
  }

  function loadFilterOptionsAsync(mainQueryInfo, done) {
    if (!mainQueryInfo) {
      if (typeof done === 'function') {
        done();
      }
      return;
    }
    $.post('./resource/functions.php', {
      type: 'filteroptions',
      mainQueryInfo: mainQueryInfo,
      appliedFilters: JSON.stringify(collectAppliedFiltersMap())
    }, function(data) {
      if (data && !data.error) {
        populateFilterSelects(data);
      }
      if (typeof done === 'function') {
        done();
      }
    }, 'json').fail(function() {
      if (typeof done === 'function') {
        done();
      }
    });
  }

  function reloadFilterOptions(done) {
    loadFilterOptionsAsync($('#rawQueryInfo').text(), done);
  }

  function loadDetailContent($toggle) {
    var $detailRow = $toggle.closest('.Table-line').next('.Detail-line');
    var $cell = $detailRow.find('td').first();

    if ($cell.data('loaded')) {
      return;
    }

    var rawdata = $toggle.attr('value');
    $cell.html('<div class="detail-loading"><div class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></div>Loading detail...</div>');

    $.post('./resource/functions.php', { type: 'detail', rawdata: rawdata }, function(html, status) {
      if (status !== 'success') {
        $cell.removeData('loaded');
        $cell.html('<div class="status-msg status-error">Failed to load detail.</div>');
        return;
      }
      $cell.html(html);
      $cell.data('loaded', true);
      initDetailPanel($cell);
    }).fail(function() {
      $cell.removeData('loaded');
      $cell.html('<div class="status-msg status-error">Failed to load detail.</div>');
    });
  }

  function bindFilterEvents() {
    $(document).on('click', RESULT_ROOT + ' .rf-select-toggle', function(e) {
      e.stopPropagation();
      var $div = $(this).closest('.filter-div');
      var $select = $div.find('.rf-select');
      if (!$select.hasClass('is-open')) {
        openFilterPanel($div);
      } else {
        closeFilterPanels();
      }
    });

    $(document).on('click', RESULT_ROOT + ' .rf-option', function(e) {
      e.preventDefault();
      $(this).toggleClass('is-checked');
    });

    $(document).on('input', RESULT_ROOT + ' .rf-select-search input', function() {
      var keywords = $(this).val().toLowerCase();
      var $panel = $(this).closest('.rf-select-panel');
      $panel.find('.rf-option').each(function() {
        var text = $(this).find('.rf-option-label').text().toLowerCase();
        $(this).toggleClass('is-hidden', keywords !== '' && text.indexOf(keywords) === -1);
      });
    });

    $(document).on('click', RESULT_ROOT + ' .rf-apply-btn', function(e) {
      e.stopPropagation();
      applyFilterDropdown($(this).closest('.filter-div'));
    });

    $(document).on('click', RESULT_ROOT + ' .rf-clear-btn', function(e) {
      e.stopPropagation();
      clearFilterDropdown($(this).closest('.filter-div'));
    });

    $(document).on('click', function(e) {
      if (!$(e.target).closest(RESULT_ROOT + ' .rf-select').length) {
        closeFilterPanels();
      }
    });
  }

  function isCircleExpandIcon($icon) {
    return $icon.hasClass('ri-add-circle-fill') || $icon.hasClass('ri-indeterminate-circle-fill');
  }

  function setExpandIconOpen($icon, isOpen) {
    if (isCircleExpandIcon($icon)) {
      $icon.toggleClass('ri-add-circle-fill', !isOpen).toggleClass('ri-indeterminate-circle-fill', isOpen);
      return;
    }
    $icon.toggleClass('ri-arrow-down-circle-fill', !isOpen).toggleClass('ri-arrow-up-circle-fill', isOpen);
  }

  function isExpandIconOpen($icon) {
    if (isCircleExpandIcon($icon)) {
      return $icon.hasClass('ri-indeterminate-circle-fill');
    }
    return $icon.hasClass('ri-arrow-up-circle-fill');
  }

  function bindResultEvents() {
    bindFilterEvents();

    $('#filterButton').on('click', function() {
      $(RESULT_ROOT + ' .filter-div').each(function() {
        var $div = $(this);
        if ($div.find('.rf-select').hasClass('is-open')) {
          applyFilterDropdown($div, false);
        }
      });
      reloadFilterOptions(function() {
        changeResultTable(1);
      });
    });

    $('#filterClearButton').on('click', function() {
      $(RESULT_ROOT + ' .filter-div').each(function() {
        clearFilterDropdown($(this), false);
      });
      closeFilterPanels();
      reloadFilterOptions(function() {
        changeResultTable(1);
      });
    });

    $(document).on('change', RESULT_ROOT + ' #selectRowNumber', function() {
      changeResultTable(1);
    });

    $(document).on('click', RESULT_ROOT + ' .th-sort-indicator', function(e) {
      e.preventDefault();
      e.stopPropagation();
      var field = $(this).closest('th.th-sortable').data('sort');
      if (field) {
        handleSortClick(field);
      }
    });

    $('#download_button').on('click', function() {
      var $btn = $(this);
      var originalHtml = $btn.html();
      $btn.prop('disabled', true).html("<span class='typing-dots' aria-hidden='true'><span></span><span></span><span></span></span> waiting...");
      downloadResultTable();
      $btn.prop('disabled', false).html(originalHtml);
    });

    $(document).on('click', RESULT_ROOT + ' .page-item:not(.disabled):not(.active)', function() {
      var page = Number($(this).find('a').first().attr('value'));
      if (page) {
        changeResultTable(page);
      }
    });

    $(document).on('click', RESULT_ROOT + ' .col-detail .detail-toggle', function() {
      var $toggle = $(this);
      var $row = $toggle.closest('.Table-line');
      var $detailRow = $row.next('.Detail-line');
      var $icon = $toggle.find('i');

      if ($detailRow.is(':visible')) {
        $icon.removeClass('ri-indeterminate-circle-fill').addClass('ri-add-circle-fill');
        $toggle.removeClass('is-open');
        $row.removeClass('is-expanded');
        $detailRow.hide();
        return;
      }

      $icon.removeClass('ri-add-circle-fill').addClass('ri-indeterminate-circle-fill');
      $toggle.addClass('is-open');
      $row.addClass('is-expanded');
      $detailRow.show();
      loadDetailContent($toggle);
      window.requestAnimationFrame(function() {
        updateDetailPanelCaret($detailRow.find('.detail-wrap').first());
      });
    });

    $(document).on('click', RESULT_ROOT + ' .detail-wrap .detail-tab', function(e) {
      e.preventDefault();
      var clickBtn = $(this).attr('id');
      var $tabs = $(this).closest('.detail-tabs');
      var $wrap = $(this).closest('.detail-wrap');

      $tabs.find('.detail-tab').each(function() {
        var btnId = $(this).attr('id');
        if (btnId !== clickBtn) {
          $(this).removeClass('active');
          $('#div-' + btnId).hide();
        } else {
          $(this).addClass('active');
          $('#div-' + btnId).show();
        }
      });

      updateDetailPanelCaret($wrap);

      if (clickBtn.indexOf('pro-') === 0) {
        var lineId = clickBtn.split('-').slice(1).join('-');
        var $proPanel = $('#div-' + clickBtn);
        // Wait until the panel is visible and laid out, then render charts.
        window.setTimeout(function() {
          prefetchLazyTables($proPanel);
          ensureStructureData($proPanel, lineId, function() {
            renderStructureCharts(lineId);
          });
          if (window.initKnownLocalizations) {
            window.initKnownLocalizations($proPanel);
          }
          if (window.initProteinStructurePanels) {
            window.initProteinStructurePanels($proPanel);
          }
        }, 40);
      }

      if (clickBtn.indexOf('reg-') === 0) {
        prefetchLazyTables($('#div-' + clickBtn));
      }

      if (clickBtn.indexOf('enz-') === 0) {
        var $enzPanel = $('#div-' + clickBtn);
        loadEkpiQuantitative($enzPanel);
      }
    });

    function loadEkpiQuantitative($panel) {
      var $block = $panel.find('.ekpi-quant-block').first();
      if (!$block.length || $block.attr('data-loaded') === '1') {
        return;
      }
      var up = $block.attr('data-up') || '';
      var pos = $block.attr('data-pos') || '';
      if (!up || !pos) {
        return;
      }
      $block.attr('data-loaded', '1');
      var $status = $block.find('.ekpi-quant-status');
      var $wrap = $block.find('.ekpi-quant-table-wrap');
      $status.text('Loading inferred correlations…');
      var url = 'api/enzyme_ekpi.php?uniprot_ac=' + encodeURIComponent(up) + '&position=' + encodeURIComponent(pos) + '&limit=10';
      fetch(url, { credentials: 'same-origin' })
        .then(function(r) { return r.json(); })
        .then(function(data) {
          var rows = (data && data.correlations) ? data.correlations : [];
          var $note = $block.find('.ekpi-quant-note');
          if (!rows.length) {
            $status.text('-');
            $note.hide();
            return;
          }
          var html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'><tr>"
            + "<th>Kinase</th><th>Feature</th><th>Correlation (ρ)</th><th>P value</th><th>Cancer</th><th>PMID</th>"
            + "</tr></thead><tbody>";
          rows.forEach(function(row) {
            var pmid = row.pmid
              ? '<a href="https://pubmed.ncbi.nlm.nih.gov/' + row.pmid + '/" target="_blank" rel="noopener">' + row.pmid + '</a>'
              : '-';
            var cancer = row.cancer_type || '';
            if (row.n != null && row.n !== '') {
              cancer = cancer
                ? (cancer + ' (n=' + row.n + ')')
                : ('(n=' + row.n + ')');
            }
            if (!cancer) {
              cancer = '-';
            }
            html += '<tr>'
              + '<td>' + (row.kinase || '-') + '</td>'
              + '<td>' + (row.feature || '-') + '</td>'
              + '<td>' + (row.rho != null ? Number(row.rho).toFixed(3) : '-') + '</td>'
              + '<td>' + (row.pvalue != null ? Number(row.pvalue).toExponential(2) : '-') + '</td>'
              + '<td>' + cancer + '</td>'
              + '<td>' + pmid + '</td>'
              + '</tr>';
          });
          html += '</tbody></table></div>';
          $status.hide();
          $wrap.html(html);
          $note.show();
        })
        .catch(function() {
          $block.attr('data-loaded', '0');
          $status.text('Failed to load inferred evidence');
          $block.find('.ekpi-quant-note').hide();
        });
    }
    $(document).on('click', RESULT_ROOT + ' .detail-panel .show-table', function(e) {
      e.preventDefault();
      e.stopPropagation();
      var $btn = $(this);
      var $icon = $btn.find('i').length ? $btn.find('i') : $btn;
      var $rich = $btn.closest('tr').find('.detail-rich');
      var findTarget = function() {
        var $t = $rich.find('.detail-table-scroll').first();
        if (!$t.length) {
          $t = $rich.find('.seq-table').first();
        }
        if (!$t.length) {
          $t = $rich.children('.hide-table');
        }
        return $t;
      };
      var $target = findTarget();
      if (!isExpandIconOpen($icon)) {
        var $lazy = $rich.find('.lazy-detail-table').first();
        if ($lazy.length && $lazy.attr('data-loaded') !== '1') {
          setExpandIconOpen($icon, true);
          $btn.addClass('is-open');
          loadLazyDetailTable($lazy, function($new) {
            $target = $new && $new.length ? $new : findTarget();
            $target.removeClass('hide-more');
          });
          return;
        }
        setExpandIconOpen($icon, true);
        $target.removeClass('hide-more');
        $btn.addClass('is-open');
      } else {
        setExpandIconOpen($icon, false);
        $target.addClass('hide-more');
        $btn.removeClass('is-open');
      }
    });

    $(document).on('click', RESULT_ROOT + ' .detail-panel .show-text', function(e) {
      e.preventDefault();
      e.stopPropagation();
      var $btn = $(this);
      var $icon = $btn.find('i').length ? $btn.find('i') : $btn;
      if (!isExpandIconOpen($icon)) {
        setExpandIconOpen($icon, true);
        $btn.closest('tr').find('.hide-text').removeClass('text-less');
        $btn.addClass('is-open');
      } else {
        setExpandIconOpen($icon, false);
        $btn.closest('tr').find('.hide-text').addClass('text-less');
        $btn.removeClass('is-open');
      }
    });

    $(window).on('resize.detailCaret', function() {
      $(RESULT_ROOT + ' .detail-wrap:visible').each(function() {
        updateDetailPanelCaret($(this));
      });
    });
  }

  function initResultPage() {
    if (!$('#tableChange').length) {
      return;
    }

    bindResultEvents();
    updateSortIndicators();

    var params = new URLSearchParams(window.location.search);
    var searchInput = params.get('simple_search_input0') || '';

    if (!searchInput) {
      $('#pageInfo').text('No search keyword provided.');
      renderResultError('Please enter a keyword on the home page or advanced search page.');
      hidePagePreloader();
      return;
    }

    $('#pageInfo').text('Searching...');
    $('#tableChange').html('<tr><td colspan="10"><div class="status-msg"><div class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></div>Loading results...</div></td></tr>');

    $.ajax({
      url: './resource/functions.php',
      method: 'POST',
      data: collectSearchParams(),
      dataType: 'json',
      success: function(data) {
        if (data.error) {
          $('#pageInfo').text('Search failed');
          renderResultError(data.error);
          hidePagePreloader();
          return;
        }
        $('#rawQueryInfo').text(data.mainQueryInfo);
        lastQueryContent = data.queryContent || '';
        if (lastQueryContent) {
          renderQuerySummary();
        }
        changeResultTable(1);
        loadFilterOptionsAsync(data.mainQueryInfo);
      },
      error: function(jqXHR, textStatus) {
        $('#pageInfo').text('Search failed');
        renderResultError('Failed to build search query: ' + textStatus);
        hidePagePreloader();
      }
    });
  }

  $(document).ready(initResultPage);
})(jQuery);

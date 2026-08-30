(function($) {
  'use strict';

  var RESULT_ROOT = '#main';

  var FILTER_CONFIG = {
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
      return config.formatLabel ? config.formatLabel(value) : value;
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

  function applyFilterDropdown($div, refreshTable) {
    setAppliedValues($div, getPendingValues($div));
    updateFilterLabel($div);
    closeFilterPanels();
    if (refreshTable !== false) {
      changeResultTable(1);
    }
  }

  function clearFilterDropdown($div, refreshTable) {
    setAppliedValues($div, []);
    setPendingValues($div, []);
    updateFilterLabel($div);
    closeFilterPanels();
    if (refreshTable !== false) {
      changeResultTable(1);
    }
  }

  function populateFilterSelects(filterOptions) {
    var $row = $(RESULT_ROOT + ' .filter-dropdowns');
    $row.empty();

    Object.keys(FILTER_CONFIG).forEach(function(key) {
      var values = (filterOptions && filterOptions[key]) ? filterOptions[key] : [];
      if (!values.length) {
        return;
      }

      var config = FILTER_CONFIG[key];
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
        var label = config.formatLabel ? config.formatLabel(value) : value;
        html += '<button type="button" class="rf-option" data-value="' + escapeHtml(value) + '">';
        html += '<span class="rf-checkbox"><i class="ri-check-line"></i></span>';
        html += '<span class="rf-option-label">' + escapeHtml(label) + '</span>';
        html += '</button>';
      });
      html += '</div>';
      html += '<div class="rf-select-actions">';
      html += '<button type="button" class="btn btn-sm btn-primary rf-apply-btn">Apply</button>';
      html += '<button type="button" class="btn btn-sm rf-clear-btn">Clear</button>';
      html += '</div></div></div></div>';
      $row.append(html);
    });
  }

  var PAGE_SIZE_OPTIONS = [10, 20, 50];
  var lastQueryContent = '';
  var initialLoadPending = true;
  var sortState = { field: 'qptmscore', dir: 'desc' };

  function getOrderInfo() {
    if (!sortState.field) {
      return 'qptmscore desc, up, pos';
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
      '<tr><td colspan="11"><div class="status-msg status-error"><i class="ri-error-warning-line"></i> ' + message + '</div></td></tr>'
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

  function initDetailPanel($container) {
    if (window.drawTimeCourse && $container.find('.timeCourseShow').length > 0) {
      $container.find('.timeCourseShow').each(function() {
        drawTimeCourse($(this).attr('id'));
      });
    }
    $container.find('[data-toggle="popover"]').popover();
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

  function bindResultEvents() {
    bindFilterEvents();

    $('#filterButton').on('click', function() {
      $(RESULT_ROOT + ' .filter-div').each(function() {
        var $div = $(this);
        if ($div.find('.rf-select').hasClass('is-open')) {
          applyFilterDropdown($div, false);
        }
      });
      changeResultTable(1);
    });

    $('#filterClearButton').on('click', function() {
      $(RESULT_ROOT + ' .filter-div').each(function() {
        clearFilterDropdown($(this), false);
      });
      closeFilterPanels();
      changeResultTable(1);
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

    $(document).on('click', RESULT_ROOT + ' .detail-toggle', function() {
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
    });

    $(document).on('click', RESULT_ROOT + ' .detail-panel .detail-tab', function(e) {
      e.preventDefault();
      var clickBtn = $(this).attr('id');
      var $tabs = $(this).closest('.detail-tabs');

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

      if (clickBtn.indexOf('str-') === 0) {
        renderStructureCharts(clickBtn.split('-')[1]);
      }
    });

    $(document).on('click', RESULT_ROOT + ' .show-table', function(e) {
      e.preventDefault();
      var $btn = $(this);
      var $icon = $btn.find('i').length ? $btn.find('i') : $btn;
      var $target = $btn.closest('tr').find('.detail-rich').children('.detail-table-scroll, .hide-table');
      if ($icon.hasClass('ri-arrow-down-circle-fill')) {
        $icon.removeClass('ri-arrow-down-circle-fill').addClass('ri-arrow-up-circle-fill');
        $target.removeClass('hide-more');
        $btn.addClass('is-open');
      } else {
        $icon.removeClass('ri-arrow-up-circle-fill').addClass('ri-arrow-down-circle-fill');
        $target.addClass('hide-more');
        $btn.removeClass('is-open');
      }
    });

    $(document).on('click', RESULT_ROOT + ' .show-text', function() {
      var $icon = $(this).find('i').length ? $(this).find('i') : $(this);
      if ($icon.hasClass('ri-arrow-down-circle-fill')) {
        $icon.removeClass('ri-arrow-down-circle-fill').addClass('ri-arrow-up-circle-fill');
        $(this).closest('tr').find('.hide-text').removeClass('text-less');
        $(this).addClass('is-open');
      } else {
        $icon.removeClass('ri-arrow-up-circle-fill').addClass('ri-arrow-down-circle-fill');
        $(this).closest('tr').find('.hide-text').addClass('text-less');
        $(this).removeClass('is-open');
      }
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
    $('#tableChange').html('<tr><td colspan="11"><div class="status-msg"><div class="typing-dots" aria-hidden="true"><span></span><span></span><span></span></div>Loading results...</div></td></tr>');

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
        if (data.filterOptions) {
          populateFilterSelects(data.filterOptions);
        }
        changeResultTable(1);
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

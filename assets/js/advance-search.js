(function($) {
  'use strict';

  var TAG_OPTIONS = [
    { value: 'Context', label: 'Any Field' },
    { value: 'uniprotaccs', label: 'UniProt ID' },
    { value: 'uppos', label: 'UniProt ID#Position' },
    { value: 'genename', label: 'Gene Name' },
    { value: 'genepos', label: 'Gene Name#Position' },
    { value: 'proteinname', label: 'Protein Name' },
    { value: 'proteinpos', label: 'Protein Name#Position' },
    { value: 'pos', label: 'Position' },
    { value: 'func', label: 'Function' },
    { value: 'samdetail', label: 'Sample' },
    { value: 'con condetail', label: 'Condition' }
  ];

  var LINK_OPTIONS = [
    { value: 'and', label: 'AND' },
    { value: 'or', label: 'OR' },
    { value: 'and not', label: 'NOT' }
  ];

  var $drawer;

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function instantSelectHtml(name, id, options, selectedValue, extraClass) {
    var selected = selectedValue || (options[0] && options[0].value) || '';
    var selectedLabel = selected;
    options.forEach(function(opt) {
      if (String(opt.value) === String(selected)) {
        selectedLabel = opt.label;
      }
    });
    var html = '<div class="rf-select rf-select--instant' + (extraClass ? ' ' + extraClass : '') + '">';
    html += '<input type="hidden" name="' + name + '" id="' + id + '" value="' + escapeHtml(selected) + '">';
    html += '<button type="button" class="rf-select-toggle" aria-haspopup="listbox" aria-expanded="false">';
    html += '<span class="rf-select-label" title="' + escapeHtml(selectedLabel) + '">' + escapeHtml(selectedLabel) + '</span>';
    html += '<i class="ri-arrow-down-s-line rf-select-arrow"></i>';
    html += '</button>';
    html += '<div class="rf-select-panel"><div class="rf-select-options" role="listbox">';
    options.forEach(function(opt) {
      var checked = String(opt.value) === String(selected) ? ' is-checked' : '';
      html += '<button type="button" class="rf-option' + checked + '" data-value="' + escapeHtml(opt.value) + '" data-label="' + escapeHtml(opt.label) + '" title="' + escapeHtml(opt.label) + '">';
      html += '<span class="rf-checkbox"><i class="ri-check-line"></i></span>';
      html += '<span class="rf-option-label">' + escapeHtml(opt.label) + '</span>';
      html += '</button>';
    });
    html += '</div></div></div>';
    return html;
  }

  function tagSelectHtml(name, id, selected) {
    return instantSelectHtml(name, id, TAG_OPTIONS, selected || 'Context', 'adv-row-select');
  }

  function linkSelectHtml(name, id, selected) {
    return instantSelectHtml(name, id, LINK_OPTIONS, selected || 'and', 'adv-row-select adv-link-select');
  }

  function linkColumnHtml(index) {
    if (index === 0) {
      return '<div class="adv-search-link-col adv-search-link-col--empty" aria-hidden="true"></div>';
    }
    return '<div class="adv-search-link-col">' +
      linkSelectHtml('simple_search_link' + index, 'adv_simple_search_link' + index) +
      '</div>';
  }

  function buildSearchRow(index, isAddRow, rowData) {
    var tag = (rowData && rowData.tag) || 'Context';
    var link = (rowData && rowData.link) || 'and';
    var input = (rowData && rowData.input) || '';
    var row = '<div class="adv-search-row" data-row-index="' + index + '">';
    if (index === 0) {
      row += linkColumnHtml(0);
    } else {
      row += '<div class="adv-search-link-col">' +
        linkSelectHtml('simple_search_link' + index, 'adv_simple_search_link' + index, link) +
        '</div>';
    }
    row += '<div class="adv-search-tag-col">' + tagSelectHtml('simple_search_tag' + index, 'adv_simple_search_tag' + index, tag) + '</div>';
    row += '<div class="adv-search-input"><input class="form-control" type="text" name="simple_search_input' + index + '" id="adv_simple_search_input' + index + '" placeholder="" value="' + escapeHtml(input) + '"></div>';
    row += '<button type="button" class="adv-search-action ' + (isAddRow ? 'add' : 'remove') + '" aria-label="' + (isAddRow ? 'Add row' : 'Remove row') + '">';
    row += '<i class="' + (isAddRow ? 'ri-add-circle-fill' : 'ri-indeterminate-circle-fill') + '"></i>';
    row += '</button></div>';
    return row;
  }

  function getDefaultRows() {
    return [
      { index: 0, link: '', tag: 'Context', input: '' },
      { index: 1, link: 'and', tag: 'Context', input: '' }
    ];
  }

  function getRowValues() {
    var rows = [];
    $('#advance_search_rows .adv-search-row').each(function() {
      var index = $(this).data('row-index');
      rows.push({
        index: index,
        link: index > 0 ? $('#adv_simple_search_link' + index).val() : '',
        tag: $('#adv_simple_search_tag' + index).val(),
        input: $('#adv_simple_search_input' + index).val()
      });
    });
    return rows;
  }

  function renderRows(rows) {
    var html = '';
    rows.forEach(function(row, i) {
      html += buildSearchRow(i, i === 0, row);
    });
    $('#advance_search_rows').html(html);
  }

  function reindexRows() {
    renderRows(getRowValues());
  }

  function addSearchRow() {
    var rows = getRowValues();
    rows.push({ index: rows.length, link: 'and', tag: 'Context', input: '' });
    renderRows(rows);
  }

  function closeInstantPanels($root) {
    var $scope = $root && $root.length ? $root : $(document);
    $scope.find('.rf-select--instant').removeClass('is-open');
    $scope.find('.rf-select--instant .rf-select-toggle').attr('aria-expanded', 'false');
    if ($drawer && $drawer.length) {
      $drawer.find('.adv-search-drawer-body').removeClass('has-open-select');
    }
    $('.hero-search-box').removeClass('has-open-select');
  }

  function setInstantSelect($select, value) {
    var $input = $select.find('input[type="hidden"]').first();
    var $options = $select.find('.rf-option');
    var $match = $options.filter(function() {
      return String($(this).attr('data-value')) === String(value);
    });
    if (!$match.length) {
      $match = $options.first();
      value = $match.attr('data-value');
    }
    var label = $match.attr('data-label') || $match.find('.rf-option-label').text();
    $input.val(value);
    $options.removeClass('is-checked');
    $match.addClass('is-checked');
    $select.find('.rf-select-label').first().text(label).attr('title', label);
    $input.trigger('change');
  }

  function syncInstantOptionTitles($root) {
    ($root && $root.length ? $root : $(document)).find('.rf-select--instant .rf-option').each(function() {
      var label = $(this).attr('data-label') || $(this).find('.rf-option-label').text();
      $(this).attr('title', label);
    });
    ($root && $root.length ? $root : $(document)).find('.rf-select--instant').each(function() {
      var $select = $(this);
      var label = $select.find('.rf-option.is-checked').attr('data-label') || $select.find('.rf-select-label').first().text();
      $select.find('.rf-select-label').first().attr('title', label);
    });
  }

  function setInstantSelectById(inputId, value) {
    var $input = $('#' + inputId);
    var $select = $input.closest('.rf-select--instant');
    if ($select.length) {
      setInstantSelect($select, value);
    } else {
      $input.val(value);
    }
  }

  function syncFromSimpleSearch() {
    setInstantSelectById('adv_simple_search_tag0', $('#simple_search_tag0').val());
    $('#adv_simple_search_input0').val($('#simple_search_input0').val());
    var $org = $('#simple_search_org');
    var $mod = $('#simple_search_mod');
    setInstantSelectById('adv_simple_search_org', $org.length ? $org.val() : 'All');
    setInstantSelectById('adv_simple_search_mod', $mod.length ? $mod.val() : 'All');
  }

  function openAdvancedSearch() {
    closeInstantPanels();
    syncFromSimpleSearch();
    $('#adv-search-overlay, #adv-search-drawer').addClass('is-open');
    $('body').addClass('adv-search-open');
    if (window.location.hash !== '#advanced') {
      history.replaceState(null, '', '#advanced');
    }
  }

  function closeAdvancedSearch() {
    closeInstantPanels($drawer);
    $('#adv-search-overlay, #adv-search-drawer').removeClass('is-open');
    $('body').removeClass('adv-search-open');
    if (window.location.hash === '#advanced') {
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }

  function resetAdvancedSearch() {
    renderRows(getDefaultRows());
    setInstantSelectById('adv_simple_search_org', 'All');
    setInstantSelectById('adv_simple_search_mod', 'All');
  }

  function fillExample() {
    renderRows([
      { index: 0, link: '', tag: 'genepos', input: 'TP53#392' },
      { index: 1, link: 'and', tag: 'con condetail', input: 'Genistein' }
    ]);
    setInstantSelectById('adv_simple_search_org', 'Human');
    setInstantSelectById('adv_simple_search_mod', 'Phosphorylation');
  }

  function openInstantPanel($select) {
    var inDrawer = $drawer && $drawer.length && $.contains($drawer[0], $select[0]);
    closeInstantPanels(inDrawer ? $drawer : $(document));
    $select.addClass('is-open');
    $select.find('.rf-select-toggle').attr('aria-expanded', 'true');
    if (inDrawer) {
      $drawer.find('.adv-search-drawer-body').addClass('has-open-select');
    }
    if ($select.hasClass('hero-field-select')) {
      $select.closest('.hero-search-box').addClass('has-open-select');
    }
  }

  function bindInstantSelectEvents() {
    $(document).on('click', '.rf-select--instant .rf-select-toggle', function(e) {
      e.preventDefault();
      e.stopPropagation();
      var $select = $(this).closest('.rf-select--instant');
      if ($select.hasClass('is-open')) {
        closeInstantPanels($select.closest('#adv-search-drawer').length ? $drawer : $(document));
      } else {
        openInstantPanel($select);
      }
    });

    $(document).on('click', '.rf-select--instant .rf-option', function(e) {
      e.preventDefault();
      e.stopPropagation();
      var $opt = $(this);
      var $select = $opt.closest('.rf-select--instant');
      setInstantSelect($select, $opt.attr('data-value'));
      closeInstantPanels($select.closest('#adv-search-drawer').length ? $drawer : $(document));
    });

    $(document).on('click.instantRfSelect', function(e) {
      if ($(e.target).closest('.rf-select--instant').length) {
        return;
      }
      closeInstantPanels();
    });
  }

  $(document).ready(function() {
    bindInstantSelectEvents();
    syncInstantOptionTitles();

    if (!$('#advance_search_form').length) {
      return;
    }

    $drawer = $('#adv-search-drawer');
    renderRows(getDefaultRows());

    $('#open-advanced-search').on('click keydown', function(e) {
      if (e.type === 'keydown' && e.key !== 'Enter' && e.key !== ' ') {
        return;
      }
      e.preventDefault();
      openAdvancedSearch();
    });

    $('#adv-search-overlay, #adv-search-close').on('click', function() {
      closeAdvancedSearch();
    });

    $(document).on('keydown', function(e) {
      if (e.key !== 'Escape') {
        return;
      }
      if ($('.rf-select--instant.is-open').length) {
        closeInstantPanels();
        return;
      }
      if ($drawer && $drawer.hasClass('is-open')) {
        closeAdvancedSearch();
      }
    });

    $drawer.on('click', '.adv-search-action.add', function(e) {
      e.preventDefault();
      addSearchRow();
    });

    $drawer.on('click', '.adv-search-action.remove', function(e) {
      e.preventDefault();
      $(this).closest('.adv-search-row').remove();
      reindexRows();
    });

    $('#adv-search-example').on('click', fillExample);

    $('#advance_search_form').on('reset', function() {
      setTimeout(resetAdvancedSearch, 0);
    });

    if (window.location.hash === '#advanced') {
      openAdvancedSearch();
    }

    $(window).on('hashchange', function() {
      if (window.location.hash === '#advanced') {
        openAdvancedSearch();
      } else {
        closeAdvancedSearch();
      }
    });
  });

  window.openAdvancedSearch = openAdvancedSearch;
  window.closeAdvancedSearch = closeAdvancedSearch;
  window.setQptmInstantSelectById = setInstantSelectById;
})(jQuery);

(function($) {
  'use strict';

  var TAG_OPTIONS = [
    { value: 'Context', label: 'Any Field' },
    { value: 'uniprotaccs', label: 'UniProt ID' },
    { value: 'genename', label: 'Gene name' },
    { value: 'proteinname', label: 'Protein name' },
    { value: 'func', label: 'Function' },
    { value: 'samdetail', label: 'Sample' },
    { value: 'con condetail', label: 'Condition' }
  ];

  var $drawer;

  function tagSelectHtml(name, id) {
    var html = '<select class="form-control" name="' + name + '" id="' + id + '">';
    TAG_OPTIONS.forEach(function(opt) {
      html += '<option value="' + opt.value + '">' + opt.label + '</option>';
    });
    return html + '</select>';
  }

  function linkSelectHtml(name, id, selected) {
    var html = '<select class="form-control" name="' + name + '" id="' + id + '">';
    ['and', 'or', 'and not'].forEach(function(value) {
      var label = value === 'and not' ? 'NOT' : value.toUpperCase();
      var isSelected = value === (selected || 'and') ? ' selected' : '';
      html += '<option value="' + value + '"' + isSelected + '>' + label + '</option>';
    });
    return html + '</select>';
  }

  function linkColumnHtml(index) {
    if (index === 0) {
      return '<div class="adv-search-link-col adv-search-link-col--empty" aria-hidden="true"></div>';
    }
    return '<div class="adv-search-link-col">' +
      linkSelectHtml('simple_search_link' + index, 'adv_simple_search_link' + index) +
      '</div>';
  }

  function buildSearchRow(index, isAddRow) {
    var row = '<div class="adv-search-row" data-row-index="' + index + '">';
    row += linkColumnHtml(index);
    row += '<div class="adv-search-tag-col">' + tagSelectHtml('simple_search_tag' + index, 'adv_simple_search_tag' + index) + '</div>';
    row += '<div class="adv-search-input"><input class="form-control" type="text" name="simple_search_input' + index + '" id="adv_simple_search_input' + index + '" placeholder=""></div>';
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
      html += buildSearchRow(i, i === 0);
      if (i > 0) {
        // values filled after html insert
      }
    });
    $('#advance_search_rows').html(html);
    rows.forEach(function(row, i) {
      if (i > 0 && row.link) {
        $('#adv_simple_search_link' + i).val(row.link);
      }
      $('#adv_simple_search_tag' + i).val(row.tag);
      $('#adv_simple_search_input' + i).val(row.input);
    });
  }

  function reindexRows() {
    renderRows(getRowValues());
  }

  function addSearchRow() {
    var rows = getRowValues();
    rows.push({ index: rows.length, link: 'and', tag: 'Context', input: '' });
    renderRows(rows);
  }

  function syncFromSimpleSearch() {
    $('#adv_simple_search_tag0').val($('#simple_search_tag0').val());
    $('#adv_simple_search_input0').val($('#simple_search_input0').val());
    var $org = $('#simple_search_org');
    var $mod = $('#simple_search_mod');
    $('#adv_simple_search_org').val($org.length ? $org.val() : 'All');
    $('#adv_simple_search_mod').val($mod.length ? $mod.val() : 'All');
  }

  function openAdvancedSearch() {
    syncFromSimpleSearch();
    $('#adv-search-overlay, #adv-search-drawer').addClass('is-open');
    $('body').addClass('adv-search-open');
    if (window.location.hash !== '#advanced') {
      history.replaceState(null, '', '#advanced');
    }
  }

  function closeAdvancedSearch() {
    $('#adv-search-overlay, #adv-search-drawer').removeClass('is-open');
    $('body').removeClass('adv-search-open');
    if (window.location.hash === '#advanced') {
      history.replaceState(null, '', window.location.pathname + window.location.search);
    }
  }

  function resetAdvancedSearch() {
    renderRows(getDefaultRows());
    $('#adv_simple_search_org').val('All');
    $('#adv_simple_search_mod').val('All');
  }

  function fillExample() {
    renderRows([
      { index: 0, link: '', tag: 'genename', input: 'NPM1' },
      { index: 1, link: 'and', tag: 'samdetail', input: 'Hela' }
    ]);
    $('#adv_simple_search_org').val('Human');
    $('#adv_simple_search_mod').val('All');
  }

  $(document).ready(function() {
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
      if (e.key === 'Escape') {
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
})(jQuery);

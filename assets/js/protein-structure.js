(function(window, $) {
  'use strict';

  var PROXY_BASE = './resource/proxyStructure.php';
  var UNAVAILABLE_MSG = 'Sorry, 3D structure is unavailable for this protein.';
  var structureState = {};

  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function getLineState(lineId) {
    if (!structureState[lineId]) {
      structureState[lineId] = {
        viewer: null,
        blobUrl: null,
        loadTimer: null,
        loadSuccess: false,
        spinBound: false,
        lastArgs: null,
        renderPending: false
      };
    }
    return structureState[lineId];
  }

  function plotEl(lineId) {
    return document.getElementById('structure-box-plot-' + lineId);
  }

  function statusEl(lineId) {
    return document.getElementById('structure-viewer-status-' + lineId);
  }

  function isContainerVisible(lineId) {
    var box = plotEl(lineId);
    if (!box) return false;
    return box.offsetWidth > 0 && box.offsetHeight > 0;
  }

  function isValidStructureContent(data, format) {
    var text = String(data || '').trim();
    if (!text) return false;
    if (/^<!DOCTYPE/i.test(text) || /^<html/i.test(text)) return false;
    if (format === 'cif') {
      return text.indexOf('data_') === 0 || text.indexOf('_atom_site') !== -1;
    }
    return text.indexOf('HEADER') !== -1 || text.indexOf('ATOM') !== -1 || text.indexOf('HETATM') !== -1;
  }

  function destroyLineState(lineId) {
    var state = getLineState(lineId);
    if (state.loadTimer) {
      clearTimeout(state.loadTimer);
      state.loadTimer = null;
    }
    if (state.blobUrl) {
      URL.revokeObjectURL(state.blobUrl);
      state.blobUrl = null;
    }
    state.viewer = null;
    state.spinBound = false;
    state.loadSuccess = false;
  }

  function showStructureStatus(lineId, contentHtml) {
    var status = statusEl(lineId);
    var plot = plotEl(lineId);
    if (!status) return;
    if (plot) plot.innerHTML = '';
    destroyLineState(lineId);
    status.innerHTML = contentHtml;
    status.hidden = false;
  }

  function hideStructureStatus(lineId) {
    var status = statusEl(lineId);
    if (status) status.hidden = true;
  }

  function showStructureLoading(lineId) {
    showStructureStatus(lineId,
      '<div class="structure-viewer-loading"><span class="structure-spinner" aria-hidden="true"></span><span>Loading 3D structure...</span></div>'
    );
  }

  function showStructureError(lineId, message) {
    showStructureStatus(lineId,
      '<div class="structure-viewer-error"><i class="ri-information-line"></i><span>' + escapeHtml(message) + '</span></div>'
    );
  }

  function getStructureProxyMeta(pdbId, uniprotId) {
    if (pdbId === 'AlphaFold') {
      return {
        url: PROXY_BASE + '?source=alphafold&uniprot=' + encodeURIComponent(uniprotId),
        format: 'cif'
      };
    }
    if (pdbId === 'Local') {
      return {
        url: PROXY_BASE + '?source=local&uniprot=' + encodeURIComponent(uniprotId),
        format: 'pdb'
      };
    }
    return {
      url: PROXY_BASE + '?source=rcsb&pdb=' + encodeURIComponent(String(pdbId).toUpperCase()),
      format: 'pdb'
    };
  }

  function fetchProteinStructureData(pdbId, uniprotId) {
    var meta = getStructureProxyMeta(pdbId, uniprotId);
    return $.ajax({
      url: meta.url,
      type: 'GET',
      dataType: 'text',
      cache: false
    }).then(function(data, textStatus, jqXHR) {
      if (!jqXHR || jqXHR.status !== 200) return null;
      if (!isValidStructureContent(data, meta.format)) return null;
      return String(data);
    }, function() {
      return null;
    });
  }

  function fetchPdbIdsForUniprot(uniprotId) {
    return $.ajax({
      url: 'https://search.rcsb.org/rcsbsearch/v2/query',
      type: 'POST',
      contentType: 'application/json',
      data: JSON.stringify({
        query: {
          type: 'terminal',
          service: 'text',
          parameters: {
            attribute: 'rcsb_polymer_entity_container_identifiers.reference_sequence_identifiers.database_accession',
            operator: 'exact_match',
            value: uniprotId
          }
        },
        return_type: 'entry',
        request_options: {
          paginate: { start: 0, rows: 10 },
          sort: [{ sort_by: 'rcsb_entry_info.resolution_combined', direction: 'asc' }]
        }
      })
    }).then(function(data) {
      return (data.result_set || []).map(function(row) {
        return row.identifier.toLowerCase();
      });
    }, function() {
      return [];
    });
  }

  function buildStructureOptions(sitePos, blobUrl, format) {
    var options = {
      hideControls: true,
      visualStyle: 'cartoon',
      hideStructure: ['het', 'water'],
      landscape: true,
      sequencePanel: true,
      loadingOverlay: true,
      expanded: false,
      customData: {
        url: blobUrl,
        format: format,
        binary: false
      }
    };
    var pos = parseInt(sitePos, 10);
    if (!isNaN(pos) && pos > 0) {
      options.selection = {
        data: [{
          start_residue_number: pos,
          end_residue_number: pos,
          color: 'red'
        }],
        nonSelectedColor: '#ddccbb'
      };
    }
    return options;
  }

  function bindStructureEvents(lineId) {
    var state = getLineState(lineId);
    if (state.spinBound || !state.viewer || !state.viewer.events) return;
    state.spinBound = true;

    state.viewer.events.loadComplete.subscribe(function() {
      state.loadSuccess = true;
      hideStructureStatus(lineId);
      if (state.loadTimer) {
        clearTimeout(state.loadTimer);
        state.loadTimer = null;
      }
      var plot = plotEl(lineId);
      if (!plot || plot._spinBound) return;
      plot._spinBound = true;
      plot.addEventListener('mouseenter', function() {
        if (state.viewer && state.viewer.visual) {
          state.viewer.visual.toggleSpin(true);
        }
      });
    });

    if (state.viewer.events.loadError && state.viewer.events.loadError.subscribe) {
      state.viewer.events.loadError.subscribe(function() {
        showStructureError(lineId, UNAVAILABLE_MSG);
      });
    }
  }

  function drawStructureNow(lineId, pdbId, uniprotId, sitePos) {
    if (typeof PDBeMolstarPlugin === 'undefined') {
      showStructureError(lineId, 'Sorry, the 3D structure viewer failed to load.');
      return;
    }
    var container = plotEl(lineId);
    if (!container || !isContainerVisible(lineId)) return;

    showStructureLoading(lineId);

    fetchProteinStructureData(pdbId, uniprotId).then(function(data) {
      if (!data) {
        showStructureError(lineId, UNAVAILABLE_MSG);
        return;
      }

      var state = getLineState(lineId);
      var sourceMeta = getStructureProxyMeta(pdbId, uniprotId);
      if (state.blobUrl) {
        URL.revokeObjectURL(state.blobUrl);
      }
      state.blobUrl = URL.createObjectURL(new Blob([data], { type: 'text/plain' }));

      hideStructureStatus(lineId);
      container.innerHTML = '';
      state.viewer = new PDBeMolstarPlugin();
      state.spinBound = false;
      state.loadSuccess = false;

      try {
        state.viewer.render(
          container,
          buildStructureOptions(sitePos, state.blobUrl, sourceMeta.format)
        );
        bindStructureEvents(lineId);
        state.loadTimer = setTimeout(function() {
          if (!state.loadSuccess) {
            showStructureError(lineId, UNAVAILABLE_MSG);
          }
        }, 12000);
      } catch (err) {
        showStructureError(lineId, UNAVAILABLE_MSG);
      }
    });
  }

  function drawStructure(lineId, pdbId, uniprotId, sitePos) {
    var state = getLineState(lineId);
    state.lastArgs = { pdbId: pdbId, uniprotId: uniprotId, sitePos: sitePos };
    if (!isContainerVisible(lineId)) {
      state.renderPending = true;
      return;
    }
    state.renderPending = false;
    drawStructureNow(lineId, pdbId, uniprotId, sitePos);
  }

  function ensureMolstarAssets() {
    if (typeof PDBeMolstarPlugin !== 'undefined') {
      return $.Deferred().resolve().promise();
    }
    if (!window.__molstarAssetsPromise) {
      window.__molstarAssetsPromise = $.Deferred();
      if (!document.querySelector('link[data-molstar-css]')) {
        var link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = 'https://cdn.jsdelivr.net/npm/pdbe-molstar@3.2.0/build/pdbe-molstar.css';
        link.setAttribute('data-molstar-css', '1');
        document.head.appendChild(link);
      }
      var script = document.createElement('script');
      script.src = 'https://cdn.jsdelivr.net/npm/pdbe-molstar@3.2.0/build/pdbe-molstar-plugin.js';
      script.onload = function() { window.__molstarAssetsPromise.resolve(); };
      script.onerror = function() { window.__molstarAssetsPromise.reject(); };
      document.body.appendChild(script);
    }
    return window.__molstarAssetsPromise.promise();
  }

  function bootStructurePanel($panel) {
    var lineId = $panel.attr('data-line');
    var uniprot = $panel.attr('data-uniprot');
    var sitePos = $panel.attr('data-site-pos') || '';
    if (!lineId || !uniprot) return;

    ensureMolstarAssets().then(function() {
      fetchPdbIdsForUniprot(uniprot).then(function(pdbIds) {
        var $select = $('#pdb-select-' + lineId);
        $select.empty();
        pdbIds.forEach(function(id) {
          $select.append($('<option></option>').val(id).text(id));
        });
        $select.append($('<option></option>').val('Local').text('Local'));
        $select.append($('<option></option>').val('AlphaFold').text('AlphaFold'));

        var defaultPdb = pdbIds.length > 0 ? pdbIds[0] : 'AlphaFold';
        $select.val(defaultPdb);
        drawStructure(lineId, defaultPdb, uniprot, sitePos);

        $select.off('change.proteinStructure').on('change.proteinStructure', function() {
          drawStructure(lineId, $(this).val(), uniprot, sitePos);
        });
      });
    }).fail(function() {
      showStructureError(lineId, 'Sorry, the 3D structure viewer failed to load.');
    });
  }

  function initProteinStructurePanels($container) {
    var $scope = $container && $container.length ? $container : $(document);
    $scope.find('.protein-structure-panel').each(function() {
      var $panel = $(this);
      if ($panel.attr('data-rendered') === '1') {
        var lineId = $panel.attr('data-line');
        var state = lineId ? getLineState(lineId) : null;
        if (state && state.renderPending && state.lastArgs) {
          drawStructureNow(lineId, state.lastArgs.pdbId, state.lastArgs.uniprotId, state.lastArgs.sitePos);
        }
        return;
      }
      $panel.attr('data-rendered', '1');
      bootStructurePanel($panel);
    });
  }

  window.initProteinStructurePanels = initProteinStructurePanels;
})(window, jQuery);

<?php
/**
 * GET /api/stats
 *
 * Get database statistics: total events, sites, proteins, conditions,
 * broken down by organism and PTM type.
 */

require_once __DIR__ . '/db.php';

// ── Overall totals ────────────────────────────────────────────────
$totals = fetch_one(
    "SELECT
        (SELECT COUNT(*) FROM ptm_events) as total_events,
        (SELECT COUNT(*) FROM ptm_sites) as total_sites,
        (SELECT COUNT(*) FROM proteins) as total_proteins,
        (SELECT COUNT(*) FROM conditions) as total_conditions,
        (SELECT COUNT(*) FROM samples) as total_samples"
);

// ── By organism ───────────────────────────────────────────────────
$organismRows = fetch_all(
    "SELECT p.organism,
            COUNT(DISTINCT e.id) as events,
            COUNT(DISTINCT e.uniprot_ac) as proteins
     FROM ptm_events e
     JOIN proteins p ON e.uniprot_ac = p.uniprot_ac
     GROUP BY p.organism"
);

$byOrganism = [];
foreach ($organismRows as $row) {
    $byOrganism[$row['organism']] = [
        'events'   => intval($row['events']),
        'proteins' => intval($row['proteins']),
    ];
}

// ── By PTM type ───────────────────────────────────────────────────
$ptmRows = fetch_all(
    "SELECT ptm_type,
            COUNT(*) as events,
            COUNT(DISTINCT uniprot_ac) as proteins
     FROM ptm_events
     GROUP BY ptm_type"
);

$byPtmType = [];
foreach ($ptmRows as $row) {
    $byPtmType[$row['ptm_type']] = [
        'events'   => intval($row['events']),
        'proteins' => intval($row['proteins']),
    ];
}

json_response([
    'total_events'     => intval($totals['total_events'] ?? 0),
    'total_sites'      => intval($totals['total_sites'] ?? 0),
    'total_proteins'   => intval($totals['total_proteins'] ?? 0),
    'total_conditions' => intval($totals['total_conditions'] ?? 0),
    'total_samples'    => intval($totals['total_samples'] ?? 0),
    'by_organism'      => $byOrganism,
    'by_ptm_type'      => $byPtmType,
]);

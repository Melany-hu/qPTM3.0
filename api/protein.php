<?php
/**
 * GET /api/protein.php
 *
 * Protein info from protable + PTM sites aggregated from qevent.
 *
 * Path: /api/protein/{uniprot_ac}
 * Or query: uniprot_ac=
 */

require_once __DIR__ . '/db.php';

$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$parts = explode('/', trim($path, '/'));
$proteinIdx = array_search('protein', $parts);

$uniprot_ac = null;
if ($proteinIdx !== false && isset($parts[$proteinIdx + 1])
    && $parts[$proteinIdx + 1] !== 'protein.php') {
    $uniprot_ac = $parts[$proteinIdx + 1];
} else {
    $uniprot_ac = param('uniprot_ac');
}

if (!$uniprot_ac) {
    json_error('Path must be /api/protein/{uniprot_ac} (or pass uniprot_ac query param)');
}

$protein = fetch_one(
    'SELECT primaryacc, genename, proteinname, func, uniprotaccs
     FROM protable WHERE primaryacc = ?',
    [$uniprot_ac],
    's'
);

// Fallback: use any qevent row for this accession
$qe = fetch_one(
    'SELECT gene, org FROM qevent WHERE up = ? LIMIT 1',
    [$uniprot_ac],
    's'
);

if (!$protein && !$qe) {
    json_error("Protein not found: $uniprot_ac", 404);
}

$sites = fetch_all(
    'SELECT pos, mods,
            MAX(qptmscore) AS stars,
            COUNT(*) AS total_events,
            MIN(pep) AS pep
     FROM qevent
     WHERE up = ?
     GROUP BY pos, mods
     ORDER BY pos, mods',
    [$uniprot_ac],
    's'
);

$ptmSites = array_map(function ($row) {
    return [
        'position'         => intval($row['pos']),
        'ptm_type'         => strtolower($row['mods']),
        'stars'            => nullable_int($row['stars']),
        'total_events'     => intval($row['total_events']),
        'identified_count' => intval($row['total_events']),
        'in_dbptm'         => false,
        'in_psp'           => false,
        'site_fdr'         => null,
        'sequence_window'  => $row['pep'],
    ];
}, $sites);

json_response([
    'uniprot_ac'    => $uniprot_ac,
    'gene'          => $protein['genename'] ?? ($qe['gene'] ?? null),
    'protein_name'  => $protein['proteinname'] ?? null,
    'organism'      => $qe['org'] ?? null,
    'function_desc' => $protein['func'] ?? null,
    'sequence'      => null,
    'ptm_sites'     => $ptmSites,
]);

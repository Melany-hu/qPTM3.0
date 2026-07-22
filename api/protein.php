<?php
/**
 * GET /api/protein/{uniprot_ac}
 *
 * Get protein information including all PTM sites.
 *
 * Path parameters:
 *   uniprot_ac - UniProt accession (e.g., P04637)
 */

require_once __DIR__ . '/db.php';

// ── Parse path ────────────────────────────────────────────────────
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$parts = explode('/', trim($path, '/'));
$proteinIdx = array_search('protein', $parts);
if ($proteinIdx === false || !isset($parts[$proteinIdx + 1])) {
    json_error('Path must be /api/protein/{uniprot_ac}');
}
$uniprot_ac = $parts[$proteinIdx + 1];

// ── Protein info ──────────────────────────────────────────────────
$protein = fetch_one(
    "SELECT uniprot_ac, gene, protein_name, organism, function_desc, sequence
     FROM proteins WHERE uniprot_ac = ?",
    [$uniprot_ac],
    's'
);

if (!$protein) {
    json_error("Protein not found: $uniprot_ac", 404);
}

// ── PTM sites on this protein ─────────────────────────────────────
$sites = fetch_all(
    "SELECT position, ptm_type, stars, total_events,
            identified_count, in_dbptm, in_psp, site_fdr
     FROM ptm_sites
     WHERE uniprot_ac = ?
     ORDER BY position, ptm_type",
    [$uniprot_ac],
    's'
);

$ptmSites = array_map(function ($row) {
    return [
        'position'         => intval($row['position']),
        'ptm_type'         => $row['ptm_type'],
        'stars'            => $row['stars'] !== null ? intval($row['stars']) : null,
        'total_events'     => intval($row['total_events']),
        'identified_count' => intval($row['identified_count']),
        'in_dbptm'         => boolval($row['in_dbptm']),
        'in_psp'           => boolval($row['in_psp']),
        'site_fdr'         => $row['site_fdr'] !== null ? floatval($row['site_fdr']) : null,
    ];
}, $sites);

json_response([
    'uniprot_ac'    => $protein['uniprot_ac'],
    'gene'          => $protein['gene'],
    'protein_name'  => $protein['protein_name'],
    'organism'      => $protein['organism'],
    'function_desc' => $protein['function_desc'],
    'sequence'      => $protein['sequence'] ? substr($protein['sequence'], 0, 200) . '...' : null,
    'ptm_sites'     => $ptmSites,
]);

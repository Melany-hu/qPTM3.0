<?php
/**
 * GET /api/kinases/{uniprot_ac}/{position}
 *
 * Get kinases/enzymes associated with a specific PTM site.
 * Returns data from qPTM's integrated kinase-substrate relationships
 * and Deep-PLA predictions for acetylation.
 *
 * Path parameters:
 *   uniprot_ac - UniProt accession (e.g., P04637)
 *   position   - residue position (e.g., 15)
 */

require_once __DIR__ . '/db.php';

// ── Parse path ────────────────────────────────────────────────────
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$parts = explode('/', trim($path, '/'));
$kinaseIdx = array_search('kinases', $parts);
if ($kinaseIdx === false || !isset($parts[$kinaseIdx + 1]) || !isset($parts[$kinaseIdx + 2])) {
    json_error('Path must be /api/kinases/{uniprot_ac}/{position}');
}

$uniprot_ac = $parts[$kinaseIdx + 1];
$position = intval($parts[$kinaseIdx + 2]);

if (!$uniprot_ac || $position < 1) {
    json_error('Invalid uniprot_ac or position');
}

// ── Query kinase-substrate table ──────────────────────────────────
$rows = fetch_all(
    "SELECT kinase_gene, kinase_uniprot, evidence_type, source_db,
            inhibitor, ptm_type
     FROM kinase_substrate
     WHERE uniprot_ac = ? AND position = ?
     ORDER BY evidence_type, kinase_gene",
    [$uniprot_ac, $position],
    'si'
);

$kinases = array_map(function ($row) {
    return [
        'kinase_gene'   => $row['kinase_gene'],
        'kinase_uniprot'=> $row['kinase_uniprot'],
        'evidence_type' => $row['evidence_type'],
        'source_db'     => $row['source_db'],
        'inhibitor'     => $row['inhibitor'],
        'ptm_type'      => $row['ptm_type'],
    ];
}, $rows);

json_response([
    'uniprot_ac' => $uniprot_ac,
    'position'   => $position,
    'total'      => count($kinases),
    'kinases'    => $kinases,
]);

<?php
/**
 * GET /api/site/{uniprot_ac}/{position}
 *
 * Get all quantitative events for a specific PTM site.
 *
 * Path parameters:
 *   uniprot_ac - UniProt accession (e.g., P04637)
 *   position   - residue position (e.g., 15)
 *
 * Optional:
 *   ptm_type   - filter by PTM type
 */

require_once __DIR__ . '/db.php';

// ── Parse path ────────────────────────────────────────────────────
// Expected: /api/site/P04637/15
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$parts = explode('/', trim($path, '/'));

// Find "site" in path and take next two segments
$siteIdx = array_search('site', $parts);
if ($siteIdx === false || !isset($parts[$siteIdx + 1]) || !isset($parts[$siteIdx + 2])) {
    json_error('Path must be /api/site/{uniprot_ac}/{position}');
}

$uniprot_ac = $parts[$siteIdx + 1];
$position = intval($parts[$siteIdx + 2]);

if (!$uniprot_ac || $position < 1) {
    json_error('Invalid uniprot_ac or position');
}

$ptm_type = param('ptm_type', 'all');

// ── Site summary ──────────────────────────────────────────────────
$where = ["e.uniprot_ac = ?", "e.position = ?"];
$params = [$uniprot_ac, $position];
$types = 'si';

if ($ptm_type !== 'all' && isset($PTM_TYPE_MAP[$ptm_type])) {
    $where[] = "e.ptm_type = ?";
    $params[] = $PTM_TYPE_MAP[$ptm_type];
    $types .= 's';
}
$whereClause = implode(' AND ', $where);

$summarySql = "SELECT e.uniprot_ac, e.position, e.ptm_type,
                      MAX(e.stars) as stars,
                      COUNT(*) as total_events,
                      COUNT(DISTINCT e.condition_id) as total_conditions,
                      COUNT(DISTINCT e.sample_id) as total_samples,
                      e.sequence_window
    FROM ptm_events e
    WHERE $whereClause
    GROUP BY e.uniprot_ac, e.position, e.ptm_type, e.sequence_window";

$summaryRows = fetch_all($summarySql, $params, $types);

if (empty($summaryRows)) {
    json_response([
        'summary' => null,
        'events' => [],
        'message' => 'No PTM events found for this site',
    ]);
}

// ── Events ────────────────────────────────────────────────────────
$eventsSql = "SELECT e.pmid, e.uniprot_ac, e.gene, e.position, e.ptm_type,
                     e.sequence_window, s.sample_name as sample,
                     c.condition_name as `condition`, c.condition_abbr,
                     e.log2_ratio, e.p_value, e.stars, e.fdr_flag,
                     e.proteome_log2_ratio, e.proteome_p_value
    FROM ptm_events e
    LEFT JOIN samples s ON e.sample_id = s.id
    LEFT JOIN conditions c ON e.condition_id = c.id
    WHERE $whereClause
    ORDER BY e.ptm_type, c.condition_name, s.sample_name";

$eventRows = fetch_all($eventsSql, $params, $types);

$events = array_map(function ($row) {
    return [
        'pmid'           => $row['pmid'],
        'uniprot_ac'     => $row['uniprot_ac'],
        'gene'           => $row['gene'],
        'position'       => intval($row['position']),
        'ptm_type'       => $row['ptm_type'],
        'sequence_window'=> $row['sequence_window'],
        'sample'         => $row['sample'],
        'condition'      => $row['condition_abbr'] ?? $row['condition'],
        'log2_ratio'     => $row['log2_ratio'] !== null ? floatval($row['log2_ratio']) : null,
        'p_value'        => $row['p_value'] !== null ? floatval($row['p_value']) : null,
        'proteome_log2_ratio' => $row['proteome_log2_ratio'] !== null ? floatval($row['proteome_log2_ratio']) : null,
        'proteome_p_value'    => $row['proteome_p_value'] !== null ? floatval($row['proteome_p_value']) : null,
        'stars'          => $row['stars'] !== null ? intval($row['stars']) : null,
        'fdr_flag'       => boolval($row['fdr_flag']),
    ];
}, $eventRows);

// ── Format summaries ──────────────────────────────────────────────
$summaries = array_map(function ($row) {
    return [
        'uniprot_ac'       => $row['uniprot_ac'],
        'position'         => intval($row['position']),
        'ptm_type'         => $row['ptm_type'],
        'stars'            => $row['stars'] !== null ? intval($row['stars']) : null,
        'total_events'     => intval($row['total_events']),
        'total_conditions' => intval($row['total_conditions']),
        'total_samples'    => intval($row['total_samples']),
        'sequence_window'  => $row['sequence_window'],
    ];
}, $summaryRows);

json_response([
    'summaries' => $summaries,
    'events'    => $events,
]);

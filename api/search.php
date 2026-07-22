<?php
/**
 * GET /api/search
 *
 * Search qPTM PTM events by keyword.
 *
 * Parameters:
 *   q         - search keyword (required)
 *   field     - search field: any|gene|uniprot|protein|function|sample|condition (default: any)
 *   organism  - human|mouse|rat|yeast|all (default: all)
 *   ptm_type  - phosphorylation|acetylation|... (default: all)
 *   page      - page number (default: 1)
 *   per_page  - results per page, max 100 (default: 20)
 */

require_once __DIR__ . '/db.php';

// ── Parameters ────────────────────────────────────────────────────
$q = param('q');
if (!$q) {
    json_error('Parameter "q" is required');
}

$field    = param('field', 'any');
$organism = param('organism', 'all');
$ptm_type = param('ptm_type', 'all');
$page     = param_int('page', 1);
$per_page = min(param_int('per_page', 20), 100);
$offset   = ($page - 1) * $per_page;

// ── Build WHERE clauses ───────────────────────────────────────────
$where = [];
$params = [];
$types = '';

// Search field
$searchCol = match ($field) {
    'gene'      => 'e.gene',
    'uniprot'   => 'e.uniprot_ac',
    'protein'   => 'p.protein_name',
    'function'  => 'p.function_desc',
    'sample'    => 's.sample_name',
    'condition' => 'c.condition_name',
    default     => null, // "any" — search across multiple columns
};

if ($searchCol) {
    $where[] = "$searchCol LIKE ?";
    $params[] = "%$q%";
    $types .= 's';
} else {
    // "any" field: search across gene, uniprot_ac, protein_name, sample, condition
    $where[] = "(e.gene LIKE ? OR e.uniprot_ac LIKE ? OR p.protein_name LIKE ? OR s.sample_name LIKE ? OR c.condition_name LIKE ?)";
    $params[] = "%$q%";
    $params[] = "%$q%";
    $params[] = "%$q%";
    $params[] = "%$q%";
    $params[] = "%$q%";
    $types .= 'sssss';
}

// Organism filter
if ($organism !== 'all' && isset($ORGANISM_MAP[$organism])) {
    $where[] = "p.organism = ?";
    $params[] = $ORGANISM_MAP[$organism];
    $types .= 's';
}

// PTM type filter
if ($ptm_type !== 'all' && isset($PTM_TYPE_MAP[$ptm_type])) {
    $where[] = "e.ptm_type = ?";
    $params[] = $PTM_TYPE_MAP[$ptm_type];
    $types .= 's';
}

$whereClause = implode(' AND ', $where);

// ── Count total ───────────────────────────────────────────────────
$countSql = "SELECT COUNT(*) as total
    FROM ptm_events e
    LEFT JOIN proteins p ON e.uniprot_ac = p.uniprot_ac
    LEFT JOIN samples s ON e.sample_id = s.id
    LEFT JOIN conditions c ON e.condition_id = c.id
    WHERE $whereClause";

$countRow = fetch_one($countSql, $params, $types);
$total = intval($countRow['total'] ?? 0);

// ── Fetch page ────────────────────────────────────────────────────
$dataSql = "SELECT e.pmid, e.uniprot_ac, e.gene, e.position, e.ptm_type,
                   e.sequence_window, s.sample_name as sample,
                   c.condition_name as `condition`, c.condition_abbr,
                   e.log2_ratio, e.p_value, e.stars, e.fdr_flag
    FROM ptm_events e
    LEFT JOIN proteins p ON e.uniprot_ac = p.uniprot_ac
    LEFT JOIN samples s ON e.sample_id = s.id
    LEFT JOIN conditions c ON e.condition_id = c.id
    WHERE $whereClause
    ORDER BY e.gene, e.position, e.ptm_type
    LIMIT ? OFFSET ?";

$pageParams = array_merge($params, [$per_page, $offset]);
$pageTypes = $types . 'ii';

$rows = fetch_all($dataSql, $pageParams, $pageTypes);

// ── Format response ───────────────────────────────────────────────
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
        'stars'          => $row['stars'] !== null ? intval($row['stars']) : null,
        'fdr_flag'       => boolval($row['fdr_flag']),
    ];
}, $rows);

json_response([
    'total'    => $total,
    'page'     => $page,
    'per_page' => $per_page,
    'events'   => $events,
]);

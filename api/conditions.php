<?php
/**
 * GET /api/conditions
 *
 * Get distinct conditions where a site (or protein) was quantified.
 *
 * Parameters:
 *   uniprot_ac - UniProt accession (required)
 *   position   - residue position (optional; if omitted, returns conditions for all sites on the protein)
 *   ptm_type   - filter by PTM type (optional)
 */

require_once __DIR__ . '/db.php';

$uniprot_ac = param('uniprot_ac');
if (!$uniprot_ac) {
    json_error('Parameter "uniprot_ac" is required');
}

$position  = param('position');
$ptm_type  = param('ptm_type', 'all');

$where = ["e.uniprot_ac = ?"];
$params = [$uniprot_ac];
$types = 's';

if ($position) {
    $where[] = "e.position = ?";
    $params[] = intval($position);
    $types .= 'i';
}

if ($ptm_type !== 'all' && isset($PTM_TYPE_MAP[$ptm_type])) {
    $where[] = "e.ptm_type = ?";
    $params[] = $PTM_TYPE_MAP[$ptm_type];
    $types .= 's';
}

$whereClause = implode(' AND ', $where);

// ── Distinct conditions with event counts ─────────────────────────
$sql = "SELECT c.id, c.condition_name, c.condition_abbr, c.description,
               COUNT(*) as event_count,
               GROUP_CONCAT(DISTINCT s.sample_name) as samples,
               MIN(e.log2_ratio) as min_log2,
               MAX(e.log2_ratio) as max_log2,
               AVG(e.log2_ratio) as avg_log2
    FROM ptm_events e
    LEFT JOIN conditions c ON e.condition_id = c.id
    LEFT JOIN samples s ON e.sample_id = s.id
    WHERE $whereClause
    GROUP BY c.id, c.condition_name, c.condition_abbr, c.description
    ORDER BY event_count DESC";

$rows = fetch_all($sql, $params, $types);

$conditions = array_map(function ($row) {
    return [
        'condition_name' => $row['condition_name'],
        'condition_abbr' => $row['condition_abbr'],
        'description'    => $row['description'],
        'event_count'    => intval($row['event_count']),
        'samples'        => $row['samples'] ? explode(',', $row['samples']) : [],
        'log2_range'     => [
            'min' => $row['min_log2'] !== null ? floatval($row['min_log2']) : null,
            'max' => $row['max_log2'] !== null ? floatval($row['max_log2']) : null,
            'avg' => $row['avg_log2'] !== null ? floatval($row['avg_log2']) : null,
        ],
    ];
}, $rows);

json_response([
    'uniprot_ac' => $uniprot_ac,
    'position'   => $position ? intval($position) : null,
    'total_conditions' => count($conditions),
    'conditions' => $conditions,
]);

<?php
/**
 * GET /api/browse/{type}
 *
 * Browse genes, conditions, or samples alphabetically with event counts.
 *
 * Path parameters:
 *   type - gene|condition|sample
 *
 * Parameters:
 *   organism  - human|mouse|rat|yeast|all (default: all)
 *   ptm_type  - phosphorylation|acetylation|... (default: all)
 *   letter    - filter by initial letter (default: all)
 *   page      - page number (default: 1)
 *   per_page  - results per page, max 200 (default: 50)
 */

require_once __DIR__ . '/db.php';

// ── Parse path ────────────────────────────────────────────────────
$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$parts = explode('/', trim($path, '/'));
$browseIdx = array_search('browse', $parts);
if ($browseIdx === false || !isset($parts[$browseIdx + 1])) {
    json_error('Path must be /api/browse/{type}');
}

$type = $parts[$browseIdx + 1];
if (!in_array($type, ['gene', 'condition', 'sample'])) {
    json_error('Type must be: gene, condition, or sample');
}

$organism = param('organism', 'all');
$ptm_type = param('ptm_type', 'all');
$letter   = param('letter', 'all');
$page     = param_int('page', 1);
$per_page = min(param_int('per_page', 50), 200);
$offset   = ($page - 1) * $per_page;

// ── Build query based on browse type ──────────────────────────────
$where = [];
$params = [];
$types = '';

if ($organism !== 'all' && isset($ORGANISM_MAP[$organism])) {
    $where[] = "p.organism = ?";
    $params[] = $ORGANISM_MAP[$organism];
    $types .= 's';
}

if ($ptm_type !== 'all' && isset($PTM_TYPE_MAP[$ptm_type])) {
    $where[] = "e.ptm_type = ?";
    $params[] = $PTM_TYPE_MAP[$ptm_type];
    $types .= 's';
}

$whereClause = $where ? 'WHERE ' . implode(' AND ', $where) : '';

switch ($type) {
    case 'gene':
        $nameCol = 'e.gene';
        $groupBy = 'e.gene';
        $orderBy = 'e.gene';
        break;
    case 'condition':
        $nameCol = 'c.condition_name';
        $groupBy = 'c.condition_name';
        $orderBy = 'c.condition_name';
        break;
    case 'sample':
        $nameCol = 's.sample_name';
        $groupBy = 's.sample_name';
        $orderBy = 's.sample_name';
        break;
}

// Letter filter
if ($letter !== 'all' && strlen($letter) === 1) {
    $where[] = "$nameCol LIKE ?";
    $params[] = "$letter%";
    $types .= 's';
    $whereClause = 'WHERE ' . implode(' AND ', $where);
}

// ── Count ─────────────────────────────────────────────────────────
$joinClause = match ($type) {
    'gene' => "FROM ptm_events e LEFT JOIN proteins p ON e.uniprot_ac = p.uniprot_ac",
    'condition' => "FROM ptm_events e LEFT JOIN proteins p ON e.uniprot_ac = p.uniprot_ac LEFT JOIN conditions c ON e.condition_id = c.id",
    'sample' => "FROM ptm_events e LEFT JOIN proteins p ON e.uniprot_ac = p.uniprot_ac LEFT JOIN samples s ON e.sample_id = s.id",
};

$countSql = "SELECT COUNT(DISTINCT $nameCol) as total $joinClause $whereClause";
$countRow = fetch_one($countSql, $params, $types);
$total = intval($countRow['total'] ?? 0);

// ── Fetch ─────────────────────────────────────────────────────────
$dataSql = "SELECT $nameCol as name, COUNT(*) as event_count
    $joinClause $whereClause
    GROUP BY $groupBy
    ORDER BY $orderBy
    LIMIT ? OFFSET ?";

$pageParams = array_merge($params, [$per_page, $offset]);
$pageTypes = $types . 'ii';

$rows = fetch_all($dataSql, $pageParams, $pageTypes);

$items = array_map(function ($row) {
    return [
        'name'        => $row['name'],
        'event_count' => intval($row['event_count']),
    ];
}, $rows);

json_response([
    'type'     => $type,
    'total'    => $total,
    'page'     => $page,
    'per_page' => $per_page,
    'items'    => $items,
]);

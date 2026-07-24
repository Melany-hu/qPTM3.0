<?php
/**
 * GET /api/browse.php?type=gene|condition|sample
 * Also supports path /api/browse/{type}
 *
 * Prefer browsetable when available; fall back to distinct qevent values.
 */

require_once __DIR__ . '/db.php';

$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$parts = explode('/', trim($path, '/'));
$browseIdx = array_search('browse', $parts);

$type = null;
if ($browseIdx !== false && isset($parts[$browseIdx + 1])
    && $parts[$browseIdx + 1] !== 'browse.php') {
    $type = $parts[$browseIdx + 1];
} else {
    $type = param('type');
}

if (!in_array($type, ['gene', 'condition', 'sample'], true)) {
    json_error('Type must be: gene, condition, or sample (path /api/browse/{type} or ?type=)');
}

$organism = strtolower(param('organism', 'all'));
$ptm_type = strtolower(param('ptm_type', 'all'));
$letter   = param('letter', 'all');
$page     = param_int('page', 1);
$per_page = min(param_int('per_page', 50), 200);
$offset   = ($page - 1) * $per_page;

$where = ['b.btype = ?'];
$params = [$type];
$types = 's';

if ($organism !== 'all' && isset($ORGANISM_MAP[$organism])) {
    $where[] = 'b.org = ?';
    $params[] = $ORGANISM_MAP[$organism];
    $types .= 's';
}

if ($ptm_type !== 'all' && isset($PTM_TYPE_MAP[$ptm_type])) {
    $where[] = 'b.mods = ?';
    $params[] = $PTM_TYPE_MAP[$ptm_type];
    $types .= 's';
}

if ($letter !== 'all' && strlen($letter) === 1) {
    $where[] = 'b.fword = ?';
    $params[] = strtoupper($letter);
    $types .= 's';
}

$whereClause = implode(' AND ', $where);

// Try browsetable first
$countRow = fetch_one(
    "SELECT COUNT(DISTINCT b.cont) AS total FROM browsetable b WHERE $whereClause",
    $params,
    $types
);
$total = intval($countRow['total'] ?? 0);

if ($total > 0) {
    $rows = fetch_all(
        "SELECT b.cont AS name, COUNT(*) AS event_count
         FROM browsetable b
         WHERE $whereClause
         GROUP BY b.cont
         ORDER BY b.cont
         LIMIT ? OFFSET ?",
        array_merge($params, [$per_page, $offset]),
        $types . 'ii'
    );
} else {
    // Fallback: distinct values from qevent
    $colMap = [
        'gene'      => 'gene',
        'condition' => 'samplecondition',
        'sample'    => 'sample',
    ];
    $col = $colMap[$type];

    $qWhere = ["$col IS NOT NULL", "$col <> ''"];
    $qParams = [];
    $qTypes = '';

    if ($organism !== 'all' && isset($ORGANISM_MAP[$organism])) {
        $qWhere[] = 'org = ?';
        $qParams[] = $ORGANISM_MAP[$organism];
        $qTypes .= 's';
    }
    if ($ptm_type !== 'all' && isset($PTM_TYPE_MAP[$ptm_type])) {
        $qWhere[] = 'mods = ?';
        $qParams[] = $PTM_TYPE_MAP[$ptm_type];
        $qTypes .= 's';
    }
    if ($letter !== 'all' && strlen($letter) === 1) {
        $qWhere[] = "$col LIKE ?";
        $qParams[] = strtoupper($letter) . '%';
        $qTypes .= 's';
    }
    $qWhereClause = implode(' AND ', $qWhere);

    $countRow = fetch_one(
        "SELECT COUNT(DISTINCT $col) AS total FROM qevent WHERE $qWhereClause",
        $qParams,
        $qTypes
    );
    $total = intval($countRow['total'] ?? 0);

    $rows = fetch_all(
        "SELECT $col AS name, COUNT(*) AS event_count
         FROM qevent
         WHERE $qWhereClause
         GROUP BY $col
         ORDER BY $col
         LIMIT ? OFFSET ?",
        array_merge($qParams, [$per_page, $offset]),
        $qTypes . 'ii'
    );
}

$items = array_map(function ($row) {
    return [
        'name'        => trim($row['name']),
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

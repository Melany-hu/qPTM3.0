<?php
/**
 * GET /api/protein.php
 *
 * PTM modifications, sites, and experimental conditions for a protein (from qevent).
 * Not a UniProt annotation dump.
 *
 * Path: /api/protein/{uniprot_ac}
 * Or query: uniprot_ac=
 * Optional: position, ptm_type
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

$position = param('position');
$ptm_type = strtolower(param('ptm_type', 'all'));

$where = ['e.up = ?'];
$params = [$uniprot_ac];
$types = 's';

if ($position !== null && $position !== '') {
    $where[] = 'e.pos = ?';
    $params[] = (string)intval($position);
    $types .= 's';
}
if ($ptm_type !== 'all' && isset($PTM_TYPE_MAP[$ptm_type])) {
    $where[] = 'e.mods = ?';
    $params[] = $PTM_TYPE_MAP[$ptm_type];
    $types .= 's';
}
$whereClause = implode(' AND ', $where);

$identity = fetch_one(
    "SELECT e.gene, e.org, COUNT(*) AS total_events
     FROM qevent e
     WHERE $whereClause
     GROUP BY e.gene, e.org
     LIMIT 1",
    $params,
    $types
);

if (!$identity) {
    // Broader identity check without filters
    $any = fetch_one('SELECT gene, org FROM qevent WHERE up = ? LIMIT 1', [$uniprot_ac], 's');
    if (!$any) {
        json_error("Protein not found in qPTM: $uniprot_ac", 404);
    }
    $empty = [
        'uniprot_ac'       => $uniprot_ac,
        'gene'             => $any['gene'] ?? null,
        'organism'         => $any['org'] ?? null,
        'total_events'     => 0,
        'total_sites'      => 0,
        'total_conditions' => 0,
        'modifications'    => [],
        'ptm_sites'        => [],
        'conditions'       => [],
        'message'          => 'No quantitative events match the given filters',
    ];
    if ($position !== null && $position !== '') {
        $empty['position'] = intval($position);
    }
    if ($ptm_type !== 'all') {
        $empty['ptm_type'] = $ptm_type;
    }
    json_response($empty);
}

$siteRows = fetch_all(
    "SELECT e.pos, e.mods,
            MAX(e.qptmscore) AS stars,
            COUNT(*) AS total_events,
            COUNT(DISTINCT e.samplecondition) AS condition_count,
            COUNT(DISTINCT e.sample) AS sample_count
     FROM qevent e
     WHERE $whereClause
     GROUP BY e.pos, e.mods
     ORDER BY e.pos, e.mods",
    $params,
    $types
);

$ptmSites = [];
$modAgg = [];
$totalEvents = 0;
foreach ($siteRows as $row) {
    $mod = strtolower($row['mods']);
    $events = intval($row['total_events']);
    $totalEvents += $events;
    $ptmSites[] = [
        'position'         => intval($row['pos']),
        'ptm_type'         => $mod,
        'stars'            => nullable_int($row['stars']),
        'total_events'     => $events,
        'condition_count'  => intval($row['condition_count']),
        'sample_count'     => intval($row['sample_count']),
    ];
    if (!isset($modAgg[$mod])) {
        $modAgg[$mod] = ['ptm_type' => $mod, 'site_count' => 0, 'event_count' => 0];
    }
    $modAgg[$mod]['site_count']++;
    $modAgg[$mod]['event_count'] += $events;
}
$modifications = array_values($modAgg);
usort($modifications, function ($a, $b) {
    return $b['event_count'] <=> $a['event_count'];
});

$condRows = fetch_all(
    "SELECT e.samplecondition, e.sample, e.qratio
     FROM qevent e
     WHERE $whereClause
       AND e.samplecondition IS NOT NULL AND e.samplecondition <> ''",
    $params,
    $types
);
$conditions = aggregate_condition_stats($condRows, true);

$out = [
    'uniprot_ac'       => $uniprot_ac,
    'gene'             => $identity['gene'] ?? null,
    'organism'         => $identity['org'] ?? null,
    'total_events'     => $totalEvents,
    'total_sites'      => count($ptmSites),
    'total_conditions' => count($conditions),
    'modifications'    => $modifications,
    'ptm_sites'        => $ptmSites,
    'conditions'       => $conditions,
];
if ($position !== null && $position !== '') {
    $out['position'] = intval($position);
}
if ($ptm_type !== 'all') {
    $out['ptm_type'] = $ptm_type;
}
json_response($out);
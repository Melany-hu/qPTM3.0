<?php
/**
 * GET /api/conditions.php
 *
 * Search experimental conditions by name and/or condition type (contrast_type),
 * then return matching condition summaries plus their quantitative PTM events
 * from qevent (same event fields as /api/search).
 *
 * Parameters:
 *   q              - condition name / detail / agent / gene keyword (optional if contrast_type set)
 *   contrast_type  - pharmacological|genetic|physical|disease|cell_state|other (optional if q set)
 *   organism       - human|mouse|rat|yeast|all (default: all)
 *   ptm_type       - phosphorylation|...|all (default: all)
 *   page, per_page - event pagination (default 1 / 20, max 100)
 *
 * Note: site-level events are returned when the matched condition set is
 * reasonably small (≤50). Very broad contrast_type-only queries return the
 * condition catalog; add q to retrieve qevent rows.
 */

require_once __DIR__ . '/db.php';

$q = param('q', '');
$contrast_type = strtolower(param('contrast_type', ''));
$organism = strtolower(param('organism', 'all'));
$ptm_type = strtolower(param('ptm_type', 'all'));
$page = param_int('page', 1);
$per_page = min(param_int('per_page', 20), 100);
$offset = ($page - 1) * $per_page;

$allowedTypes = [
    'pharmacological' => true,
    'genetic'         => true,
    'physical'        => true,
    'disease'         => true,
    'cell_state'      => true,
    'other'           => true,
];

if ($q === '' && $contrast_type === '') {
    json_error('Provide q (condition name/keyword) and/or contrast_type');
}
if ($contrast_type !== '' && !isset($allowedTypes[$contrast_type])) {
    json_error('contrast_type must be one of: ' . implode(', ', array_keys($allowedTypes)));
}

$names = resolve_condition_names($q !== '' ? $q : null, $contrast_type !== '' ? $contrast_type : null, 2000);
sort($names, SORT_STRING | SORT_FLAG_CASE);
$matchedConditions = count($names);

$responseBase = [];
if ($q !== '') {
    $responseBase['q'] = $q;
}
if ($contrast_type !== '') {
    $responseBase['contrast_type'] = $contrast_type;
}
$responseBase['organism'] = $organism;
$responseBase['ptm_type'] = $ptm_type;

if ($matchedConditions === 0) {
    json_response(array_merge($responseBase, [
        'matched_conditions' => 0,
        'conditions'         => [],
        'total'              => 0,
        'page'               => $page,
        'per_page'           => $per_page,
        'events'             => [],
    ]));
}

$meta = load_condition_metadata($names);

// Broad catalog only (e.g. all pharmacological): avoid full-table qevent scans.
if ($matchedConditions > 50) {
    $conditions = [];
    foreach ($names as $name) {
        $m = $meta[$name] ?? [];
        $entry = ['condition_name' => $name];
        if (!empty($m['detail_condition'])) {
            $entry['detail_condition'] = $m['detail_condition'];
        }
        if (!empty($m['contrast_type'])) {
            $entry['contrast_type'] = $m['contrast_type'];
        }
        if (!empty($m['condition_factor'])) {
            $entry['condition_factor'] = $m['condition_factor'];
        }
        if (!empty($m['condition_perturbation'])) {
            $entry['condition_perturbation'] = $m['condition_perturbation'];
        }
        $conditions[] = $entry;
    }
    json_response(array_merge($responseBase, [
        'matched_conditions' => $matchedConditions,
        'conditions'         => $conditions,
        'total'              => 0,
        'page'               => $page,
        'per_page'           => $per_page,
        'events'             => [],
        'message'            => 'Too many matching conditions for site-level events; add q= to narrow (e.g. a drug or condition name)',
    ]));
}

$where = ['e.samplecondition IN (' . implode(',', array_fill(0, count($names), '?')) . ')'];
$params = $names;
$types = str_repeat('s', count($names));

if ($organism !== 'all' && isset($ORGANISM_MAP[$organism])) {
    $where[] = 'e.org = ?';
    $params[] = $ORGANISM_MAP[$organism];
    $types .= 's';
}
if ($ptm_type !== 'all' && isset($PTM_TYPE_MAP[$ptm_type])) {
    $where[] = 'e.mods = ?';
    $params[] = $PTM_TYPE_MAP[$ptm_type];
    $types .= 's';
}
$whereClause = implode(' AND ', $where);

$aggRows = fetch_all(
    "SELECT e.samplecondition AS name,
            COUNT(*) AS event_count,
            COUNT(DISTINCT e.sample) AS sample_count,
            MIN(e.qratio) AS log2_min,
            MAX(e.qratio) AS log2_max,
            AVG(e.qratio) AS log2_avg
     FROM qevent e
     WHERE $whereClause
     GROUP BY e.samplecondition
     ORDER BY event_count DESC, e.samplecondition",
    $params,
    $types
);
$byName = [];
foreach ($aggRows as $r) {
    $byName[$r['name']] = $r;
}

$samplesByName = [];
$sampleRows = fetch_all(
    "SELECT DISTINCT e.samplecondition AS name, e.sample
     FROM qevent e
     WHERE $whereClause
       AND e.sample IS NOT NULL AND e.sample <> ''
     ORDER BY e.samplecondition, e.sample",
    $params,
    $types
);
foreach ($sampleRows as $r) {
    $samplesByName[$r['name']][] = $r['sample'];
}

$conditions = [];
foreach ($names as $name) {
    $m = $meta[$name] ?? [];
    $a = $byName[$name] ?? null;
    $entry = [
        'condition_name' => $name,
        'event_count'    => $a ? intval($a['event_count']) : 0,
        'sample_count'   => $a ? intval($a['sample_count']) : 0,
        'log2_range'     => [
            'min' => $a ? nullable_float($a['log2_min']) : null,
            'max' => $a ? nullable_float($a['log2_max']) : null,
            'avg' => $a && $a['log2_avg'] !== null ? round((float)$a['log2_avg'], 4) : null,
        ],
    ];
    if (isset($samplesByName[$name])) {
        $entry['samples'] = $samplesByName[$name];
    }
    if (!empty($m['detail_condition'])) {
        $entry['detail_condition'] = $m['detail_condition'];
    }
    if (!empty($m['contrast_type'])) {
        $entry['contrast_type'] = $m['contrast_type'];
    }
    if (!empty($m['condition_factor'])) {
        $entry['condition_factor'] = $m['condition_factor'];
    }
    if (!empty($m['condition_perturbation'])) {
        $entry['condition_perturbation'] = $m['condition_perturbation'];
    }
    $conditions[] = $entry;
}
usort($conditions, function ($a, $b) {
    return $b['event_count'] <=> $a['event_count'];
});

$countRow = fetch_one(
    "SELECT COUNT(*) AS total FROM qevent e WHERE $whereClause",
    $params,
    $types
);
$totalEvents = intval($countRow['total'] ?? 0);

$events = [];
if ($totalEvents > 0) {
    $dataSql = event_select_page_sql($whereClause, 'e.qptmscore DESC, e.gene, e.pos');
    $rows = fetch_all(
        $dataSql,
        array_merge($params, [$per_page, $offset]),
        $types . 'ii'
    );
    $events = array_map('format_event_row', $rows);
}

json_response(array_merge($responseBase, [
    'matched_conditions' => $matchedConditions,
    'conditions'         => $conditions,
    'total'              => $totalEvents,
    'page'               => $page,
    'per_page'           => $per_page,
    'events'             => $events,
]));

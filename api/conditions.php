<?php
/**
 * GET /api/conditions.php
 *
 * Distinct experimental conditions for a UniProt site / protein (from qevent).
 *
 * Parameters:
 *   uniprot_ac - UniProt accession (required)
 *   position   - residue position (optional)
 *   ptm_type   - filter by PTM type (optional)
 */

require_once __DIR__ . '/db.php';

$uniprot_ac = param('uniprot_ac');
if (!$uniprot_ac) {
    json_error('Parameter "uniprot_ac" is required');
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

$where[] = "e.samplecondition IS NOT NULL AND e.samplecondition <> ''";
$whereClause = implode(' AND ', $where);

$rows = fetch_all(
    "SELECT e.samplecondition, e.sample, e.qratio
     FROM qevent e
     WHERE $whereClause",
    $params,
    $types
);

$grouped = [];
foreach ($rows as $row) {
    $name = $row['samplecondition'];
    if (!isset($grouped[$name])) {
        $grouped[$name] = [
            'condition_name' => $name,
            'condition_abbr' => $name,
            'description'    => null,
            'event_count'    => 0,
            'samples'        => [],
            'ratios'         => [],
        ];
    }
    $grouped[$name]['event_count']++;
    if (!empty($row['sample'])) {
        $grouped[$name]['samples'][$row['sample']] = true;
    }
    $f = nullable_float($row['qratio'] ?? null);
    if ($f !== null) {
        $grouped[$name]['ratios'][] = $f;
    }
}

$conditions = [];
foreach ($grouped as $g) {
    $vals = $g['ratios'];
    $conditions[] = [
        'condition_name' => $g['condition_name'],
        'condition_abbr' => $g['condition_abbr'],
        'description'    => null,
        'event_count'    => $g['event_count'],
        'samples'        => array_keys($g['samples']),
        'log2_range'     => [
            'min' => $vals ? min($vals) : null,
            'max' => $vals ? max($vals) : null,
            'avg' => $vals ? round(array_sum($vals) / count($vals), 4) : null,
        ],
    ];
}

usort($conditions, function ($a, $b) {
    return $b['event_count'] <=> $a['event_count'];
});

json_response([
    'uniprot_ac'       => $uniprot_ac,
    'position'         => ($position !== null && $position !== '') ? intval($position) : null,
    'total_conditions' => count($conditions),
    'conditions'       => $conditions,
]);

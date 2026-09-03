<?php
/**
 * GET /api/browse.php?type=condition|sample
 * Also supports path /api/browse/{type}
 *
 * Prefer browsetable when available; fall back to distinct qevent values.
 *
 * Shared filters: organism, ptm_type, page, per_page
 * Extra for type=condition:
 *   contrast_type = pharmacological|genetic|physical|disease|cell_state|other
 *   ontology      = condition ontology keyword (preferred name / ontology id / agent key / alias)
 *   agent_key     = exact agent_dictionary.agent_key (optional; ontology resolves to keys)
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

if (!in_array($type, ['condition', 'sample'], true)) {
    json_error('Type must be: condition or sample (path /api/browse/{type} or ?type=)');
}

$organism = strtolower(param('organism', 'all'));
$ptm_type = strtolower(param('ptm_type', 'all'));
$contrast_type = strtolower(trim((string)param('contrast_type', '')));
$agent_key = trim((string)param('agent_key', ''));
$ontology = trim((string)param('ontology', ''));
if ($ontology === '') {
    // Accept alias param names used in docs / Try it.
    $ontology = trim((string)param('agent', ''));
}
$page     = param_int('page', 1);
$per_page = min(param_int('per_page', 50), 200);
$offset   = ($page - 1) * $per_page;

$allowedTypes = [
    'pharmacological' => true,
    'genetic'         => true,
    'physical'        => true,
    'disease'         => true,
    'cell_state'      => true,
    'other'           => true,
];
if ($contrast_type !== '' && !isset($allowedTypes[$contrast_type])) {
    json_error('contrast_type must be one of: ' . implode(', ', array_keys($allowedTypes)));
}
if (($contrast_type !== '' || $ontology !== '' || $agent_key !== '') && $type !== 'condition') {
    json_error('contrast_type / ontology / agent_key are only valid when type=condition');
}

/** Resolve ontology keyword → agent_key list via agent_dictionary. */
function resolve_ontology_agent_keys(string $ontology, int $limit = 50): array {
    $ontology = trim($ontology);
    if ($ontology === '') {
        return [];
    }
    $like = '%' . $ontology . '%';
    $rows = fetch_all(
        'SELECT DISTINCT agent_key FROM agent_dictionary
         WHERE agent_key = ?
            OR preferred_name = ?
            OR ontology_id = ?
            OR agent_key LIKE ?
            OR preferred_name LIKE ?
            OR IFNULL(ontology_id, \'\') LIKE ?
            OR IFNULL(aliases, \'\') LIKE ?
         LIMIT ?',
        [$ontology, $ontology, $ontology, $like, $like, $like, $like, $limit],
        'sssssssi'
    );
    $keys = [];
    foreach ($rows as $r) {
        if (!empty($r['agent_key'])) {
            $keys[] = $r['agent_key'];
        }
    }
    // Also allow matching raw agent_key / gene on con_annotation when dictionary miss.
    if (empty($keys)) {
        $ann = fetch_all(
            'SELECT DISTINCT agent_key FROM con_annotation
             WHERE agent_key = ? OR agent_key LIKE ? OR IFNULL(agent_raw, \'\') LIKE ? OR IFNULL(gene, \'\') LIKE ?
             LIMIT ?',
            [$ontology, $like, $like, $like, $limit],
            'ssssi'
        );
        foreach ($ann as $r) {
            if (!empty($r['agent_key'])) {
                $keys[] = $r['agent_key'];
            }
        }
    }
    return array_values(array_unique($keys));
}

$agentKeys = [];
if ($agent_key !== '') {
    $agentKeys[] = $agent_key;
}
if ($ontology !== '') {
    $agentKeys = array_values(array_unique(array_merge($agentKeys, resolve_ontology_agent_keys($ontology))));
    if (empty($agentKeys)) {
        $empty = [
            'type'     => $type,
            'total'    => 0,
            'page'     => $page,
            'per_page' => $per_page,
            'items'    => [],
            'message'  => 'No condition ontology matches',
        ];
        if ($contrast_type !== '') {
            $empty['contrast_type'] = $contrast_type;
        }
        if ($ontology !== '') {
            $empty['ontology'] = $ontology;
        }
        if ($agent_key !== '') {
            $empty['agent_key'] = $agent_key;
        }
        json_response($empty);
    }
}

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

$useAnn = ($type === 'condition' && ($contrast_type !== '' || !empty($agentKeys)));
$joinSql = '';
if ($useAnn) {
    $joinSql = ' INNER JOIN con_annotation a ON a.con = b.cont ';
    if ($contrast_type !== '') {
        $where[] = 'a.contrast_type = ?';
        $params[] = $contrast_type;
        $types .= 's';
    }
    if (!empty($agentKeys)) {
        $where[] = 'a.agent_key IN (' . implode(',', array_fill(0, count($agentKeys), '?')) . ')';
        foreach ($agentKeys as $ak) {
            $params[] = $ak;
            $types .= 's';
        }
    }
}

$whereClause = implode(' AND ', $where);

$countRow = fetch_one(
    "SELECT COUNT(DISTINCT b.cont) AS total FROM browsetable b{$joinSql} WHERE $whereClause",
    $params,
    $types
);
$total = intval($countRow['total'] ?? 0);

if ($total > 0) {
    $rows = fetch_all(
        "SELECT b.cont AS name, COUNT(*) AS event_count
         FROM browsetable b{$joinSql}
         WHERE $whereClause
         GROUP BY b.cont
         ORDER BY b.cont
         LIMIT ? OFFSET ?",
        array_merge($params, [$per_page, $offset]),
        $types . 'ii'
    );
} else {
    $colMap = [
        'condition' => 'samplecondition',
        'sample'    => 'sample',
    ];
    $col = $colMap[$type];

    $qWhere = ["$col IS NOT NULL", "$col <> ''"];
    $qParams = [];
    $qTypes = '';
    $qJoin = '';

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
    if ($type === 'condition' && ($contrast_type !== '' || !empty($agentKeys))) {
        $qJoin = ' INNER JOIN con_annotation a ON a.con = qevent.samplecondition ';
        if ($contrast_type !== '') {
            $qWhere[] = 'a.contrast_type = ?';
            $qParams[] = $contrast_type;
            $qTypes .= 's';
        }
        if (!empty($agentKeys)) {
            $qWhere[] = 'a.agent_key IN (' . implode(',', array_fill(0, count($agentKeys), '?')) . ')';
            foreach ($agentKeys as $ak) {
                $qParams[] = $ak;
                $qTypes .= 's';
            }
        }
    }

    $qWhereClause = implode(' AND ', $qWhere);
    $countRow = fetch_one(
        "SELECT COUNT(DISTINCT $col) AS total FROM qevent{$qJoin} WHERE $qWhereClause",
        $qParams,
        $qTypes
    );
    $total = intval($countRow['total'] ?? 0);

    $rows = fetch_all(
        "SELECT $col AS name, COUNT(*) AS event_count
         FROM qevent{$qJoin}
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

// Enrich condition items with type / ontology metadata.
if ($type === 'condition' && !empty($items)) {
    $names = array_column($items, 'name');
    $meta = load_condition_metadata($names);
    // Also pull ontology_id from dictionary via agent_key on annotation.
    $placeholders = implode(',', array_fill(0, count($names), '?'));
    $annRows = fetch_all(
        "SELECT a.con, a.contrast_type, a.agent_key, a.perturbation, a.gene, a.agent_raw,
                d.preferred_name, d.ontology_id
         FROM con_annotation a
         LEFT JOIN agent_dictionary d ON d.agent_key = a.agent_key
         WHERE a.con IN ($placeholders)",
        $names,
        str_repeat('s', count($names))
    );
    $annByCon = [];
    foreach ($annRows as $r) {
        $con = $r['con'];
        if (!isset($annByCon[$con])) {
            $annByCon[$con] = $r;
        }
    }
    foreach ($items as &$item) {
        $name = $item['name'];
        $m = $meta[$name] ?? [];
        $a = $annByCon[$name] ?? [];
        $ct = $m['contrast_type'] ?? ($a['contrast_type'] ?? null);
        if ($ct !== null && $ct !== '') {
            $item['contrast_type'] = $ct;
        }
        $factor = $m['condition_factor'] ?? null;
        if ($factor === null || $factor === '') {
            $factor = api_text($a['preferred_name'] ?? null)
                ?: api_text($a['gene'] ?? null)
                ?: api_text($a['agent_raw'] ?? null);
        }
        if ($factor !== null && $factor !== '') {
            $item['condition_factor'] = $factor;
        }
        $pert = $m['condition_perturbation'] ?? ($a['perturbation'] ?? null);
        if ($pert !== null && $pert !== '') {
            $item['condition_perturbation'] = $pert;
        }
        if (!empty($a['agent_key'])) {
            $item['agent_key'] = $a['agent_key'];
        }
        if (!empty($a['ontology_id'])) {
            $item['ontology_id'] = $a['ontology_id'];
        }
    }
    unset($item);
}

$response = [
    'type'     => $type,
    'total'    => $total,
    'page'     => $page,
    'per_page' => $per_page,
    'items'    => $items,
];
if ($contrast_type !== '') {
    $response['contrast_type'] = $contrast_type;
}
if ($ontology !== '') {
    $response['ontology'] = $ontology;
}
if ($agent_key !== '') {
    $response['agent_key'] = $agent_key;
}
json_response($response);

<?php
/**
 * qPTM REST API — Shared database connection and JSON helpers.
 *
 * Connects to the live qPTM MySQL schema (qevent / protable / …).
 * Defaults match resource/functions.php; override via QPTM_DB_* env vars.
 */

// ── CORS Headers ──────────────────────────────────────────────────
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');
header('Content-Type: application/json; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// ── Database Configuration ────────────────────────────────────────
$DB_HOST = getenv('QPTM_DB_HOST') ?: 'localhost';
$DB_USER = getenv('QPTM_DB_USER') ?: 'cancerbi_web';
$DB_PASS = getenv('QPTM_DB_PASS') ?: 'web4lzx!';
$DB_NAME = getenv('QPTM_DB_NAME') ?: 'cancerbi_qptm2026';
$DB_PORT = intval(getenv('QPTM_DB_PORT') ?: '3306');

// URL-friendly names → live DB values (qevent.org / qevent.mods)
$PTM_TYPE_MAP = [
    'phosphorylation'         => 'Phosphorylation',
    'acetylation'             => 'Acetylation',
    'ubiquitylation'          => 'Ubiquitylation',
    'methylation'             => 'Methylation',
    'glycosylation'           => 'Glycosylation',
    'sumoylation'             => 'SUMOylation',
    'malonylation'            => 'Malonylation',
    'palmitoylation'          => 'Palmitoylation',
    'lactylation'             => 'Lactylation',
    'succinylation'           => 'Succinylation',
    'crotonylation'           => 'Crotonylation',
    'β-hydroxybutyrylation'   => 'β-Hydroxybutyrylation',
    'beta-hydroxybutyrylation'=> 'β-Hydroxybutyrylation',
];

$ORGANISM_MAP = [
    'human'  => 'Human',
    'mouse'  => 'Mouse',
    'rat'    => 'Rat',
    'yeast'  => 'Yeast',
];

// ── Database Connection ───────────────────────────────────────────
function db(): mysqli {
    global $DB_HOST, $DB_USER, $DB_PASS, $DB_NAME, $DB_PORT;
    static $conn = null;
    if ($conn === null) {
        $conn = new mysqli($DB_HOST, $DB_USER, $DB_PASS, $DB_NAME, $DB_PORT);
        if ($conn->connect_error) {
            json_error('Database connection failed: ' . $conn->connect_error, 500);
        }
        $conn->set_charset('utf8mb4');
    }
    return $conn;
}

// ── JSON Response Helpers ─────────────────────────────────────────
function json_response($data, int $status = 200): void {
    http_response_code($status);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

function json_error(string $message, int $status = 400): void {
    http_response_code($status);
    echo json_encode(['error' => $message], JSON_UNESCAPED_UNICODE);
    exit;
}

// ── Parameter Helpers ─────────────────────────────────────────────
function param(string $key, $default = null) {
    $val = $_GET[$key] ?? $default;
    return $val !== null ? trim((string)$val) : $default;
}

function param_int(string $key, int $default): int {
    $val = $_GET[$key] ?? null;
    if ($val === null) return $default;
    $int = intval($val);
    return $int > 0 ? $int : $default;
}

function nullable_float($val) {
    if ($val === null || $val === '' || $val === '-' || strcasecmp((string)$val, 'NA') === 0) {
        return null;
    }
    if (!is_numeric($val)) {
        return null;
    }
    return floatval($val);
}

function nullable_int($val) {
    if ($val === null || $val === '' || !is_numeric($val)) {
        return null;
    }
    return intval($val);
}

/** Clean free-text from DB for API JSON (mojibake / empty → null). */
function api_text($val) {
    if ($val === null) {
        return null;
    }
    $value = trim((string)$val);
    if ($value === '' || $value === '-') {
        return null;
    }
    if (strpos($value, 'Î') !== false || strpos($value, 'Â') !== false || strpos($value, 'Ã') !== false) {
        $latin1 = @mb_convert_encoding($value, 'ISO-8859-1', 'UTF-8');
        if ($latin1 !== false && $latin1 !== '' && mb_check_encoding($latin1, 'UTF-8')) {
            $still = (strpos($latin1, 'Î') !== false && substr_count($latin1, 'Î') >= substr_count($value, 'Î'));
            if (!$still || preg_match('/\p{Greek}/u', $latin1)) {
                $value = $latin1;
            }
        }
    }
    return $value;
}

/** Map a qevent row (optionally joined with Experimental information tables) to API JSON. */
function format_event_row(array $row): array {
    $fdr = $row['fdr'] ?? null;
    $fdrFlag = false;
    if ($fdr !== null && $fdr !== '' && $fdr !== '-' && $fdr !== '0') {
        $fdrFlag = true;
    }

    $timetype = $row['timetype'] ?? null;
    $hasTimeCourse = ($timetype !== null && $timetype !== '' && (string)$timetype !== '0');

    $conditionType = api_text($row['contrast_type'] ?? null);
    $conditionPerturbation = api_text($row['perturbation'] ?? null);

    $conditionFactor = api_text($row['agent_preferred_name'] ?? null);
    if ($conditionFactor === null) {
        $conditionFactor = api_text($row['ann_gene'] ?? null);
    }
    if ($conditionFactor === null) {
        $conditionFactor = api_text($row['agent_raw'] ?? null);
    }

    $ontologyId = api_text($row['ontology_id'] ?? null);

    $prob = api_text($row['prob'] ?? null);
    if ($prob !== null) {
        $prob = str_replace('#', ': ', $prob);
    }

    $flag_or_null = function ($v) {
        if ($v === null || $v === '') {
            return null;
        }
        $s = strtolower(trim((string)$v));
        if ($s === 'yes' || $s === 'y' || $s === '1' || $s === 'true') {
            return true;
        }
        if ($s === 'no' || $s === 'n' || $s === '0' || $s === 'false') {
            return false;
        }
        return (string)$v;
    };

    return [
        'pmid'                => $row['pmid'] ?? null,
        'uniprot_ac'          => $row['up'] ?? null,
        'gene'                => $row['gene'] ?? null,
        'position'            => nullable_int($row['pos'] ?? null),
        'ptm_type'            => isset($row['mods']) ? strtolower($row['mods']) : null,
        'sample'              => api_text($row['sample'] ?? null),
        'sample_type'         => api_text($row['samtype'] ?? null),
        'condition'           => api_text($row['samplecondition'] ?? null),
        'detail_condition'    => api_text($row['condetail'] ?? null),
        'condition_type'      => $conditionType,
        'condition_perturbation' => $conditionPerturbation,
        'condition_factor'    => $conditionFactor,
        'condition_ontology_id' => $ontologyId,
        'organism'            => $row['org'] ?? null,
        'resource_title'      => api_text($row['exp_title'] ?? null),
        'label_method'        => api_text($row['labelmethod'] ?? null),
        'enrichment_method'   => api_text($row['enrichmethod'] ?? null),
        'mass_spectrometer'   => api_text($row['msmethod'] ?? null),
        'log2_ratio'          => nullable_float($row['qratio'] ?? null),
        'p_value'             => nullable_float($row['pvalue'] ?? null),
        'proteome_log2_ratio' => nullable_float($row['qratiopro'] ?? null),
        'proteome_p_value'    => nullable_float($row['pvaluepro'] ?? null),
        'has_time_course'     => $hasTimeCourse,
        'reported_pep_localization_prob' => $prob,
        'stars'               => nullable_int($row['qptmscore'] ?? null),
        'fdr_flag'            => $fdrFlag,
        'fdr'                 => $fdr,
        'qptm_count'          => nullable_int($row['qptmcount'] ?? null),
        'in_psp'              => $flag_or_null($row['ispsp'] ?? null),
        'in_dbptm'            => $flag_or_null($row['isdbptm'] ?? null),
        'in_ptmatlas'         => $flag_or_null($row['isptmatlas'] ?? null),
    ];
}

/** Core qevent columns used by event APIs (no sequence window / pep). */
function event_qevent_columns(): string {
    return 'e.pmid, e.up, e.gene, e.pos, e.mods, e.sample,
            e.samplecondition, e.org, e.qratio, e.pvalue,
            e.qratiopro, e.pvaluepro, e.qptmscore, e.fdr,
            e.timetype, e.qptmcount';
}

/**
 * Shared SELECT with Experiment information joins.
 * Pass a FROM clause; default is qevent. For large filters, pass a limited
 * subquery aliased as `e` so joins run only on the page rows.
 */
function event_select_sql(string $fromClause = 'qevent e'): string {
    return 'SELECT ' . event_qevent_columns() . ',
                   x.tit AS exp_title, x.labelmethod, x.enrichmethod, x.msmethod,
                   c.condetail,
                   s.samtype,
                   sc.prob, sc.ispsp, sc.isdbptm, sc.isptmatlas,
                   a.contrast_type, a.perturbation, a.agent_key, a.agent_raw,
                   a.gene AS ann_gene,
                   d.preferred_name AS agent_preferred_name, d.ontology_id
            FROM ' . $fromClause . '
            LEFT JOIN exptable x ON x.pmid = e.pmid AND x.mods = e.mods
            LEFT JOIN contable c ON c.pmid = e.pmid AND c.con = e.samplecondition
            LEFT JOIN samtable s ON s.sam = e.sample
            LEFT JOIN scoretable sc ON sc.scoreid = CONCAT(e.org, \'#\', e.pmid, \'#\', e.up, \'#\', e.pos, \'#\', e.mods)
            LEFT JOIN con_annotation a ON a.pmid = e.pmid AND a.con = e.samplecondition
            LEFT JOIN agent_dictionary d ON d.agent_key = a.agent_key';
}

/**
 * Page qevent first (LIMIT/OFFSET), then attach Experimental information joins.
 * Avoids joining scoretable/exptable against huge intermediate result sets.
 */
function event_select_page_sql(string $whereClause, string $orderBy): string {
    $inner = 'SELECT ' . event_qevent_columns() . '
              FROM qevent e
              WHERE ' . $whereClause . '
              ORDER BY ' . $orderBy . '
              LIMIT ? OFFSET ?';
    return event_select_sql('(' . $inner . ') e');
}

// ── Query Helper ──────────────────────────────────────────────────
function query(string $sql, array $params = [], string $types = ''): mysqli_result {
    $conn = db();
    if (empty($params)) {
        $result = $conn->query($sql);
        if ($result === false) {
            json_error('Query failed: ' . $conn->error, 500);
        }
        return $result;
    }
    $stmt = $conn->prepare($sql);
    if ($stmt === false) {
        json_error('Prepare failed: ' . $conn->error, 500);
    }
    if (!empty($types)) {
        $stmt->bind_param($types, ...$params);
    }
    if (!$stmt->execute()) {
        json_error('Query execution failed: ' . $stmt->error, 500);
    }
    $result = $stmt->get_result();
    if ($result === false) {
        json_error('Query execution failed: ' . $stmt->error, 500);
    }
    return $result;
}

function fetch_all(string $sql, array $params = [], string $types = ''): array {
    $result = query($sql, $params, $types);
    $rows = [];
    while ($row = $result->fetch_assoc()) {
        $rows[] = $row;
    }
    return $rows;
}

function fetch_one(string $sql, array $params = [], string $types = ''): ?array {
    $result = query($sql, $params, $types);
    $row = $result->fetch_assoc();
    return $row ?: null;
}

/**
 * Aggregate condition stats from qevent rows that include samplecondition, sample, qratio.
 * Optionally enrich with con_annotation / contable metadata for the given names.
 */
function aggregate_condition_stats(array $rows, bool $enrich = true): array {
    $grouped = [];
    foreach ($rows as $row) {
        $name = trim((string)($row['samplecondition'] ?? ''));
        if ($name === '') {
            continue;
        }
        if (!isset($grouped[$name])) {
            $grouped[$name] = [
                'condition_name' => $name,
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

    $meta = [];
    if ($enrich && !empty($grouped)) {
        $meta = load_condition_metadata(array_keys($grouped));
    }

    $conditions = [];
    foreach ($grouped as $name => $g) {
        $vals = $g['ratios'];
        $m = $meta[$name] ?? [];
        $conditions[] = [
            'condition_name'         => $name,
            'detail_condition'       => $m['detail_condition'] ?? null,
            'contrast_type'          => $m['contrast_type'] ?? null,
            'condition_factor'       => $m['condition_factor'] ?? null,
            'condition_perturbation' => $m['condition_perturbation'] ?? null,
            'event_count'            => $g['event_count'],
            'samples'                => array_keys($g['samples']),
            'log2_range'             => [
                'min' => $vals ? min($vals) : null,
                'max' => $vals ? max($vals) : null,
                'avg' => $vals ? round(array_sum($vals) / count($vals), 4) : null,
            ],
        ];
    }

    usort($conditions, function ($a, $b) {
        return $b['event_count'] <=> $a['event_count'];
    });
    return $conditions;
}

/** Load annotation/detail metadata for a list of condition names (capped). */
function load_condition_metadata(array $names): array {
    $names = array_values(array_unique(array_filter(array_map('strval', $names))));
    if (empty($names)) {
        return [];
    }
    if (count($names) > 500) {
        $names = array_slice($names, 0, 500);
    }
    $placeholders = implode(',', array_fill(0, count($names), '?'));
    $types = str_repeat('s', count($names));

    $meta = [];
    $conRows = fetch_all(
        "SELECT con, condetail FROM contable WHERE con IN ($placeholders)",
        $names,
        $types
    );
    foreach ($conRows as $r) {
        $con = $r['con'];
        if (!isset($meta[$con])) {
            $meta[$con] = [];
        }
        if (!empty($r['condetail'])) {
            $meta[$con]['detail_condition'] = api_text($r['condetail']);
        }
    }

    $annRows = fetch_all(
        "SELECT a.con, a.contrast_type, a.perturbation, a.agent_raw, a.agent_key, a.gene,
                a.condetail, d.preferred_name
         FROM con_annotation a
         LEFT JOIN agent_dictionary d ON d.agent_key = a.agent_key
         WHERE a.con IN ($placeholders)",
        $names,
        $types
    );
    foreach ($annRows as $r) {
        $con = $r['con'];
        if (!isset($meta[$con])) {
            $meta[$con] = [];
        }
        if (empty($meta[$con]['detail_condition']) && !empty($r['condetail'])) {
            $meta[$con]['detail_condition'] = api_text($r['condetail']);
        }
        if (!empty($r['contrast_type'])) {
            $meta[$con]['contrast_type'] = $r['contrast_type'];
        }
        if (!empty($r['perturbation'])) {
            $meta[$con]['condition_perturbation'] = $r['perturbation'];
        }
        $factor = api_text($r['preferred_name'] ?? null)
            ?: api_text($r['gene'] ?? null)
            ?: api_text($r['agent_raw'] ?? null);
        if ($factor !== null) {
            $meta[$con]['condition_factor'] = $factor;
        }
    }
    return $meta;
}

/** Resolve condition names matching q / contrast_type from small lookup tables. */
function resolve_condition_names(?string $q, ?string $contrast_type, int $limit = 200): array {
    $q = $q !== null ? trim($q) : '';
    $contrast_type = $contrast_type !== null ? trim(strtolower($contrast_type)) : '';
    $names = [];

    if ($contrast_type !== '') {
        $rows = fetch_all(
            'SELECT DISTINCT con FROM con_annotation WHERE contrast_type = ? LIMIT ?',
            [$contrast_type, $limit],
            'si'
        );
        foreach ($rows as $r) {
            if (!empty($r['con'])) {
                $names[] = $r['con'];
            }
        }
    }

    if ($q !== '') {
        $like = '%' . $q . '%';
        $rows = fetch_all(
            'SELECT DISTINCT con FROM contable
             WHERE con = ? OR con LIKE ? OR con LIKE ? OR IFNULL(condetail, \'\') LIKE ?
             LIMIT ?',
            [$q, $q . '%', $like, $like, $limit],
            'ssssi'
        );
        foreach ($rows as $r) {
            if (!empty($r['con'])) {
                $names[] = $r['con'];
            }
        }
        $rows = fetch_all(
            'SELECT DISTINCT con FROM con_annotation
             WHERE con = ? OR con LIKE ? OR con LIKE ?
                OR IFNULL(condetail, \'\') LIKE ?
                OR IFNULL(agent_raw, \'\') LIKE ?
                OR IFNULL(agent_key, \'\') LIKE ?
                OR IFNULL(gene, \'\') LIKE ?
                OR IFNULL(contrast_type, \'\') LIKE ?
             LIMIT ?',
            [$q, $q . '%', $like, $like, $like, $like, $like, $like, $limit],
            'ssssssssi'
        );
        foreach ($rows as $r) {
            if (!empty($r['con'])) {
                $names[] = $r['con'];
            }
        }
    }

    $names = array_values(array_unique($names));
    if ($q !== '' && $contrast_type !== '') {
        // Intersection when both filters are set
        $byType = [];
        $typeRows = fetch_all(
            'SELECT DISTINCT con FROM con_annotation WHERE contrast_type = ?',
            [$contrast_type],
            's'
        );
        foreach ($typeRows as $r) {
            if (!empty($r['con'])) {
                $byType[$r['con']] = true;
            }
        }
        $names = array_values(array_filter($names, function ($n) use ($byType) {
            return isset($byType[$n]);
        }));
    }

    return $names;
}

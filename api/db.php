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
    'phosphorylation' => 'Phosphorylation',
    'acetylation'     => 'Acetylation',
    'ubiquitylation'  => 'Ubiquitylation',
    'methylation'     => 'Methylation',
    'glycosylation'   => 'Glycosylation',
    'sumoylation'     => 'SUMOylation',
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

/** Map a qevent row to the API event JSON shape expected by the agent. */
function format_event_row(array $row): array {
    $fdr = $row['fdr'] ?? null;
    $fdrFlag = false;
    if ($fdr !== null && $fdr !== '' && $fdr !== '-' && $fdr !== '0') {
        $fdrFlag = true;
    }

    return [
        'pmid'                => $row['pmid'] ?? null,
        'uniprot_ac'          => $row['up'] ?? null,
        'gene'                => $row['gene'] ?? null,
        'position'            => nullable_int($row['pos'] ?? null),
        'ptm_type'            => isset($row['mods']) ? strtolower($row['mods']) : null,
        'sequence_window'     => $row['pep'] ?? null,
        'sample'              => $row['sample'] ?? null,
        'condition'           => $row['samplecondition'] ?? null,
        'organism'            => $row['org'] ?? null,
        'log2_ratio'          => nullable_float($row['qratio'] ?? null),
        'p_value'             => nullable_float($row['pvalue'] ?? null),
        'proteome_log2_ratio' => nullable_float($row['qratiopro'] ?? null),
        'proteome_p_value'    => nullable_float($row['pvaluepro'] ?? null),
        'stars'               => nullable_int($row['qptmscore'] ?? null),
        'fdr_flag'            => $fdrFlag,
        'fdr'                 => $fdr,
    ];
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

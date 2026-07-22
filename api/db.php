<?php
/**
 * qPTM REST API — Shared database connection and JSON helpers.
 *
 * This file is included by all /api/*.php endpoints. It provides:
 * - MySQL connection (from environment or config constants)
 * - CORS headers
 * - JSON response helpers
 * - Query parameter sanitization
 *
 * Configuration: set DB credentials via environment variables or edit
 * the defaults below to match your qPTM MySQL database.
 */

// ── CORS Headers ──────────────────────────────────────────────────
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');
header('Content-Type: application/json; charset=utf-8');

// Handle preflight
if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(204);
    exit;
}

// ── Database Configuration ────────────────────────────────────────
// Adjust these to match your qPTM MySQL database credentials.
// You can also set them as environment variables.
$DB_HOST = getenv('QPTM_DB_HOST') ?: 'localhost';
$DB_USER = getenv('QPTM_DB_USER') ?: 'qptm_user';
$DB_PASS = getenv('QPTM_DB_PASS') ?: 'qptm_password';
$DB_NAME = getenv('QPTM_DB_NAME') ?: 'qptm';
$DB_PORT = intval(getenv('QPTM_DB_PORT') ?: '3306');

// ── PTM type mapping ──────────────────────────────────────────────
// Maps URL-friendly names to database values
$PTM_TYPE_MAP = [
    'phosphorylation' => 'phosphorylation',
    'acetylation'     => 'acetylation',
    'ubiquitylation'  => 'ubiquitylation',
    'methylation'     => 'methylation',
    'glycosylation'   => 'glycosylation',
    'sumoylation'     => 'sumoylation',
];

$ORGANISM_MAP = [
    'human'  => 'Homo sapiens',
    'mouse'  => 'Mus musculus',
    'rat'    => 'Rattus norvegicus',
    'yeast'  => 'Saccharomyces cerevisiae',
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
    return $val !== null ? trim($val) : $default;
}

function param_int(string $key, int $default): int {
    $val = $_GET[$key] ?? null;
    if ($val === null) return $default;
    $int = intval($val);
    return $int > 0 ? $int : $default;
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
    $stmt->execute();
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

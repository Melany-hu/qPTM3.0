<?php
/**
 * GET /api/search.php
 *
 * Search qPTM PTM events (qevent) using the same resolution strategy as the
 * live site: resolve gene/protein/function via protable → filter qevent by up.
 *
 * Parameters:
 *   q         - search keyword (required)
 *   field     - any|gene|uniprot|protein|function|sample|condition (default: any)
 *   organism  - human|mouse|rat|yeast|all (default: all)
 *   ptm_type  - phosphorylation|acetylation|... (default: all)
 *   page      - page number (default: 1)
 *   per_page  - results per page, max 100 (default: 20)
 */

require_once __DIR__ . '/db.php';

$q = param('q');
if (!$q) {
    json_error('Parameter "q" is required');
}

$field    = param('field', 'any');
$organism = strtolower(param('organism', 'all'));
$ptm_type = strtolower(param('ptm_type', 'all'));
$page     = param_int('page', 1);
$per_page = min(param_int('per_page', 20), 100);
$offset   = ($page - 1) * $per_page;

// Auto-route vague "any" queries to a fast indexed path.
if ($field === 'any') {
    if (preg_match('/^[OPQ][0-9][A-Z0-9]{3}[0-9](-[0-9]+)?$/i', $q)
        || preg_match('/^[A-NR-Z][0-9][A-Z][A-Z0-9]{2}[0-9](-[0-9]+)?$/i', $q)) {
        $field = 'uniprot';
    } elseif (preg_match('/^[A-Za-z][A-Za-z0-9-]{1,14}$/', $q) && !preg_match('/\s/', $q)) {
        // Short token without spaces → treat as gene symbol
        $field = 'gene';
    }
}

$where = [];
$params = [];
$types = '';

/**
 * Resolve UniProt accessions from protable (capped to avoid huge IN lists).
 * Returns list of primaryacc strings.
 */
function resolve_accessions(string $column, string $keyword, int $limit = 100): array {
    $allowed = [
        'genename'    => true,
        'proteinname' => true,
        'func'        => true,
        'uniprotaccs' => true,
        'primaryacc'  => true,
    ];
    if (!isset($allowed[$column])) {
        return [];
    }
    $rows = fetch_all(
        "SELECT primaryacc FROM protable WHERE $column LIKE ? LIMIT ?",
        ["%$keyword%", $limit],
        'si'
    );
    $accs = [];
    foreach ($rows as $row) {
        if (!empty($row['primaryacc'])) {
            $accs[] = $row['primaryacc'];
        }
    }
    return array_values(array_unique($accs));
}

function append_in_clause(array &$where, array &$params, string &$types, string $column, array $values): void {
    if (empty($values)) {
        $where[] = '0=1';
        return;
    }
    $placeholders = implode(',', array_fill(0, count($values), '?'));
    $where[] = "$column IN ($placeholders)";
    foreach ($values as $v) {
        $params[] = $v;
        $types .= 's';
    }
}

switch ($field) {
    case 'gene':
        // Exact gene symbol match (same as live browse-by-gene).
        $where[] = 'e.gene = ?';
        $params[] = $q;
        $types .= 's';
        break;

    case 'uniprot':
        $where[] = '(e.up = ? OR e.up LIKE ?)';
        $params[] = $q;
        $params[] = $q . '%';
        $types .= 'ss';
        break;

    case 'sample':
        $where[] = 'e.sample LIKE ?';
        $params[] = '%' . $q . '%';
        $types .= 's';
        break;

    case 'condition':
        $where[] = 'e.samplecondition LIKE ?';
        $params[] = '%' . $q . '%';
        $types .= 's';
        break;

    case 'protein':
        append_in_clause($where, $params, $types, 'e.up', resolve_accessions('proteinname', $q, 80));
        break;

    case 'function':
        append_in_clause($where, $params, $types, 'e.up', resolve_accessions('func', $q, 80));
        break;

    default: // any — only for free-text (samples/conditions); avoid leading-wildcard OR storms
        // Prefer gene/uniprot equality + protable AC resolution; skip sample/condition LIKE.
        $accs = array_unique(array_merge(
            resolve_accessions('genename', $q, 40),
            resolve_accessions('proteinname', $q, 40),
            resolve_accessions('primaryacc', $q, 20)
        ));
        $parts = ['e.gene = ?', 'e.up = ?'];
        $params[] = $q;
        $params[] = $q;
        $types .= 'ss';
        if (!empty($accs)) {
            $placeholders = implode(',', array_fill(0, count($accs), '?'));
            $parts[] = "e.up IN ($placeholders)";
            foreach ($accs as $a) {
                $params[] = $a;
                $types .= 's';
            }
        }
        $where[] = '(' . implode(' OR ', $parts) . ')';
        break;
}

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

$countSql = "SELECT COUNT(*) AS total FROM qevent e WHERE $whereClause";
$countRow = fetch_one($countSql, $params, $types);
$total = intval($countRow['total'] ?? 0);

$dataSql = "SELECT e.pmid, e.up, e.gene, e.pos, e.mods, e.pep, e.sample,
                   e.samplecondition, e.org, e.qratio, e.pvalue,
                   e.qratiopro, e.pvaluepro, e.qptmscore, e.fdr
            FROM qevent e
            WHERE $whereClause
            ORDER BY e.qptmscore DESC, e.gene, e.pos
            LIMIT ? OFFSET ?";

$pageParams = array_merge($params, [$per_page, $offset]);
$pageTypes = $types . 'ii';
$rows = fetch_all($dataSql, $pageParams, $pageTypes);
$events = array_map('format_event_row', $rows);

json_response([
    'total'    => $total,
    'page'     => $page,
    'per_page' => $per_page,
    'events'   => $events,
]);

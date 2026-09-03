<?php
/**
 * GET /api/search.php
 *
 * Search qPTM PTM events (qevent) using the same resolution strategy as the
 * live site: resolve gene/protein/function via protable → filter qevent by up.
 * Each event includes Experiment information fields (resource, methods,
 * condition annotations, sample type, database cross-refs, etc.).
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
        // Resolve names via small samtable, then equality on indexed qevent.sample
        // (avoids leading-wildcard LIKE + huge JOIN against scoretable).
        $sampleHits = fetch_all(
            'SELECT DISTINCT sam FROM samtable
             WHERE sam = ? OR sam LIKE ? OR sam LIKE ? OR IFNULL(samdetail, \'\') LIKE ?',
            [$q, $q . '%', '%' . $q . '%', '%' . $q . '%'],
            'ssss'
        );
        $sampleNames = [];
        foreach ($sampleHits as $hit) {
            if (!empty($hit['sam'])) {
                $sampleNames[] = $hit['sam'];
            }
        }
        // Also include exact qevent.sample equality in case samtable is incomplete.
        if (!in_array($q, $sampleNames, true)) {
            $sampleNames[] = $q;
        }
        append_in_clause($where, $params, $types, 'e.sample', array_values(array_unique($sampleNames)));
        break;

    case 'condition':
        // Resolve names via small contable / con_annotation, then equality on
        // indexed qevent.samplecondition (avoids leading-wildcard LIKE on 15M rows).
        $condNames = [];
        $condHits = fetch_all(
            'SELECT DISTINCT con FROM contable
             WHERE con = ? OR con LIKE ? OR con LIKE ? OR IFNULL(condetail, \'\') LIKE ?
             LIMIT 500',
            [$q, $q . '%', '%' . $q . '%', '%' . $q . '%'],
            'ssss'
        );
        foreach ($condHits as $hit) {
            if (!empty($hit['con'])) {
                $condNames[] = $hit['con'];
            }
        }
        $annHits = fetch_all(
            'SELECT DISTINCT con FROM con_annotation
             WHERE con = ? OR con LIKE ? OR con LIKE ?
                OR IFNULL(condetail, \'\') LIKE ?
                OR IFNULL(agent_raw, \'\') LIKE ?
                OR IFNULL(agent_key, \'\') LIKE ?
                OR IFNULL(gene, \'\') LIKE ?
             LIMIT 500',
            [$q, $q . '%', '%' . $q . '%', '%' . $q . '%', '%' . $q . '%', '%' . $q . '%', '%' . $q . '%'],
            'sssssss'
        );
        foreach ($annHits as $hit) {
            if (!empty($hit['con'])) {
                $condNames[] = $hit['con'];
            }
        }
        if (!in_array($q, $condNames, true)) {
            $condNames[] = $q;
        }
        append_in_clause($where, $params, $types, 'e.samplecondition', array_values(array_unique($condNames)));
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

$dataSql = event_select_page_sql($whereClause, 'e.timetype DESC, e.qptmscore DESC, e.gene, e.pos');

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

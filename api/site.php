<?php
/**
 * GET /api/site.php
 *
 * All quantitative events for a specific PTM site (qevent).
 *
 * Path: /api/site/{uniprot_ac}/{position}
 * Or query: uniprot_ac=&position=
 * Optional: ptm_type
 */

require_once __DIR__ . '/db.php';

$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$parts = explode('/', trim($path, '/'));

$siteIdx = array_search('site', $parts);
$uniprot_ac = null;
$position = 0;
if ($siteIdx !== false && isset($parts[$siteIdx + 1]) && isset($parts[$siteIdx + 2])
    && $parts[$siteIdx + 1] !== 'site.php') {
    $uniprot_ac = $parts[$siteIdx + 1];
    $position = intval($parts[$siteIdx + 2]);
} else {
    $uniprot_ac = param('uniprot_ac');
    $position = param_int('position', 0);
}

if (!$uniprot_ac || $position < 1) {
    json_error('Path must be /api/site/{uniprot_ac}/{position} (or pass uniprot_ac & position query params)');
}

$ptm_type = strtolower(param('ptm_type', 'all'));

$where = ['e.up = ?', 'e.pos = ?'];
$params = [$uniprot_ac, $position];
$types = 'si';

if ($ptm_type !== 'all' && isset($PTM_TYPE_MAP[$ptm_type])) {
    $where[] = 'e.mods = ?';
    $params[] = $PTM_TYPE_MAP[$ptm_type];
    $types .= 's';
}
$whereClause = implode(' AND ', $where);

$summarySql = "SELECT e.up, e.pos, e.mods, e.pep,
                      MAX(e.qptmscore) AS stars,
                      COUNT(*) AS total_events,
                      COUNT(DISTINCT e.samplecondition) AS total_conditions,
                      COUNT(DISTINCT e.sample) AS total_samples
               FROM qevent e
               WHERE $whereClause
               GROUP BY e.up, e.pos, e.mods, e.pep";

$summaryRows = fetch_all($summarySql, $params, $types);

if (empty($summaryRows)) {
    json_response([
        'summaries' => [],
        'events'    => [],
        'message'   => 'No PTM events found for this site',
    ]);
}

$eventsSql = "SELECT e.pmid, e.up, e.gene, e.pos, e.mods, e.pep, e.sample,
                      e.samplecondition, e.org, e.qratio, e.pvalue,
                      e.qratiopro, e.pvaluepro, e.qptmscore, e.fdr
               FROM qevent e
               WHERE $whereClause
               ORDER BY e.mods, e.samplecondition, e.sample";

$eventRows = fetch_all($eventsSql, $params, $types);
$events = array_map('format_event_row', $eventRows);

$summaries = array_map(function ($row) {
    return [
        'uniprot_ac'       => $row['up'],
        'position'         => intval($row['pos']),
        'ptm_type'         => strtolower($row['mods']),
        'stars'            => nullable_int($row['stars']),
        'total_events'     => intval($row['total_events']),
        'total_conditions' => intval($row['total_conditions']),
        'total_samples'    => intval($row['total_samples']),
        'sequence_window'  => $row['pep'],
    ];
}, $summaryRows);

json_response([
    'summaries' => $summaries,
    'events'    => $events,
]);

<?php
/**
 * GET /api/stats.php
 *
 * Lightweight stats. Avoids full-table scans on large qevent tables.
 * Agent tools do not depend on this endpoint.
 */

require_once __DIR__ . '/db.php';

$approx = fetch_one(
    "SELECT TABLE_ROWS AS c
     FROM information_schema.TABLES
     WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'qevent'"
);

// Cheap distinct lists from smaller dimension-ish usage via LIMIT sample is unreliable;
// return organism/PTM keys known to the site UI instead of scanning qevent.
json_response([
    'total_events'     => intval($approx['c'] ?? 0),
    'total_sites'      => null,
    'total_proteins'   => null,
    'total_conditions' => null,
    'total_samples'    => null,
    'by_organism'      => [
        'Human' => new stdClass(),
        'Mouse' => new stdClass(),
        'Rat'   => new stdClass(),
        'Yeast' => new stdClass(),
    ],
    'by_ptm_type'      => [
        'phosphorylation' => new stdClass(),
        'acetylation'     => new stdClass(),
        'methylation'     => new stdClass(),
        'ubiquitylation'  => new stdClass(),
        'glycosylation'   => new stdClass(),
        'sumoylation'     => new stdClass(),
    ],
    'note'             => 'total_events is approximate (INFORMATION_SCHEMA.TABLE_ROWS)',
]);

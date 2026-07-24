<?php
/**
 * GET /api/kinases.php
 *
 * Kinases / enzymes for a PTM site from phosenztable / aceenztable.
 *
 * Path: /api/kinases/{uniprot_ac}/{position}
 * Or query: uniprot_ac=&position=
 */

require_once __DIR__ . '/db.php';

$path = parse_url($_SERVER['REQUEST_URI'], PHP_URL_PATH);
$parts = explode('/', trim($path, '/'));
$kinaseIdx = array_search('kinases', $parts);

$uniprot_ac = null;
$position = 0;
if ($kinaseIdx !== false && isset($parts[$kinaseIdx + 1]) && isset($parts[$kinaseIdx + 2])
    && $parts[$kinaseIdx + 1] !== 'kinases.php') {
    $uniprot_ac = $parts[$kinaseIdx + 1];
    $position = intval($parts[$kinaseIdx + 2]);
} else {
    $uniprot_ac = param('uniprot_ac');
    $position = param_int('position', 0);
}

if (!$uniprot_ac || $position < 1) {
    json_error('Path must be /api/kinases/{uniprot_ac}/{position} (or pass uniprot_ac & position query params)');
}

/**
 * Parse "Kinase#DrugBankID|..." style enzyme fields into API kinase objects.
 */
function parse_enzyme_field(?string $raw, string $evidenceType, string $sourceDb, string $ptmType): array {
    $out = [];
    if ($raw === null || $raw === '' || $raw === '-') {
        return $out;
    }
    foreach (explode('|', $raw) as $chunk) {
        $chunk = trim($chunk);
        if ($chunk === '') {
            continue;
        }
        $bits = explode('#', $chunk);
        $gene = trim($bits[0] ?? '');
        $inhibitor = isset($bits[1]) ? trim($bits[1]) : '';
        if ($gene === '') {
            continue;
        }
        $out[] = [
            'kinase_gene'    => $gene,
            'kinase_uniprot' => null,
            'evidence_type'  => $evidenceType,
            'source_db'      => $sourceDb,
            'inhibitor'      => $inhibitor !== '' ? $inhibitor : null,
            'ptm_type'       => $ptmType,
        ];
    }
    return $out;
}

$kinases = [];

$posStr = (string)$position;

$phos = fetch_one(
    'SELECT exp, gps, igps FROM phosenztable WHERE up = ? AND pos = ?',
    [$uniprot_ac, $posStr],
    'ss'
);
if ($phos) {
    $kinases = array_merge(
        $kinases,
        parse_enzyme_field($phos['exp'] ?? null, 'experimental', 'qPTM', 'phosphorylation'),
        parse_enzyme_field($phos['gps'] ?? null, 'predicted', 'GPS', 'phosphorylation'),
        parse_enzyme_field($phos['igps'] ?? null, 'predicted', 'iGPS', 'phosphorylation')
    );
}

$ace = fetch_one(
    'SELECT exp, pla FROM aceenztable WHERE up = ? AND pos = ?',
    [$uniprot_ac, $posStr],
    'ss'
);
if ($ace) {
    $kinases = array_merge(
        $kinases,
        parse_enzyme_field($ace['exp'] ?? null, 'experimental', 'qPTM', 'acetylation'),
        parse_enzyme_field($ace['pla'] ?? null, 'predicted', 'Deep-PLA', 'acetylation')
    );
}

json_response([
    'uniprot_ac' => $uniprot_ac,
    'position'   => $position,
    'total'      => count($kinases),
    'kinases'    => $kinases,
]);

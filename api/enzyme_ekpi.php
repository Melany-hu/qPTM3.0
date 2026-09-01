<?php
/**
 * GET /api/enzyme_ekpi.php
 *
 * Lazy-load top eKPI quantitative kinase–site Spearman correlations.
 * Query: uniprot_ac=&position=&limit=10
 */

require_once __DIR__ . '/db.php';

$uniprot_ac = param('uniprot_ac');
$position = param_int('position', 0);
$limit = param_int('limit', 10);
if ($limit < 1) {
    $limit = 10;
}
if ($limit > 20) {
    $limit = 20;
}

if (!$uniprot_ac || $position < 1) {
    json_error('Pass uniprot_ac and position');
}

$CANCER_TYPE_BY_PMID = [
    '34534465' => 'Pancreatic Ductal Adenocarcinoma',
    '33242424' => 'Pediatric Brain Cancer',
    '32649875' => 'Non-Smoking Lung Cancer',
    '30205044' => 'Medulloblastoma',
    '32888432' => 'Metastatic Colorectal Cancer',
    '32649874' => 'Lung Adenocarcinoma',
    '32649877' => 'Lung Adenocarcinoma',
    '34358469' => 'Lung Squamous Cell Carcinoma',
    '34971568' => 'Intrahepatic Cholangiocarcinoma',
    '27372738' => 'High-Grade Serous Ovarian Cancer',
    '31585088' => 'HBV-Related Hepatocellular Carcinoma',
    '33577785' => 'Glioblastoma',
    '30814741' => 'Early-Stage Hepatocellular Carcinoma',
    '34764241' => 'Esophageal Squamous Cell Carcinoma',
    '30645970' => 'Early-Onset Gastric Cancer',
    '32059776' => 'Endometrial Carcinoma',
    '34400640' => 'Esophageal Cancer',
    '31751824' => 'Diffuse-Type Gastric Cancer',
    '25043054' => 'CRC.Nat',
    '31031003' => 'Colon Cancer',
    '31675502' => 'Clear Cell Renal Cell Carcinoma',
    '27251275' => 'Breast Cancer',
    '33212010' => 'Treatment-Naive Primary Breast Cancers',
    '33417831' => 'HPV-Negative Head And Neck Squamous Cell Carcinoma',
    '36001024' => 'Triple-Negative Breast Cancer',
];

$sitesDb = dirname(__DIR__) . '/agent-backend/data/enzymes/eKPI/indexes/sites.sqlite';
$ekpiDir = getenv('EKPI_FINAL_RESULT_DIR') ?: '/var/www/html/ekpi/final_result';

if (!is_file($sitesDb)) {
    json_response([
        'uniprot_ac' => $uniprot_ac,
        'position' => $position,
        'total' => 0,
        'correlations' => [],
        'message' => 'eKPI site index not available',
    ]);
}

try {
    $sqlite = new SQLite3($sitesDb, SQLITE3_OPEN_READONLY);
} catch (Exception $e) {
    json_error('Cannot open eKPI index', 500);
}

$stmt = $sqlite->prepare('SELECT file_key, site, gene FROM records WHERE uniprot_base = :u AND position = :p LIMIT 1');
$stmt->bindValue(':u', $uniprot_ac, SQLITE3_TEXT);
$stmt->bindValue(':p', (string)$position, SQLITE3_TEXT);
$res = $stmt->execute();
$siteRow = $res ? $res->fetchArray(SQLITE3_ASSOC) : false;
$sqlite->close();

if (!$siteRow || empty($siteRow['file_key'])) {
    json_response([
        'uniprot_ac' => $uniprot_ac,
        'position' => $position,
        'total' => 0,
        'correlations' => [],
        'message' => 'No eKPI site entry',
    ]);
}

$fileKey = $siteRow['file_key'];
$path = rtrim($ekpiDir, '/') . '/' . $fileKey . '.csv.gz';
if (!is_file($path)) {
    json_response([
        'uniprot_ac' => $uniprot_ac,
        'position' => $position,
        'site' => $siteRow['site'] ?? null,
        'total' => 0,
        'correlations' => [],
        'message' => 'eKPI matrix file not found',
    ]);
}

$fh = @gzopen($path, 'r');
if (!$fh) {
    json_error('Cannot read eKPI matrix', 500);
}

$header = gzgets($fh);
$candidates = [];
while (($line = gzgets($fh)) !== false) {
    $record = str_getcsv(rtrim($line, "\r\n"));
    if (count($record) < 5) {
        continue;
    }
    $kinase = trim($record[0]);
    $quantRaw = trim($record[4]);
    if ($kinase === '' || strcasecmp($kinase, 'Kinase') === 0 || $quantRaw === '' || $quantRaw === 'NA') {
        continue;
    }
    foreach (explode('; ', $quantRaw) as $entry) {
        $entry = trim($entry);
        if ($entry === '' || $entry === 'NA') {
            continue;
        }
        $parts = explode('#', $entry);
        if (count($parts) < 6) {
            continue;
        }
        [$feature, $rhoS, $pS, $nS, $pmid, $cohort] = array_slice($parts, 0, 6);
        if (!is_numeric($rhoS) || !is_numeric($pS)) {
            continue;
        }
        $rho = floatval($rhoS);
        $pvalue = floatval($pS);
        $n = intval(floatval($nS));
        $pmid = trim($pmid);
        $isTumor = (stripos($cohort, 'tumor') !== false);
        $candidates[] = [
            'kinase' => $kinase,
            'feature' => $feature,
            'rho' => $rho,
            'pvalue' => $pvalue,
            'n' => $n,
            'pmid' => ctype_digit($pmid) ? $pmid : null,
            'cancer_type' => (ctype_digit($pmid) && isset($CANCER_TYPE_BY_PMID[$pmid])) ? $CANCER_TYPE_BY_PMID[$pmid] : null,
            'cohort' => $cohort,
            'is_tumor' => $isTumor,
            'abs_rho' => abs($rho),
        ];
    }
}
gzclose($fh);

usort($candidates, function ($a, $b) {
    if ($a['is_tumor'] !== $b['is_tumor']) {
        return $a['is_tumor'] ? -1 : 1;
    }
    if ($a['abs_rho'] == $b['abs_rho']) {
        return $a['pvalue'] <=> $b['pvalue'];
    }
    return ($a['abs_rho'] < $b['abs_rho']) ? 1 : -1;
});

$top = array_slice($candidates, 0, $limit);
foreach ($top as &$row) {
    unset($row['abs_rho'], $row['is_tumor']);
}
unset($row);

json_response([
    'uniprot_ac' => $uniprot_ac,
    'position' => $position,
    'site' => $siteRow['site'] ?? null,
    'gene' => $siteRow['gene'] ?? null,
    'total' => count($top),
    'correlations' => $top,
    'source' => [
        'name' => 'eKPI',
        'homepage' => 'https://ekpi.omicsbio.info/',
        'pmid' => '40194556',
    ],
]);

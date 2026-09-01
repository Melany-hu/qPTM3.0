<?php
/**
 * Read-only helpers for agent-backend SQLite enzyme/drug indexes.
 */

function agentDataRoot(){
	static $root = null;
	if($root === null){
		$root = dirname(__DIR__).'/agent-backend/data';
	}
	return $root;
}

function openAgentSqlite($relativePath){
	$path = agentDataRoot().'/'.$relativePath;
	if(!is_file($path)){
		return null;
	}
	try{
		$db = new SQLite3($path, SQLITE3_OPEN_READONLY);
		$db->busyTimeout(2000);
		return $db;
	}catch(Exception $e){
		return null;
	}
}

function lookupKinaseUniprots(array $genes){
	$out = array();
	$genes = array_values(array_unique(array_filter(array_map(function($g){
		return strtoupper(trim((string)$g));
	}, $genes))));
	if(!$genes){
		return $out;
	}
	$db = openAgentSqlite('enzymes/PhosphoSitePlus/indexes/kinase_substrate.sqlite');
	if($db){
		foreach($genes as $gene){
			if(isset($out[$gene])){
				continue;
			}
			$stmt = $db->prepare('SELECT kin_uniprot FROM records WHERE UPPER(kinase) = :g AND kin_uniprot IS NOT NULL AND kin_uniprot != "" LIMIT 1');
			if(!$stmt){
				continue;
			}
			$stmt->bindValue(':g', $gene, SQLITE3_TEXT);
			$res = $stmt->execute();
			$row = $res ? $res->fetchArray(SQLITE3_ASSOC) : false;
			if($row && !empty($row['kin_uniprot'])){
				$out[$gene] = preg_replace('/-\d+$/', '', trim($row['kin_uniprot']));
			}
		}
		$db->close();
	}
	$missing = array_diff($genes, array_keys($out));
	if($missing){
		$db = openAgentSqlite('enzymes/KAKA/indexes/events.sqlite');
		if($db){
			foreach($missing as $gene){
				$stmt = $db->prepare('SELECT uniprot_base FROM records WHERE UPPER(gene) = :g AND uniprot_base IS NOT NULL AND uniprot_base != "" LIMIT 1');
				if(!$stmt){
					continue;
				}
				$stmt->bindValue(':g', $gene, SQLITE3_TEXT);
				$res = $stmt->execute();
				$row = $res ? $res->fetchArray(SQLITE3_ASSOC) : false;
				if($row && !empty($row['uniprot_base'])){
					$out[$gene] = trim($row['uniprot_base']);
				}
			}
			$db->close();
		}
	}
	return $out;
}

function lookupUbiBrowserInteractions($uniprot, $limit = 50){
	$uniprot = trim((string)$uniprot);
	$out = array();
	if($uniprot === ''){
		return $out;
	}
	$base = preg_replace('/-\d+$/', '', $uniprot);
	$db = openAgentSqlite('enzymes/UbiBrowser/indexes/interactions.sqlite');
	if(!$db){
		return $out;
	}
	$stmt = $db->prepare(
		'SELECT enzyme_type, enzyme_gene, enzyme_uniprot, family, pmid, species, sentence
		 FROM records
		 WHERE substrate_uniprot = :u OR substrate_uniprot = :b OR substrate_uniprot LIKE :like
		 LIMIT 200'
	);
	if(!$stmt){
		$db->close();
		return $out;
	}
	$stmt->bindValue(':u', $uniprot, SQLITE3_TEXT);
	$stmt->bindValue(':b', $base, SQLITE3_TEXT);
	$stmt->bindValue(':like', $base.'-%', SQLITE3_TEXT);
	$res = $stmt->execute();
	$seen = array();
	while($res && ($row = $res->fetchArray(SQLITE3_ASSOC))){
		$key = strtoupper(($row['enzyme_type'] ?? '').'|'.($row['enzyme_gene'] ?? '').'|'.($row['enzyme_uniprot'] ?? '').'|'.($row['pmid'] ?? ''));
		if(isset($seen[$key])){
			continue;
		}
		$seen[$key] = true;
		$species = (string)($row['species'] ?? '');
		$out[] = array(
			'enzyme_type' => $row['enzyme_type'] ?? '',
			'enzyme_gene' => $row['enzyme_gene'] ?? '',
			'enzyme_uniprot' => $row['enzyme_uniprot'] ?? '',
			'family' => $row['family'] ?? '',
			'pmid' => $row['pmid'] ?? '',
			'species' => $species,
			'sentence' => $row['sentence'] ?? '',
			'_human' => (stripos($species, 'sapiens') !== false || stripos($species, 'human') !== false) ? 0 : 1,
		);
		if(count($out) >= $limit){
			break;
		}
	}
	$db->close();
	usort($out, function($a, $b){
		if($a['_human'] !== $b['_human']){
			return $a['_human'] - $b['_human'];
		}
		$typeCmp = strcmp($a['enzyme_type'], $b['enzyme_type']);
		if($typeCmp !== 0){
			return $typeCmp;
		}
		return strcmp($a['enzyme_gene'], $b['enzyme_gene']);
	});
	foreach($out as &$r){
		unset($r['_human']);
	}
	unset($r);
	return $out;
}

function lookupGpsUberE3BySubstrate($uniprot, $limit = 150){
	$uniprot = trim((string)$uniprot);
	$out = array();
	if($uniprot === ''){
		return $out;
	}
	$base = preg_replace('/-\d+$/', '', strtoupper($uniprot));
	$up = strtoupper($uniprot);
	$db = openAgentSqlite('enzymes/GPS-Uber/indexes/ssesr.sqlite');
	if(!$db){
		return $out;
	}
	$stmt = $db->prepare(
		'SELECT e3_gene, e3_class, pmids
		 FROM records
		 WHERE UPPER(substrate_uniprot_base) = :b
		    OR UPPER(substrate_uniprot) = :u
		    OR UPPER(substrate_uniprot) LIKE :like
		 ORDER BY e3_gene COLLATE NOCASE, position'
	);
	if(!$stmt){
		$db->close();
		return $out;
	}
	$stmt->bindValue(':b', $base, SQLITE3_TEXT);
	$stmt->bindValue(':u', $up, SQLITE3_TEXT);
	$stmt->bindValue(':like', $base.'-%', SQLITE3_TEXT);
	$res = $stmt->execute();
	$merged = array();
	while($res && ($row = $res->fetchArray(SQLITE3_ASSOC))){
		$gene = trim((string)($row['e3_gene'] ?? ''));
		if($gene === ''){
			continue;
		}
		$key = strtoupper($gene);
		if(!isset($merged[$key])){
			$merged[$key] = array(
				'gene' => $gene,
				'class' => '',
				'pmids' => array(),
			);
		}
		$cls = trim(str_replace(array('|', '#'), '/', (string)($row['e3_class'] ?? '')));
		if($cls === ''){
			$cls = 'unclassified';
		}
		if($merged[$key]['class'] === ''){
			$merged[$key]['class'] = $cls;
		}
		foreach(preg_split('/[;,]+/', (string)($row['pmids'] ?? '')) as $pmid){
			$pmid = trim($pmid);
			if($pmid !== '' && ctype_digit($pmid) && !in_array($pmid, $merged[$key]['pmids'], true)){
				$merged[$key]['pmids'][] = $pmid;
			}
		}
	}
	$db->close();
	foreach($merged as $r){
		$out[] = $r;
	}
	usort($out, function($a, $b){
		return strcasecmp($a['gene'], $b['gene']);
	});
	if($limit > 0 && count($out) > $limit){
		$out = array_slice($out, 0, $limit);
	}
	return $out;
}

function lookupWeramRegulators($modification, $evidence = '', $limit = 300){
	$out = array();
	$modification = strtolower(trim((string)$modification));
	if($modification === ''){
		return $out;
	}
	$db = openAgentSqlite('enzymes/WERAM/indexes/proteins.sqlite');
	if(!$db){
		return $out;
	}
	$evidence = strtolower(trim((string)$evidence));
	if($evidence === 'collected' || $evidence === 'predicted'){
		$stmt = $db->prepare(
			"SELECT weram_id, gene, uniprot, role, family, class, evidence
			 FROM records
			 WHERE lower(modification) = :mod AND lower(evidence) = :ev
			 ORDER BY gene COLLATE NOCASE"
		);
		if(!$stmt){
			$db->close();
			return $out;
		}
		$stmt->bindValue(':mod', $modification, SQLITE3_TEXT);
		$stmt->bindValue(':ev', $evidence, SQLITE3_TEXT);
		$res = $stmt->execute();
	}else{
		$stmt = $db->prepare(
			"SELECT weram_id, gene, uniprot, role, family, class, evidence
			 FROM records
			 WHERE lower(modification) = :mod
			 ORDER BY gene COLLATE NOCASE"
		);
		if(!$stmt){
			$db->close();
			return $out;
		}
		$stmt->bindValue(':mod', $modification, SQLITE3_TEXT);
		$res = $stmt->execute();
	}
	$seen = array();
	$roleRank = array('writer' => 0, 'eraser' => 1, 'reader' => 2);
	while($res && ($row = $res->fetchArray(SQLITE3_ASSOC))){
		$gene = trim((string)($row['gene'] ?? ''));
		$role = trim((string)($row['role'] ?? ''));
		$family = trim((string)($row['family'] ?? ''));
		$class = trim((string)($row['class'] ?? ''));
		$ev = trim((string)($row['evidence'] ?? ''));
		$key = strtoupper($gene.'|'.$role.'|'.$family.'|'.$class.'|'.$ev);
		if($gene === '' || isset($seen[$key])){
			continue;
		}
		$seen[$key] = true;
		$out[] = array(
			'weram_id' => $row['weram_id'] ?? '',
			'gene' => $gene,
			'uniprot' => $row['uniprot'] ?? '',
			'role' => $role,
			'family' => $family,
			'class' => $class,
			'evidence' => $ev,
			'_role' => isset($roleRank[$role]) ? $roleRank[$role] : 9,
			'_ev' => (strcasecmp($ev, 'collected') === 0) ? 0 : 1,
		);
		if(count($out) >= $limit){
			break;
		}
	}
	$db->close();
	usort($out, function($a, $b){
		if($a['_role'] !== $b['_role']){
			return $a['_role'] - $b['_role'];
		}
		if($a['_ev'] !== $b['_ev']){
			return $a['_ev'] - $b['_ev'];
		}
		return strcasecmp($a['gene'], $b['gene']);
	});
	foreach($out as &$r){
		unset($r['_role'], $r['_ev']);
	}
	unset($r);
	return $out;
}

function lookupWeramAcetylation($evidence = '', $limit = 200){
	return lookupWeramRegulators('acetylation', $evidence, $limit);
}

/**
 * UniProt accession for a WERAM regulator gene (optional modification filter).
 */
function lookupWeramUniprot($gene, $modification = ''){
	$gene = strtoupper(trim((string)$gene));
	if($gene === ''){
		return '';
	}
	$db = openAgentSqlite('enzymes/WERAM/indexes/proteins.sqlite');
	if(!$db){
		return '';
	}
	$modification = strtolower(trim((string)$modification));
	if($modification !== ''){
		$stmt = $db->prepare(
			"SELECT uniprot FROM records
			 WHERE lower(modification) = :mod AND upper(gene) = :g
			   AND uniprot IS NOT NULL AND uniprot != ''
			 LIMIT 1"
		);
		if(!$stmt){
			$db->close();
			return '';
		}
		$stmt->bindValue(':mod', $modification, SQLITE3_TEXT);
		$stmt->bindValue(':g', $gene, SQLITE3_TEXT);
	}else{
		$stmt = $db->prepare(
			"SELECT uniprot FROM records
			 WHERE upper(gene) = :g
			   AND uniprot IS NOT NULL AND uniprot != ''
			 LIMIT 1"
		);
		if(!$stmt){
			$db->close();
			return '';
		}
		$stmt->bindValue(':g', $gene, SQLITE3_TEXT);
	}
	$res = $stmt->execute();
	$row = $res ? $res->fetchArray(SQLITE3_ASSOC) : false;
	$db->close();
	if(!$row || empty($row['uniprot'])){
		return '';
	}
	return preg_replace('/-\d+$/', '', trim($row['uniprot']));
}

/**
 * UniProt accession for an acetylation regulator gene (WERAM).
 */
function lookupWeramAcetylationUniprot($gene){
	return lookupWeramUniprot($gene, 'acetylation');
}

/**
 * DrugBank IDs targeting a protein (by UniProt), preferring approved/investigational drugs.
 */
function lookupDrugBankIdsByUniprot($uniprot, $limit = 8){
	$uniprot = preg_replace('/-\d+$/', '', trim((string)$uniprot));
	$limit = max(1, (int)$limit);
	if($uniprot === ''){
		return '';
	}
	$db = openAgentSqlite('drug/DrugBank/indexes/targets.sqlite');
	if(!$db){
		return '';
	}
	$stmt = $db->prepare('SELECT db_id, groups FROM records WHERE uniprot = :u');
	if(!$stmt){
		$db->close();
		return '';
	}
	$stmt->bindValue(':u', $uniprot, SQLITE3_TEXT);
	$res = $stmt->execute();
	$ranked = array();
	$seen = array();
	while($res && ($row = $res->fetchArray(SQLITE3_ASSOC))){
		$dbid = trim((string)($row['db_id'] ?? ''));
		if($dbid === '' || isset($seen[$dbid])){
			continue;
		}
		$seen[$dbid] = true;
		$groups = strtolower((string)($row['groups'] ?? ''));
		if(strpos($groups, 'approved') !== false){
			$rank = 0;
		}elseif(strpos($groups, 'investigational') !== false){
			$rank = 1;
		}elseif(strpos($groups, 'experimental') !== false){
			$rank = 2;
		}else{
			$rank = 3;
		}
		$ranked[] = array($rank, $dbid);
	}
	$db->close();
	if(!$ranked){
		return '';
	}
	usort($ranked, function($a, $b){
		if($a[0] !== $b[0]){
			return $a[0] - $b[0];
		}
		return strcmp($a[1], $b[1]);
	});
	$ids = array();
	foreach(array_slice($ranked, 0, $limit) as $item){
		$ids[] = $item[1];
	}
	return implode(',', $ids);
}

function lookupDrugBankClinical(array $dbIds){
	$out = array();
	$dbIds = array_values(array_unique(array_filter(array_map('trim', $dbIds))));
	if(!$dbIds){
		return $out;
	}
	$db = openAgentSqlite('drug/DrugBank/indexes/targets.sqlite');
	if(!$db){
		return $out;
	}
	foreach($dbIds as $id){
		if(isset($out[$id])){
			continue;
		}
		$stmt = $db->prepare('SELECT drug_name, groups FROM records WHERE db_id = :id LIMIT 5');
		if(!$stmt){
			continue;
		}
		$stmt->bindValue(':id', $id, SQLITE3_TEXT);
		$res = $stmt->execute();
		$bestName = '';
		$bestGroups = '';
		$bestRank = 99;
		while($res && ($row = $res->fetchArray(SQLITE3_ASSOC))){
			$groups = isset($row['groups']) ? strtolower($row['groups']) : '';
			$rank = 3;
			if(strpos($groups, 'approved') !== false){
				$rank = 0;
			}elseif(strpos($groups, 'investigational') !== false){
				$rank = 1;
			}elseif(strpos($groups, 'experimental') !== false){
				$rank = 2;
			}
			if($rank < $bestRank){
				$bestRank = $rank;
				$bestGroups = isset($row['groups']) ? $row['groups'] : '';
				$bestName = isset($row['drug_name']) ? $row['drug_name'] : '';
			}
		}
		if($bestGroups !== '' || $bestName !== ''){
			$out[$id] = array(
				'name' => $bestName,
				'groups' => $bestGroups,
				'status' => simplifyDrugClinicalStatus($bestGroups),
			);
		}
	}
	$db->close();
	return $out;
}

function simplifyDrugClinicalStatus($groups){
	$g = strtolower((string)$groups);
	$labels = array();
	if(strpos($g, 'approved') !== false){
		$labels[] = 'approved';
	}
	if(strpos($g, 'investigational') !== false){
		$labels[] = 'investigational';
	}
	if(strpos($g, 'experimental') !== false){
		$labels[] = 'experimental';
	}
	if(strpos($g, 'withdrawn') !== false){
		$labels[] = 'withdrawn';
	}
	if(!$labels){
		return $g !== '' ? $g : '-';
	}
	return implode(', ', $labels);
}

<?php
header('Access-Control-Allow-Origin: *');

$source = isset($_GET['source']) ? strtolower(trim((string)$_GET['source'])) : '';
$uniprot = strtoupper(trim((string)(isset($_GET['uniprot']) ? $_GET['uniprot'] : '')));
$pdb = strtoupper(trim((string)(isset($_GET['pdb']) ? $_GET['pdb'] : '')));

function fetchStructureUrl($url){
	$context = stream_context_create(array(
		'http' => array(
			'timeout' => 30,
			'user_agent' => 'qPTM/1.0',
			'ignore_errors' => true
		),
		'ssl' => array(
			'verify_peer' => true,
			'verify_peer_name' => true
		)
	));
	$data = @file_get_contents($url, false, $context);
	if($data === false || $data === ''){
		return '';
	}
	return $data;
}

function sendStructureResponse($data, $contentType){
	header('Content-Type: '.$contentType);
	header('Cache-Control: public, max-age=86400');
	echo $data;
	exit;
}

if($source === 'alphafold' && $uniprot !== ''){
	$urls = array(
		'https://alphafold.ebi.ac.uk/files/AF-'.$uniprot.'-F1-model_v6.cif',
		'https://alphafold.ebi.ac.uk/files/AF-'.$uniprot.'-F1-model_v4.cif',
		'https://alphafold.ebi.ac.uk/files/AF-'.$uniprot.'-F1-model_v3.cif'
	);
	foreach($urls as $url){
		$data = fetchStructureUrl($url);
		if($data !== '' && (strpos($data, 'data_') === 0 || strpos($data, '_atom_site') !== false)){
			sendStructureResponse($data, 'chemical/x-cif');
		}
	}
	http_response_code(404);
	exit;
}

if($source === 'rcsb' && preg_match('/^[A-Z0-9]{4}$/', $pdb)){
	$data = fetchStructureUrl('https://files.rcsb.org/download/'.$pdb.'.pdb');
	if($data !== '' && (strpos($data, 'HEADER') !== false || strpos($data, 'ATOM') !== false || strpos($data, 'HETATM') !== false)){
		sendStructureResponse($data, 'chemical/x-pdb');
	}
	http_response_code(404);
	exit;
}

if($source === 'local' && $uniprot !== ''){
	$path = __DIR__.'/structures/'.$uniprot.'.pdb';
	if(is_file($path)){
		sendStructureResponse(file_get_contents($path), 'chemical/x-pdb');
	}
	http_response_code(404);
	exit;
}

http_response_code(400);
echo 'Invalid structure source.';

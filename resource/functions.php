<?php
/**
 * @author Qingfeng Zhang
 * @version 1.0
 **/

/*------ Connnet to database ------*/
 function connectDB() {
    @ $db = new mysqli('localhost','cancerbi_web','web4lzx!','cancerbi_qptm2026');
    if (!$db) {
        echo ("Can't connect to MySQL Server. Errorcode: %s ". mysqli_connect_error());
        exit;
    }else {
        $db->set_charset('utf8mb4');
        return $db;
    }
}

/**
 * Restore common Greek/symbol chars lost as U+FFFD or literal '?' in curated text.
 */
function fixLostUtf8Replacements($value){
	if(!is_string($value) || $value === ''){
		return $value;
	}
	$u = "\u{FFFD}";
	$map = array(
		$u.$u.'M' => 'μM',
		'??M' => 'μM',
		$u.$u.'Vif' => 'ΔVif',
		'??Vif' => 'ΔVif',
		$u.$u.'Vpr' => 'ΔVpr',
		'??Vpr' => 'ΔVpr',
		$u.$u.'Vpu' => 'ΔVpu',
		'??Vpu' => 'ΔVpu',
		'micTNF'.$u.$u => 'micTNFα',
		'micTNF??' => 'micTNFα',
		'MAPT'.$u.$u.'P301S' => 'MAPT×P301S',
		'MAPT??P301S' => 'MAPT×P301S',
		'JNK2'.$u.$u => 'JNK2α',
		'JNK2??' => 'JNK2α',
		'CamKII??' => 'CamKIIα',
		'ATG5flox:CamKII??-Cre' => 'ATG5flox:CamKIIα-Cre',
	);
	foreach($map as $from => $to){
		$value = str_replace($from, $to, $value);
	}
	$value = str_replace('<U+2011>', '-', $value);
	$value = str_replace('<U+200B>', '', $value);

	if(strpos($value, '?') !== false){
		$value = preg_replace('/(\d+(?:\.\d+)?)\s*\?M\b/u', '$1 μM', $value);
		$value = preg_replace('/(\d+(?:\.\d+)?)\s+\?m\b/u', '$1 μm', $value);
		$value = preg_replace('/(\d+(?:\.\d+)?)\s+\?mol/u', '$1 μmol', $value);
	}

	return $value;
}

/**
 * Fix UTF-8 text that was mis-decoded as Latin-1 (e.g. Î± → α).
 */
function fixUtf8Mojibake($value){
	if(!is_string($value) || $value === ''){
		return $value;
	}
	if(strpos($value, 'Î') === false && strpos($value, 'Â') === false && strpos($value, 'Ã') === false){
		return $value;
	}
	$latin1 = @mb_convert_encoding($value, 'ISO-8859-1', 'UTF-8');
	if($latin1 === false || $latin1 === '' || !mb_check_encoding($latin1, 'UTF-8')){
		return $value;
	}
	$hadMojibakeMarker = (strpos($value, 'Î') !== false || strpos($value, 'Â') !== false || strpos($value, 'Ã') !== false);
	$stillMojibake = (strpos($latin1, 'Î') !== false && substr_count($latin1, 'Î') >= substr_count($value, 'Î'));
	if($hadMojibakeMarker && !$stillMojibake){
		return $latin1;
	}
	if(preg_match('/\p{Greek}/u', $latin1)){
		return $latin1;
	}
	return $value;
}

/**
 * Normalize DB/text values for HTML display: lost-char fix, mojibake fix, entity decode, escape.
 */
function displayText($value){
	if($value === null){
		return '-';
	}
	$value = trim((string)$value);
	if($value === ''){
		return '';
	}
	$value = fixLostUtf8Replacements($value);
	$value = fixUtf8Mojibake($value);
	$value = html_entity_decode($value, ENT_QUOTES | ENT_HTML5, 'UTF-8');
	return htmlspecialchars($value, ENT_QUOTES, 'UTF-8');
}

/**
 * Display-only fix: cell-cycle typo "S phage" / "G1 phage" → "phase".
 * Does not change stored data; safe against macrophage / esophageal.
 */
function fixCellCyclePhageDisplay($text){
	$text = (string)$text;
	if($text === '' || stripos($text, 'phage') === false){
		return $text;
	}
	return preg_replace(
		'/\b((?:Early|Late|Middle)\s+S|G0|G1(?:-S)?|G2|M|mitosis|S)\s+phage\b/i',
		'$1 phase',
		$text
	);
}

/** Same normalization as displayText(), without HTML escaping (for JSON/filter labels). */
function displayLabel($value){
	if($value === null){
		return '';
	}
	$value = trim((string)$value);
	if($value === ''){
		return '';
	}
	$value = fixLostUtf8Replacements($value);
	$value = fixUtf8Mojibake($value);
	return html_entity_decode($value, ENT_QUOTES | ENT_HTML5, 'UTF-8');
}

/*------ display protein query result ------*/
function displayProQueryRes($queryRes){
	if(!isset($queryRes->num_rows) or $queryRes->num_rows == 0){
      echo "<div class='card-body alert-danger'>Sorry, we haven't find any results with your keyword(s)!</div>";
    } 
    else{
    	$queryResNum = $queryRes->num_rows;
		echo "<div class='card-body alert-success'>There are ".$queryResNum." entries with your keyword(s).</div>";
		echo "<div class='card-body'><table class='table table-hover' data-toggle='table' data-pagination='true'>";	
		echo "<thead class='thead-dark'><tr><th data-sortable='true'>UniProt ID</th><th data-sortable='true'>Gene name</th><th data-sortable='true'>Sample</th><th data-sortable='true'>Condition</th><th data-sortable='true'>Modification</th><th>More</th></tr></thead><tbody>";
		for($i=0;$i<$queryResNum;$i++){
			$row = $queryRes->fetch_assoc();
			echo "<tr><td>".$row['up']."</td><td>".$row['gene']."</td><td>".displayText($row['sample'])."</td><td>".displayText($row['samplecondition'])."</td><td>".$row['mods']."</td><td><a target='_blank' href='result.php?uniprot=".$row['up']."'><i class='ri-external-link-fill'></i></a></td></tr>";
		}
		echo "</tbody></table></div>";
    }
}

/*------ Query need information in protein/sample/comdition table ------*/
function subQuery($subSearchTags, $subSearchKeyword, $subSearchTable, $subReturnTag, $mainSearchTag){
	$db = connectDB();
	$subQueryKeywords = array();
	$subqueryContent = array();
	foreach(explode(' ',$subSearchTags) as $subSearchTag){
		array_push($subqueryContent, $subSearchTag." like '%".$subSearchKeyword."%'");
	}

	$subQueryRes = $db->query("select ".$subReturnTag." from ".$subSearchTable." where ".implode(' or ', $subqueryContent));
	//echo "select ".$subReturnTag." from ".$subSearchTable." where ".implode(' or ', $subqueryContent)."<br>";
	$subQueryResNum = $subQueryRes->num_rows;

	if($subQueryResNum > 100){
		$db->close();
		return false;
	}

	$subQueryInfos = array();
	for($i=0;$i<$subQueryResNum;$i++){
		$subQueryRow = $subQueryRes->fetch_assoc();
		array_push($subQueryInfos, $mainSearchTag." = '".$subQueryRow[$subReturnTag]."'");
	}
	$db->close();
	return $subQueryInfos;
	
	
}

/*------ Resolve samplecondition values from qevent (exact / prefix; uses idx_samplecondition) ------*/
function resolveSampleConditionsFromQevent($keyword, $limit = 100){
	$keyword = trim((string)$keyword);
	$out = array();
	if($keyword === ''){
		return $out;
	}
	$db = connectDB();
	$kwEsc = $db->real_escape_string($keyword);
	$limit = max(1, (int)$limit);
	$queryRes = $db->query(
		"SELECT DISTINCT samplecondition FROM qevent".
		" WHERE samplecondition = '{$kwEsc}' OR samplecondition LIKE '{$kwEsc}%'".
		" LIMIT {$limit}"
	);
	if($queryRes){
		while($row = $queryRes->fetch_assoc()){
			$sc = isset($row['samplecondition']) ? (string)$row['samplecondition'] : '';
			if($sc === ''){
				continue;
			}
			$out[] = "samplecondition = '".$db->real_escape_string($sc)."'";
		}
	}
	$db->close();
	return $out;
}

/*------ Create need qevent query information ------*/
function createMainQueryInfo($tag, $keyword){
	$contableRes = array();
	$samtableRes = array();
	$protableRes = array();
	if($tag == 'pos'){
		$pos = preg_replace('/\D+/', '', trim($keyword));
		if($pos === ''){
			return '(1 = 0)';
		}
		return "(pos = '".$pos."')";
	}
	if($tag == 'uppos'){
		$keyword = trim((string)$keyword);
		if(!preg_match('/^([A-Za-z0-9-]+)\s*[#：:]\s*(\d+)\s*$/', $keyword, $m)){
			return '(1 = 0)';
		}
		$up = preg_replace('/[^A-Za-z0-9-]/', '', $m[1]);
		$pos = preg_replace('/\D+/', '', $m[2]);
		if($up === '' || $pos === ''){
			return '(1 = 0)';
		}
		return "(up = '".$up."' and pos = '".$pos."')";
	}
	if($tag == 'genepos'){
		$keyword = trim((string)$keyword);
		if(!preg_match('/^([A-Za-z0-9._-]+)\s*[#：:]\s*(\d+)\s*$/', $keyword, $m)){
			return '(1 = 0)';
		}
		$gene = preg_replace('/[^A-Za-z0-9._-]/', '', $m[1]);
		$pos = preg_replace('/\D+/', '', $m[2]);
		if($gene === '' || $pos === ''){
			return '(1 = 0)';
		}
		$db = connectDB();
		$geneEsc = $db->real_escape_string($gene);
		$db->close();
		return "(gene = '".$geneEsc."' and pos = '".$pos."')";
	}
	if($tag == 'proteinpos'){
		$keyword = trim((string)$keyword);
		if(!preg_match('/^(.+?)\s*[#：:]\s*(\d+)\s*$/u', $keyword, $m)){
			return '(1 = 0)';
		}
		$protein = trim($m[1]);
		$pos = preg_replace('/\D+/', '', $m[2]);
		if($protein === '' || $pos === ''){
			return '(1 = 0)';
		}
		$protableRes = subQuery('proteinname', $protein, 'protable', 'primaryacc', 'up');
		if($protableRes === false){
			return false;
		}
		if(count($protableRes) === 0){
			return '(1 = 0)';
		}
		return '(('.implode(' or ', $protableRes).") and pos = '".$pos."')";
	}
	if($tag == 'Context'){
		$contableRes = subQuery('con condetail', $keyword, 'contable', 'con', 'samplecondition');
		$samtableRes = subQuery('samdetail', $keyword, 'samtable', 'sam', 'sample');
		$protableRes = subQuery('uniprotaccs genename proteinname func', $keyword, 'protable', 'primaryacc', 'up');
		if($contableRes !== false){
			$fromQevent = resolveSampleConditionsFromQevent($keyword);
			if(count($fromQevent) > 0){
				$contableRes = array_values(array_unique(array_merge($contableRes, $fromQevent)));
			}
		}

		//$returnQueryInfos = array_merge($returnQueryInfos, subQuery('con condetail', $keyword, 'contable', 'con', 'samplecondition'), subQuery('samdetail', $keyword, 'samtable', 'sam', 'sample'), subQuery('uniprotaccs genename proteinname func', $keyword, 'protable', 'primaryacc', 'up'));
	}	
	elseif($tag == 'con condetail'){
		$contableRes = subQuery($tag, $keyword, 'contable', 'con', 'samplecondition');
		// contable may lag behind qevent; also resolve by samplecondition exact/prefix
		if($contableRes !== false){
			$fromQevent = resolveSampleConditionsFromQevent($keyword);
			if(count($fromQevent) > 0){
				$contableRes = array_values(array_unique(array_merge($contableRes, $fromQevent)));
			}
		}
	}
	elseif($tag == 'samdetail'){
		$samtableRes = subQuery($tag, $keyword, 'samtable', 'sam', 'sample');
		//$returnQueryInfos = array_merge($returnQueryInfos, subQuery($tag, $keyword, 'samtable', 'sam', 'sample'));
	}
	else{
		$protableRes = subQuery($tag, $keyword, 'protable', 'primaryacc', 'up');
		//$returnQueryInfos = array_merge($returnQueryInfos, subQuery($tag, $keyword, 'protable', 'primaryacc', 'up'));
	}

	if($contableRes === false){
		return false;
	}
	else if($samtableRes === false){
		return false;
	}
	else if($protableRes === false){
		return false;
	}
	else{
		$merged = array_merge($protableRes, $samtableRes, $contableRes);
		if(count($merged) === 0){
			return '(1 = 0)';
		}
		return '('.implode(' or ', $merged).')';
	}
}

/*------ Create filter form for all conditions/samples/modifications ------*/
function showSelect($allSelects){
	$selectsNumber = count($allSelects);
	$selectItem = "<select class='demo' multiple='multiple'>";
	for($i = 0;$i<$selectsNumber;$i++) 
    {
        $selectItem = $selectItem."<option value='".$allSelects[$i][0]."'>".$allSelects[$i][0]."</option>";
    }
    $selectItem = $selectItem."</select>";
    return $selectItem;
}

function getResultFilterOptions($mainQueryInfo, $appliedFilters = array()){
	$db = connectDB();
	$filterFields = array(
		'gene' => 'gene',
		'pos' => 'pos',
		'mods' => 'mods',
		'sample' => 'sample',
		'samplecondition' => 'samplecondition',
		'qptmscore' => 'qptmscore'
	);
	if(!is_array($appliedFilters)){
		$appliedFilters = array();
	}
	$filterOptions = array();
	foreach($filterFields as $key => $column){
		if($column === 'pos'){
			$orderBy = 'CAST(pos AS UNSIGNED) asc';
		}elseif($column === 'gene'){
			$orderBy = 'gene asc';
		}else{
			$orderBy = $column.' desc';
		}
		$whereParts = array('('.$mainQueryInfo.')');
		foreach($appliedFilters as $fkey => $vals){
			if($fkey === $key || !isset($filterFields[$fkey]) || !is_array($vals) || !count($vals)){
				continue;
			}
			$col = $filterFields[$fkey];
			$ors = array();
			foreach($vals as $v){
				$ors[] = $col." = '".$db->real_escape_string((string)$v)."'";
			}
			if(count($ors)){
				$whereParts[] = '('.implode(' or ', $ors).')';
			}
		}
		$whereSql = implode(' and ', $whereParts);
		$queryRes = $db->query("select ".$column." from qevent where ".$whereSql." group by ".$column." order by ".$orderBy);
		$values = array();
		if($queryRes){
			while($row = $queryRes->fetch_assoc()){
				$raw = $row[$column];
				if($key === 'samplecondition'){
					$values[] = array('value' => $raw, 'label' => displayLabel($raw));
				}else{
					$values[] = $raw;
				}
			}
		}
		$filterOptions[$key] = $values;
	}
	$db->close();
	return $filterOptions;
}

function appendQueryCount($buildResult){
	if(isset($buildResult['error'])){
		return $buildResult;
	}
	$db = connectDB();
	$countRes = $db->query("select count(*) from qevent where (".$buildResult['mainQueryInfo'].")");
	$countRow = $countRes->fetch_assoc();
	$buildResult['queryResNum'] = (int)$countRow['count(*)'];
	$db->close();
	return $buildResult;
}

/*------ Peptide display by modification ------*/
function showPep($seqwin,$type){
    return "<span class='couriernew'>".substr($seqwin,0,7)."</span><span class='modAA mod-".$type." couriernew'>".substr($seqwin,7,1)."</span><span class='couriernew'>".substr($seqwin,8,7)."</span>";
}

/*------ Sample display by its link ------*/
function sample2link($samples,$urls){
	$sam2link = array();
	if($urls=='NA' | $urls==''){
		array_push($sam2link,$samples);
		#$sam2link="<a class='tablea' style='cursor:default;color:#666'>".$samples."</a>";
	}
	else{
		#$sam2link='';
		$sam = explode('; ', $samples);
		$url = explode('; ', $urls);
		for($i=0;$i<sizeof($sam);$i++){
			if($url[$i]=='NA' | $url[$i]==''){
				array_push($sam2link,$sam[$i]);
				#$sam2link=$sam2link."<a class='tablea' style='cursor:default;color:#666'>".$sam[$i]."</a>; ";
			}
			else{
				array_push($sam2link,"<a target='_blank' href='https://web.expasy.org/cellosaurus/".$url[$i]."'>".$sam[$i]."</a>");
				#$sam2link=$sam2link."<a class='tablea' target='_blank' href='https://web.expasy.org/cellosaurus/".$url[$i]."'>".$sam[$i]."</a>; ";
			}
		}
		#$sam2link=substr($sam2link,0,strlen($sam2link)-2);
	}
	return implode('; ', $sam2link);
}

/*------ Display qPTM score ------*/
function showPTMscore($qptmscore, $fdr){
	$filledClass = ($fdr != '-') ? 'star-red' : '';
	$returnScore = '';
	for($i=0;$i<5;$i++){
		if($i < $qptmscore){
			$returnScore = $returnScore.'<i class="ri-star-s-line '.$filledClass.'"><i class="ri-star-s-fill"></i></i>';
		}
		else{
			$returnScore = $returnScore.'<i class="ri-star-s-line"></i>';
		}
	}
	return $returnScore;
}

/*------ Display modification badge ------*/
function showModBadge($mod){
	return "<span class='result-mod-badge mod-".htmlspecialchars($mod, ENT_QUOTES, 'UTF-8')."'>".$mod."</span>";
}

/*------ Display result table lines ------*/
function showResTable($displayQyeryRes){
	$displayQyeryResNum = $displayQyeryRes->num_rows;
	$returnLine = '';
	for($i = 0;$i<$displayQyeryResNum;$i++){
		$row = $displayQyeryRes->fetch_assoc();
		$rawdata = $row['mods'].'|'.$row['pmid'].'|'.$row['samplecondition'].'|'.$row['sample'].'|'.$i.'|'.$row['up'].'|'.$row['pos'].'|'.'|'.$row['qratiopro'].'|'.$row['pvaluepro'].'|'.$row['timefile'].'|'.$row['timetype'].'|'.$row['org'].'|'.$row['fdr'];
		$returnLine = $returnLine."<tr class='Table-line'>
			<td class='col-detail'><button type='button' class='detail-toggle' aria-label='Toggle detail' value=\"".$rawdata."\"><i class='ri-add-circle-fill'></i></button></td>
			<td class='col-uniprot'><a class='result-link' href='https://www.uniprot.org/uniprot/".$row['up']."' target='_blank' rel='noopener'>".$row['up']."</a></td>
			<td class='col-gene'><span class='result-gene'>".$row['gene']."</span></td>
			<td class='col-pos'>".$row['pos']."</td>
            <td class='col-mod'>".showModBadge($row['mods'])."</td>
            <td class='col-sample'>".displayText($row['sample'])."</td>
            <td class='col-condition'>".displayText($row['samplecondition'])."</td>
            <td class='col-ratio'>".displayDecimal($row['qratio'])."</td>
            <td class='col-pvalue'>".displayDecimal($row['pvalue'])."</td>
            <td class='col-score'><span class='result-score'>".showPTMscore($row['qptmscore'], $row['fdr'])."</span></td>
		</tr>
		<tr class='Detail-line'>
			<td colspan='10'><div class='detail-loading'><div class='typing-dots' aria-hidden='true'><span></span><span></span><span></span></div>Loading detail...</div></td>
		</tr>";
	}
	return $returnLine;
}

/*------ Show a button style ------*/
function showSingleButton($buttonValue, $buttonContain, $nowPage, $pageNumber){
	if($buttonContain == '<'){
		if($nowPage == 1){
			return "<li class='page-item disabled'><span class='page-link'>".$buttonContain."</span></li>";
		}
		else{
			return "<li class='page-item'><a class='page-link' href='javascript:void(0)' value='".($nowPage-1)."'>".$buttonContain."</a></li>";
		}
	}
	elseif($buttonContain == '>'){
		if($nowPage == $pageNumber){
			return "<li class='page-item disabled'><span class='page-link'>".$buttonContain."</span></li>";
		}
		else{
			return "<li class='page-item'><a class='page-link' href='javascript:void(0)' value='".($nowPage+1)."'>".$buttonContain."</a></li>";
		}
	}
	elseif($buttonContain == '...'){
		return "<li class='page-item disabled'><span class='page-link'>".$buttonContain."</span></li>";
	}
	else{
		if($buttonValue == $nowPage){
			return "<li class='page-item active'><span class='page-link'>".$buttonContain."</span></li>";
		}
		else{
			return "<li class='page-item'><a class='page-link' href='javascript:void(0)' value='".$buttonValue."'>".$buttonContain."</a></li>";
		}
	}
}

/*------ Display button line ------*/
function showPageButton($resultsNumber, $nowPage, $rowNumber){
	$pageNumber = ceil($resultsNumber/$rowNumber);
	$retunButtonInfo = '';
	if($pageNumber>1){
	    $retunButtonInfo = $retunButtonInfo."<nav aria-label='Page navigation' class='float-right'><ul class='pagination'>";
	    $retunButtonInfo = $retunButtonInfo.showSingleButton('', '<', $nowPage, $pageNumber);
	    if($pageNumber<8){
	    	for($i=1;$i<$pageNumber+1;$i++){
	    		$retunButtonInfo = $retunButtonInfo.showSingleButton($i, $i, $nowPage, $pageNumber);
	    	}
	    }
	    elseif($nowPage<5){
	    	for($i=1;$i<6;$i++){
	    		$retunButtonInfo = $retunButtonInfo.showSingleButton($i, $i, $nowPage, $pageNumber);
	    	}
	    	$retunButtonInfo = $retunButtonInfo.showSingleButton('', '...', $nowPage, $pageNumber);
	    	$retunButtonInfo = $retunButtonInfo.showSingleButton($pageNumber, $pageNumber, $nowPage, $pageNumber);
	    }
	    elseif($nowPage>$pageNumber-4){
	    	$retunButtonInfo = $retunButtonInfo.showSingleButton(1, 1, $nowPage, $pageNumber);
	    	$retunButtonInfo = $retunButtonInfo.showSingleButton('', '...', $nowPage, $pageNumber);
	    	for($i=$pageNumber-4;$i<$pageNumber+1;$i++){
	    		$retunButtonInfo = $retunButtonInfo.showSingleButton($i, $i, $nowPage, $pageNumber);
	    	}
	    }
	    else{
	    	$retunButtonInfo = $retunButtonInfo.showSingleButton(1, 1, $nowPage, $pageNumber);
	    	$retunButtonInfo = $retunButtonInfo.showSingleButton('', '...', $nowPage, $pageNumber);
	    	for($i=$nowPage-1;$i<$nowPage+2;$i++){
	    		$retunButtonInfo = $retunButtonInfo.showSingleButton($i, $i, $nowPage, $pageNumber);
	    	}
	    	$retunButtonInfo = $retunButtonInfo.showSingleButton('', '...', $nowPage, $pageNumber);
	    	$retunButtonInfo = $retunButtonInfo.showSingleButton($pageNumber, $pageNumber, $nowPage, $pageNumber);
	    }
	    $retunButtonInfo = $retunButtonInfo.showSingleButton('', '>', $nowPage, $pageNumber);
	    $retunButtonInfo = $retunButtonInfo."</ul></nav>";
	}
    return $retunButtonInfo;
}

/*----- Show page information, from 1 to 10 of 100 -----*/
function showPageInfo($queryResNum, $nowPage, $rowNumber){
	return "Showing ".($queryResNum==0?0:(($nowPage-1)*$rowNumber+1))." to ".(($nowPage*$rowNumber>$queryResNum)?$queryResNum:$nowPage*$rowNumber)." of ".$queryResNum." entries";
}

/*------ Build qevent query from search parameters ------*/
function buildSearchQueryInfo($links, $tags, $keywords, $mods, $orgs){
	$mainQueryInfos = array();
	$tag2item = array("Context"=>"Any Field","uniprotaccs"=>"UniProt Accession","uppos"=>"UniProt ID#Position","genename"=>"Gene Name","genepos"=>"Gene Name#Position","proteinname"=>"Protein Name","proteinpos"=>"Protein Name#Position","pos"=>"Position","func"=>"Function","con condetail"=>"Condition","samdetail"=>"Sample");
	$queryContents = array();
	for($i=0;$i<count($tags);$i++){
		array_push($queryContents, ' '.$links[$i].' ');
		array_push($queryContents, $tag2item[$tags[$i]].' = '.$keywords[$i]);

		array_push($mainQueryInfos, ' '.$links[$i].' ');
		$createMainQueryInfoRes = createMainQueryInfo($tags[$i], $keywords[$i]);
		if($createMainQueryInfoRes === false){
			return array('error' => "There are too many matched records with your keyword(s) in '".$tag2item[$tags[$i]]."', please provide a more detailed search plan.");
		}
		array_push($mainQueryInfos, $createMainQueryInfoRes);
	}
	$queryContent = implode('', $queryContents);
	$mainQueryInfo = implode('', $mainQueryInfos);

	$queryContent = 'Search content: '.$queryContent.'; Organism: '.$orgs.'; Modification: '.$mods;
	if($mods != 'All'){
		$mainQueryInfo = $mainQueryInfo." and mods ='".$mods."'";
	}
	if($orgs != 'All'){
		$mainQueryInfo = $mainQueryInfo." and org ='".$orgs."'";
	}

	return array('mainQueryInfo' => $mainQueryInfo, 'queryContent' => $queryContent);
}

/*------ Build qevent query from browse parameters ------*/
function buildBrowseQueryInfo($tag, $keyword, $mods, $orgs){
	$tag2tableIndex = array("condition"=>"samplecondition","gene"=>"gene","sample"=>"sample","up"=>'up');
	$tag2item = array("condition"=>"Condition","gene"=>"Gene name","sample"=>"Sample","up"=>"UniProt ID");
	if(!isset($tag2tableIndex[$tag])){
		return array('error' => 'Invalid browse tag.');
	}
	$keyword = trim($keyword);
	$mainQueryInfo = $tag2tableIndex[$tag]." = '".$keyword."'";
	$queryContent = 'Search content: '.$tag2item[$tag]." = ".$keyword.'; Organism: '.$orgs.'; Modification: '.$mods;
	if($mods != 'All'){
		$mainQueryInfo = $mainQueryInfo." and mods ='".$mods."'";
	}
	if($orgs != 'All'){
		$mainQueryInfo = $mainQueryInfo." and org ='".$orgs."'";
	}
	return array('mainQueryInfo' => $mainQueryInfo, 'queryContent' => $queryContent);
}

/*------ Search the qevent table and return result ------*/
function searchDB($links, $tags, $keywords, $mods, $orgs){
	$buildResult = buildSearchQueryInfo($links, $tags, $keywords, $mods, $orgs);
	if(isset($buildResult['error'])){
		echo "<div class='card-body alert-danger'>".$buildResult['error']."</div>";
		return false;
	}
	queryAndDisplay($buildResult['mainQueryInfo'], $buildResult['queryContent']);
}
function queryAndDisplay($mainQueryInfo, $queryContent){
	$db = connectDB();	
	$queryRes = $db->query("select * from qevent where (".$mainQueryInfo.") order by timetype desc, qptmscore desc, up, pos limit 0, 10");
	$queryResAll = $db->query("select count(*) from qevent where (".$mainQueryInfo.")");

	echo "<span id='rawQueryInfo' style='display:none'>".$mainQueryInfo."</span>";
	echo "<div class='card-body alert-primary'>".$queryContent."</div>";

	if(!isset($queryResAll->num_rows)){
		$queryResNum = 0;
	}
	else{
		$queryResNum = $queryResAll->fetch_assoc()['count(*)'];
	}
	if($queryResNum == 0){
		echo "<div class='card-body alert-danger'>Sorry, we haven't find any results with your keyword(s)!</div>";
	}
	else{
		$allQueryConditions = mysqli_fetch_all($db->query("select samplecondition from qevent where (".$mainQueryInfo.") group by samplecondition"), MYSQLI_NUM);
		$allQuerySamples = mysqli_fetch_all($db->query("select sample from qevent where (".$mainQueryInfo.") group by sample"), MYSQLI_NUM);
		$allQueryMods = mysqli_fetch_all($db->query("select mods from qevent where (".$mainQueryInfo.") group by mods"), MYSQLI_NUM);
		$nowPage = 1;
		$rowNumber = 10;
		echo "<div class='card-body alert-success'>There are ".$queryResNum." entries with your keyword(s).</div>";

/*------ Before table part start ------*/
/*------ Filter form for condition/sample/modification ------*/
		echo "<div class='card-body'>
		<div class='row'>
		<div class='col-md-10'>
			<div class='filter-div' value='samplecondition'><span class='filter-label text-center'>Condition</span>".showSelect($allQueryConditions)."<i class='unselected selectedall'></i></div>
			<div class='filter-div' value='sample'><span class='filter-label text-center'>Sample</span>".showSelect($allQuerySamples)."<i class='unselected selectedall'></i></div>
			<div class='filter-div' value='mods'><span class='filter-label text-center'>Modification</span>".showSelect($allQueryMods)."<i class='unselected selectedall'></i></div>
		</div>
		<div class='col-md-2'><button type='button' class='form-control btn btn-mine btn-sm' id='filterButton'>Filter</button></div>
		</div><hr>";

/*------ Number of entries per line and download results ------*/
		echo"<div class='row'>
		<div class='col-md-10'>
			<span class='mod-name'><span class='couriernew modAA mod-Phosphorylation'>A</span>-Phosphorylation</span>
        	<span class='mod-name'><span class='couriernew modAA mod-Acetylation'>A</span>-Acetylation</span>
        	<span class='mod-name'><span class='couriernew modAA mod-Methylation'>A</span>-Metylation</span>
        	<span class='mod-name'><span class='couriernew modAA mod-Ubiquitylation'>A</span>-Ubiquitylation</span>
        	<span class='mod-name'><span class='couriernew modAA mod-Glycosylation'>A</span>-Glycosylation</span>
        	<span class='mod-name'><span class='couriernew modAA mod-SUMOylation'>A</span>-SUMOylation</span>
		</div>
		<div class='col-md-2'><button type='button' class='form-control btn btn-mine btn-sm' id='download_button'>Download</button></div>
		</div>
		</div>";
/*------ Before table part end ------*/

/*------ Result table part start------*/
/*------ Fixed table head------*/
		echo "
		<table class='table table-responsive-sm text-center resultTable'>
		<thead class='thead-dark'><tr>
			<th width='7%'>Detail</th>
    		<th class='arrange' value='up' width='7%'>UniProt<i class='arrow ri-arrow-up-down-fill'></i></th>
    		<th class='arrange' value='gene' width='7%'>Gene<i class='arrow ri-arrow-up-down-fill'></i></th>
    		<th class='arrange' value='pos' width='7%'>Position<i class='arrow ri-arrow-up-down-fill'></i></th>
            <th class='arrange' value='mods' width='12%'>Modification<i class='arrow ri-arrow-up-down-fill'></i></th>
    		<th class='arrange' value='sample' width='12%'>Sample<i class='arrow ri-arrow-up-down-fill'></i></th>       		
    		<th class='arrange' value='samplecondition' width='14%'>Condition<i class='arrow ri-arrow-up-down-fill'></i></th>       		
            <th class='arrange' value='qratio' width='9%'>Log2Ratio<i class='arrow ri-arrow-up-down-fill'></i></th>
    		<th class='arrange' value='pvalue' width='9%'><i>P</i>&nbspvalue<i class='arrow ri-arrow-up-down-fill'></i></th>
    		<th class='arrange' value='qptmscore' width='12%'>Reliability <a href='help.html#help-reliability' class='th-help-link' title='About reliability scoring' aria-label='About reliability scoring'><i class='ri-error-warning-line'></i></a><i class='arrow ri-arrow-up-down-fill'></i></th>
		</tr></thead>
		<thead class='table-light table-sm'><tr>
			<th><div class='form-control form-control-sm border-0'><i class='ri-search-line'></i></div></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='up'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='gene'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='pos'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='mods'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='sample'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='samplecondition'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='qratio'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='pvalue'></th>
            <th></th>
		</tr></thead>
		<tbody id='tableChange'>
			".showResTable($queryRes)."
		</tbody>
		</table>";
/*------ Changed page button------*/
		echo "<div class='card-body'><div class='row'>
		<div class='col-md-6'>
			<span id='pageInfo'>".showPageInfo($queryResNum, $nowPage, $rowNumber)."</span><span>, <select id='selectRowNumber'><option value='10'>10</option><option value='20'>20</option><option value='50'>50</option><option value='100'>100</option></select> entries per page</span>
		</div>
		<div class='col-md-6' id='pageButton'>
			".showPageButton($queryResNum, $nowPage, $rowNumber)."
		</div>
		</div></div>";
/*------ Result table part end------*/
	}

	//displayProQueryRes($queryRes);
	$db->close();
}

/*------ Ad links to some IDs, including UniProt ID, entrez, genebank protein/nucleotide ID etc.------*/
function ID2links($headLink, $IDs){
	$linkInfos = array();
	foreach($IDs as $ID){
		array_push($linkInfos, "<a href='".$headLink.$ID."' target='_blank'>".$ID."</a>");
	}
	return implode(', ', $linkInfos);
}

/** Human-readable Condition type labels (Browse / result detail). */
function contrastTypeLabel($type){
	$map = array(
		'pharmacological' => 'Pharmacological',
		'genetic' => 'Genetic',
		'physical' => 'Physical',
		'disease' => 'Disease',
		'cell_state' => 'Cell state',
		'other' => 'Other'
	);
	$key = strtolower(trim((string)$type));
	return isset($map[$key]) ? $map[$key] : trim((string)$type);
}

/** Build external URL for an ontology CURIE (e.g. ChEBI:45716). */
function ontologyIdUrl($curie){
	$curie = trim((string)$curie);
	if($curie === '' || strpos($curie, ':') === false){
		return '';
	}
	$parts = explode(':', $curie, 2);
	$prefix = strtoupper(trim($parts[0]));
	$id = trim($parts[1]);
	if($id === ''){
		return '';
	}
	switch($prefix){
		case 'CHEBI':
			$num = preg_replace('/^CHEBI:/i', '', $id);
			if(stripos($id, 'CHEBI:') === 0){
				$num = substr($id, 6);
			}
			return 'https://www.ebi.ac.uk/chebi/searchId.do?chebiId=CHEBI:'.rawurlencode($num);
		case 'PUBCHEM':
			return 'https://pubchem.ncbi.nlm.nih.gov/compound/'.rawurlencode($id);
		case 'DOID':
			return 'https://disease-ontology.org/?id=DOID:'.rawurlencode(preg_replace('/^DOID:/i', '', $id));
		case 'HGNC':
			return 'https://www.genenames.org/data/gene-symbol-report/#!/hgnc_id/HGNC:'.rawurlencode($id);
		case 'UNIPROT':
			return 'https://www.uniprot.org/uniprotkb/'.rawurlencode($id);
		case 'CELLOSAURUS':
			return 'https://www.cellosaurus.org/'.rawurlencode($id);
		case 'MESH':
			return 'https://meshb.nlm.nih.gov/record/ui?ui='.rawurlencode($id);
		case 'GO':
			return 'https://amigo.geneontology.org/amigo/term/GO:'.rawurlencode($id);
		case 'SGD':
			return 'https://www.yeastgenome.org/locus/'.rawurlencode($id);
		case 'NCIT':
			return 'https://ncit.nci.nih.gov/ncitbrowser/ConceptReport.jsp?dictionary=NCI_Thesaurus&code='.rawurlencode($id);
		case 'NCBITAXON':
			return 'https://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?id='.rawurlencode($id);
		default:
			return '';
	}
}

/** Render ontology_id pipe list as external links. */
function formatOntologyLinks($ontologyId){
	$ontologyId = trim((string)$ontologyId);
	if($ontologyId === ''){
		return '';
	}
	$bits = preg_split('/\s*\|\s*/', $ontologyId);
	$links = array();
	foreach($bits as $bit){
		$bit = trim($bit);
		if($bit === ''){ continue; }
		$url = ontologyIdUrl($bit);
		$label = htmlspecialchars($bit, ENT_QUOTES, 'UTF-8');
		if($url !== ''){
			$links[] = "<a href='".htmlspecialchars($url, ENT_QUOTES, 'UTF-8')."' target='_blank' rel='noopener'>".$label."</a>";
		}else{
			$links[] = $label;
		}
	}
	return implode(' · ', $links);
}

/**
 * HTML rows for Condition type + Condition ontology
 * after Detail condition in result experiment detail.
 */
/** Escape a value for tab-delimited download rows. */
function tsvCell($value){
	if($value === null){
		return '';
	}
	$value = trim((string)$value);
	if($value === '' || $value === '-'){
		return '';
	}
	return str_replace(array("\t", "\r", "\n"), ' ', $value);
}

/** Column headers for Search result downloads (includes Experiment information fields). */
function downloadResultHeader(){
	return array(
		'UniProt',
		'Gene',
		'Position',
		'Modification',
		'Organism',
		'PMID',
		'Resource',
		'Detail condition',
		'Condition type',
		'Condition ontology',
		'Condition',
		'Sample',
		'Sample type',
		'Label method',
		'Enrichment method',
		'Mass spectrometer',
		'Log2Ratio',
		'pvalue',
		'Related protein Log2Ratio',
		'Related protein pvalue',
		'Has time course',
		'Reported PEP/Localization probability',
		'Reliability',
		'Re-identified FDR',
		'Identified times in qPTM',
		'Collected in PhosphoSitePlus',
		'Collected in dbPTM',
		'Collected in PTMAtlas',
	);
}

/**
 * Preload small Experimental-information lookup tables for result downloads.
 * scoretable is too large and is fetched in batches separately.
 */
function loadDownloadExperimentalMaps($db){
	$maps = array(
		'exp' => array(),
		'sam' => array(),
		'con' => array(),
		'ann' => array(),
		'dict' => array(),
	);

	$res = @$db->query("SELECT pmid, mods, tit, labelmethod, enrichmethod, msmethod FROM exptable");
	if($res){
		while($r = $res->fetch_assoc()){
			$maps['exp'][$r['pmid']."\t".$r['mods']] = $r;
		}
	}

	$res = @$db->query("SELECT sam, samtype FROM samtable");
	if($res){
		while($r = $res->fetch_assoc()){
			$maps['sam'][$r['sam']] = isset($r['samtype']) ? (string)$r['samtype'] : '';
		}
	}

	$res = @$db->query("SELECT pmid, con, condetail FROM contable");
	if($res){
		while($r = $res->fetch_assoc()){
			$maps['con'][$r['pmid']."\t".$r['con']] = isset($r['condetail']) ? (string)$r['condetail'] : '';
		}
	}

	$res = @$db->query("SELECT pmid, con, contrast_type, agent_key, agent_raw, gene, perturbation FROM con_annotation");
	if($res){
		while($r = $res->fetch_assoc()){
			$maps['ann'][$r['pmid']."\t".$r['con']] = $r;
			$conOnly = "\t".$r['con'];
			if(!isset($maps['ann'][$conOnly])){
				$maps['ann'][$conOnly] = $r;
			}
		}
	}

	$res = @$db->query("SELECT agent_key, preferred_name, ontology_id FROM agent_dictionary");
	if($res){
		while($r = $res->fetch_assoc()){
			$maps['dict'][$r['agent_key']] = $r;
		}
	}

	return $maps;
}

/** Batch-load scoretable rows by scoreid. */
function fetchScoreRowsByIds($db, $ids){
	$out = array();
	$ids = array_values(array_unique(array_filter(array_map('strval', $ids))));
	$chunkSize = 500;
	$total = count($ids);
	for($i = 0; $i < $total; $i += $chunkSize){
		$chunk = array_slice($ids, $i, $chunkSize);
		$escaped = array();
		foreach($chunk as $id){
			$escaped[] = "'".$db->real_escape_string($id)."'";
		}
		$res = $db->query("SELECT scoreid, prob, ispsp, isdbptm, isptmatlas FROM scoretable WHERE scoreid IN (".implode(',', $escaped).")");
		if($res){
			while($r = $res->fetch_assoc()){
				$out[$r['scoreid']] = $r;
			}
		}
	}
	return $out;
}

/** Resolve condition type / ontology labels for a download row. */
function resolveDownloadConditionAnnotation($pmid, $con, $maps){
	$typeLabel = '';
	$pert = '';
	$factor = '';
	$ann = null;
	$key = $pmid."\t".$con;
	if(isset($maps['ann'][$key])){
		$ann = $maps['ann'][$key];
	}elseif(isset($maps['ann']["\t".$con])){
		$ann = $maps['ann']["\t".$con];
	}
	if(is_array($ann)){
		$typeLabel = contrastTypeLabel(isset($ann['contrast_type']) ? $ann['contrast_type'] : '');
		$pert = isset($ann['perturbation']) ? trim((string)$ann['perturbation']) : '';
		$agentKey = isset($ann['agent_key']) ? trim((string)$ann['agent_key']) : '';
		$agentRaw = isset($ann['agent_raw']) ? trim((string)$ann['agent_raw']) : '';
		$gene = isset($ann['gene']) ? trim((string)$ann['gene']) : '';
		if($agentKey !== '' && isset($maps['dict'][$agentKey])){
			$dict = $maps['dict'][$agentKey];
			$factor = trim((string)(isset($dict['preferred_name']) ? $dict['preferred_name'] : ''));
			$ontologyId = trim((string)(isset($dict['ontology_id']) ? $dict['ontology_id'] : ''));
			if($factor !== '' && $ontologyId !== ''){
				$factor .= ' ('.$ontologyId.')';
			}elseif($factor === '' && $ontologyId !== ''){
				$factor = $ontologyId;
			}
		}
		if($factor === ''){
			$factor = ($gene !== '' ? $gene : $agentRaw);
		}
	}
	$typeCell = $typeLabel;
	if($typeLabel !== '' && $pert !== '' && $pert !== 'other' && $pert !== 'drug' && $pert !== 'disease' && $pert !== 'stimulus'){
		$typeCell .= ' ('.$pert.')';
	}
	return array($typeCell, $factor);
}

/** Normalize free-text for download (encoding fixes used on the result page). */
function downloadTextField($value){
	return displayLabel($value);
}

/** Build one enriched download line matching Experiment information on the result page. */
function formatDownloadResultRow($row, $maps, $score = null){
	$pmid = isset($row['pmid']) ? (string)$row['pmid'] : '';
	$mods = isset($row['mods']) ? (string)$row['mods'] : '';
	$con = isset($row['samplecondition']) ? (string)$row['samplecondition'] : '';
	$sample = isset($row['sample']) ? (string)$row['sample'] : '';
	$org = isset($row['org']) ? (string)$row['org'] : '';

	$exp = isset($maps['exp'][$pmid."\t".$mods]) ? $maps['exp'][$pmid."\t".$mods] : null;
	$condetail = isset($maps['con'][$pmid."\t".$con]) ? $maps['con'][$pmid."\t".$con] : '';
	$samtype = isset($maps['sam'][$sample]) ? $maps['sam'][$sample] : '';
	list($typeCell, $factorCell) = resolveDownloadConditionAnnotation($pmid, $con, $maps);

	$timetype = isset($row['timetype']) ? (string)$row['timetype'] : '0';
	$hasTimeCourse = ($timetype !== '' && $timetype !== '0') ? 'Yes' : 'No';

	$qptmcount = isset($row['qptmcount']) ? (string)$row['qptmcount'] : '';
	$prob = '';
	$ispsp = '';
	$isdbptm = '';
	$isptmatlas = '';
	if(is_array($score)){
		$prob = isset($score['prob']) ? str_replace('#', ': ', (string)$score['prob']) : '';
		$ispsp = isset($score['ispsp']) ? (string)$score['ispsp'] : '';
		$isdbptm = isset($score['isdbptm']) ? (string)$score['isdbptm'] : '';
		$isptmatlas = isset($score['isptmatlas']) ? (string)$score['isptmatlas'] : '';
	}

	$cells = array(
		$row['up'] ?? '',
		$row['gene'] ?? '',
		$row['pos'] ?? '',
		$row['mods'] ?? '',
		$org,
		$pmid,
		downloadTextField(is_array($exp) && isset($exp['tit']) ? $exp['tit'] : ''),
		downloadTextField(fixCellCyclePhageDisplay($condetail)),
		downloadTextField($typeCell),
		downloadTextField($factorCell),
		downloadTextField($con),
		downloadTextField($sample),
		downloadTextField($samtype),
		downloadTextField(is_array($exp) && isset($exp['labelmethod']) ? $exp['labelmethod'] : ''),
		downloadTextField(is_array($exp) && isset($exp['enrichmethod']) ? $exp['enrichmethod'] : ''),
		downloadTextField(is_array($exp) && isset($exp['msmethod']) ? $exp['msmethod'] : ''),
		$row['qratio'] ?? '',
		$row['pvalue'] ?? '',
		$row['qratiopro'] ?? '',
		$row['pvaluepro'] ?? '',
		$hasTimeCourse,
		downloadTextField($prob),
		$row['qptmscore'] ?? '',
		$row['fdr'] ?? '',
		$qptmcount,
		$ispsp,
		$isdbptm,
		$isptmatlas,
	);
	return implode("\t", array_map('tsvCell', $cells));
}

/** Write a batch of qevent rows with Experimental information enrichment. */
function writeDownloadResultBatch($handle, $db, $batch, $maps){
	$scoreIds = array();
	foreach($batch as $row){
		$scoreIds[] = ($row['org'] ?? '').'#'.($row['pmid'] ?? '').'#'.($row['up'] ?? '').'#'.($row['pos'] ?? '').'#'.($row['mods'] ?? '');
	}
	$scores = fetchScoreRowsByIds($db, $scoreIds);
	foreach($batch as $row){
		$sid = ($row['org'] ?? '').'#'.($row['pmid'] ?? '').'#'.($row['up'] ?? '').'#'.($row['pos'] ?? '').'#'.($row['mods'] ?? '');
		$score = isset($scores[$sid]) ? $scores[$sid] : null;
		fwrite($handle, formatDownloadResultRow($row, $maps, $score)."\n");
	}
}

function buildConditionAnnotationRows($db, $pmid, $con){
	$pmidEsc = $db->real_escape_string((string)$pmid);
	$conEsc = $db->real_escape_string((string)$con);
	$annRes = @$db->query(
		"SELECT contrast_type, agent_key, agent_raw, gene, perturbation, parse_confidence
		 FROM con_annotation
		 WHERE pmid='{$pmidEsc}' AND con='{$conEsc}'
		 LIMIT 1"
	);
	if(!$annRes || !$annRes->num_rows){
		// Fall back: same condition name may share annotation across PMIDs
		$annRes = @$db->query(
			"SELECT contrast_type, agent_key, agent_raw, gene, perturbation, parse_confidence
			 FROM con_annotation
			 WHERE con='{$conEsc}'
			 LIMIT 1"
		);
	}

	$typeLabel = '';
	$pert = '';
	$factorName = '';
	$ontologyHtml = '';
	if($annRes && $annRes->num_rows){
		$ann = $annRes->fetch_assoc();
		$typeLabel = contrastTypeLabel(isset($ann['contrast_type']) ? $ann['contrast_type'] : '');
		$pert = isset($ann['perturbation']) ? trim((string)$ann['perturbation']) : '';
		$agentKey = isset($ann['agent_key']) ? trim((string)$ann['agent_key']) : '';
		$agentRaw = isset($ann['agent_raw']) ? trim((string)$ann['agent_raw']) : '';
		$gene = isset($ann['gene']) ? trim((string)$ann['gene']) : '';
		if($agentKey !== ''){
			$akEsc = $db->real_escape_string($agentKey);
			$dictRes = @$db->query(
				"SELECT preferred_name, ontology_id, entity_type, agent_class
				 FROM agent_dictionary WHERE agent_key='{$akEsc}' LIMIT 1"
			);
			if($dictRes && $dictRes->num_rows){
				$dict = $dictRes->fetch_assoc();
				$factorName = trim((string)(isset($dict['preferred_name']) ? $dict['preferred_name'] : ''));
				$ontologyHtml = formatOntologyLinks(isset($dict['ontology_id']) ? $dict['ontology_id'] : '');
			}
		}
		if($factorName === ''){
			$factorName = ($gene !== '' ? $gene : $agentRaw);
		}
	}

	$typeCell = ($typeLabel !== '') ? displayText($typeLabel) : '-';
	if($typeLabel !== '' && $pert !== '' && $pert !== 'other' && $pert !== 'drug' && $pert !== 'disease' && $pert !== 'stimulus'){
		$typeCell .= " <span class='text-muted' style='font-weight:normal'>(".displayText($pert).")</span>";
	}

	if($factorName !== ''){
		$factorCell = displayText($factorName);
		if($ontologyHtml !== ''){
			$factorCell .= " <span class='text-muted' style='margin-left:0.35rem'>(".$ontologyHtml.")</span>";
		}
	}elseif($ontologyHtml !== ''){
		$factorCell = $ontologyHtml;
	}else{
		$factorCell = '-';
	}

	return "<tr><td>Condition type</td><td colspan='6'>".$typeCell."</td></tr>"
		."<tr><td>Condition ontology</td><td colspan='6'>".$factorCell."</td></tr>";
}

/*------ Add tips to PubMed info in function description------*/
function displayFuncDes($funcDes){
	$pattern = "/\((PubMed:[0-9]*,? *)+\)/";
	preg_match_all($pattern, $funcDes, $matches);
	if($matches){
		foreach($matches[0] as $match){
			$PMIDs = explode(',', str_replace(')','',str_replace('(','',$match)));
			$PMIDLinks = array();	
			foreach($PMIDs as $PMID){
				$pmid = explode(':', $PMID)[1];
				array_push($PMIDLinks, "<a href='https://www.ncbi.nlm.nih.gov/pubmed/?term=".$pmid."' target='_blank' >".$pmid."</a>");
			}
			$replace = "<a tabindex='0' href='javascript:void(0)' class='pubmed-ref' data-toggle='popover' data-trigger='focus' data-html=true title='Related literature(s)' data-content=\"".implode('<br>', $PMIDLinks)."\">".count($PMIDs)."</a>";
			$funcDes = str_replace($match,$replace,$funcDes);
		}
	}
	return $funcDes;
}

/*------ Parse PTMs_other_resource from proinfo ------*/
function parsePtmsOtherResource($raw){
	$raw = trim((string)$raw);
	if($raw === ''){
		return array();
	}
	$rows = array();
	$parts = explode(';', $raw);
	foreach($parts as $part){
		$part = trim($part);
		if($part === ''){
			continue;
		}
		if(!preg_match('/^(.+?):([\d,]+)\(([^)]+)\)$/', $part, $matches)){
			continue;
		}
		$mod = trim($matches[1]);
		$source = trim($matches[3]);
		$positions = explode(',', $matches[2]);
		foreach($positions as $pos){
			$pos = trim($pos);
			if($pos === '' || !ctype_digit($pos)){
				continue;
			}
			$rows[] = array(
				'mods' => $mod,
				'pos' => $pos,
				'source' => $source
			);
		}
	}
	usort($rows, function($a, $b){
		$posCmp = (int)$a['pos'] - (int)$b['pos'];
		if($posCmp !== 0){
			return $posCmp;
		}
		$modCmp = strcmp($a['mods'], $b['mods']);
		if($modCmp !== 0){
			return $modCmp;
		}
		return strcmp($a['source'], $b['source']);
	});
	return $rows;
}

/** Count PTM site rows without building the full sorted table. */
function countPtmsOtherResource($raw){
	$raw = trim((string)$raw);
	if($raw === ''){
		return 0;
	}
	$count = 0;
	foreach(explode(';', $raw) as $part){
		$part = trim($part);
		if($part === '' || !preg_match('/^(.+?):([\d,]+)\(([^)]+)\)$/', $part, $matches)){
			continue;
		}
		foreach(explode(',', $matches[2]) as $pos){
			$pos = trim($pos);
			if($pos !== '' && ctype_digit($pos)){
				$count++;
			}
		}
	}
	return $count;
}

/** Placeholder for large detail tables loaded on expand. */
function lazyDetailTablePlaceholder($kind, $uniprot){
	$kind = preg_replace('/[^a-z_]/', '', (string)$kind);
	$upEsc = htmlspecialchars(trim((string)$uniprot), ENT_QUOTES, 'UTF-8');
	return "<div class='detail-table-scroll hide-more lazy-detail-table is-loading' data-lazy='".$kind."' data-up='".$upEsc."' data-loaded='0'>"
		."<div class='structure-viewer-loading detail-table-loading'>"
		."<span class='structure-spinner' aria-hidden='true'></span>"
		."<span>Loading table...</span>"
		."</div></div>";
}

/*------ Display external PTM resources in a table ------*/
function formatPtmResourceSource($source){
	$source = trim((string)$source);
	if($source === ''){
		return '-';
	}
	$map = array(
		'phosphositeplus' => array('PhosphoSitePlus', 'https://www.phosphosite.org'),
		'dbptm' => array('dbPTM', 'https://biomics.lab.nycu.edu.tw/dbPTM/'),
		'ptmatlas' => array('PTMAtlas', 'https://deepmvp.ptmax.org/'),
		'cplm' => array('CPLM', 'http://cplm.biocuckoo.cn/'),
		'uniprot' => array('UniProt', 'https://www.uniprot.org/'),
		'glycositeatlas' => array('GlycositeAtlas', 'http://nglycositeatlas.biomarkercenter.org/'),
	);
	$parts = preg_split('/[;,]/', $source);
	$links = array();
	foreach($parts as $part){
		$part = trim($part);
		if($part === ''){
			continue;
		}
		$key = strtolower($part);
		if(isset($map[$key])){
			$links[] = "<a href='".$map[$key][1]."' target='_blank' rel='noopener'>".htmlspecialchars($map[$key][0])."</a>";
		}else{
			$links[] = htmlspecialchars($part);
		}
	}
	return $links ? implode(', ', $links) : '-';
}

function displayPTM($ptmRows){
	if(!is_array($ptmRows) || count($ptmRows) === 0){
		return '-';
	}
	$returnPTMInfos = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table'><thead class='thead-dark'><tr><th style='width:45%'>Modification</th><th style='width:20%'>Position</th><th style='width:35%'>Source</th></tr></thead><tbody>";
	foreach($ptmRows as $row){
		$returnPTMInfos = $returnPTMInfos."<tr><td>".htmlspecialchars($row['mods'])."</td><td>".htmlspecialchars($row['pos'])."</td><td>".formatPtmResourceSource($row['source'])."</td></tr>";
	}
	$returnPTMInfos = $returnPTMInfos."</tbody></table></div>";
	return $returnPTMInfos;
}


/*------ Display PTMD information in a table------*/
function formatPtmdSource($source){
	$source = trim((string)$source);
	$parts = ($source === '') ? array() : preg_split('/[;,]/', $source);
	$links = array();
	$hasPtmd = false;
	foreach($parts as $part){
		$part = trim($part);
		if($part === ''){
			continue;
		}
		if(preg_match('/^\d+$/', $part)){
			$links[] = "<a href='https://pubmed.ncbi.nlm.nih.gov/".$part."/' target='_blank' rel='noopener'>".$part."</a>";
		}elseif(strcasecmp($part, 'ActiveDriverDB') === 0){
			$links[] = "<a href='https://activedriverdb.org/' target='_blank' rel='noopener'>".htmlspecialchars($part)."</a>";
		}elseif(strcasecmp($part, 'PTMD') === 0){
			$hasPtmd = true;
			$links[] = "<a href='https://ptmd.biocuckoo.cn/' target='_blank' rel='noopener'>PTMD</a>";
		}else{
			$links[] = htmlspecialchars($part);
		}
	}
	// Disease and variants rows are curated from PTMD; always show PTMD as a source.
	if(!$hasPtmd){
		$links[] = "<a href='https://ptmd.biocuckoo.cn/' target='_blank' rel='noopener'>PTMD</a>";
	}
	return $links ? implode(', ', $links) : '-';
}

function fetchPtmdRows($ptmdQueryRes){
	$rows = array();
	if(!$ptmdQueryRes || !isset($ptmdQueryRes->num_rows) || $ptmdQueryRes->num_rows == 0){
		return $rows;
	}
	while($row = $ptmdQueryRes->fetch_assoc()){
		$rows[] = $row;
	}
	return $rows;
}

function displayPTMD($ptmdRows){
	if(!is_array($ptmdRows) || count($ptmdRows) === 0){
		return '-';
	}
	$returnPTMDInfos = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table'><thead class='thead-dark'><tr><th style='width:20%'>Modification</th><th style='width:12%'>Position</th><th style='width:18%'>Influence</th><th style='width:28%'>Disease</th><th style='width:22%'>Source</th></tr></thead><tbody>";
	foreach($ptmdRows as $row){
		$returnPTMDInfos = $returnPTMDInfos."<tr><td>".htmlspecialchars($row['mods'])."</td><td>".htmlspecialchars($row['pos'])."</td><td>".htmlspecialchars($row['influ'])."</td><td>".htmlspecialchars($row['disease'])."</td><td>".formatPtmdSource($row['pmid'])."</td></tr>";
	}
	$returnPTMDInfos = $returnPTMDInfos."</tbody></table></div>";
	return $returnPTMDInfos;
}

/*------ Display protein sequence------*/
function displaySequence($sequence){
	$seqStart = 0;
	$seqLength = 10;
	$rowNum = 5; // 5 × 10 = 50 amino acids per row
	$rowCount = 0;
	$returnSeqInfos = "<div class='sequence-scroll'><table class='table-borderless seq-table'><thead><tr>";
	for($i=0;$i<$rowNum;$i++){
		$returnSeqInfos = $returnSeqInfos."<th></th>";
	}
	$returnSeqInfos = $returnSeqInfos."</tr></thead><tbody>";

	while($seqStart < strlen($sequence)){
		$rowCount += 1;
		if($rowCount ==1){
			$returnSeqInfos = $returnSeqInfos."<tr>";
		}

		$chunkLen = min($seqLength, strlen($sequence) - $seqStart);
		$chunkText = substr($sequence, $seqStart, $chunkLen);
		$seqPos = $seqStart + $chunkLen;
		$posLabel = ($seqPos % 10 === 0) ? (string)$seqPos : '&nbsp;';
		$returnSeqInfos = $returnSeqInfos."<td class='seq-chunk' style='width:".$chunkLen."ch'><p class='seq-pos'>".$posLabel."</p><p class='seq-pep couriernew'>".$chunkText."</p></td>";

		if($rowCount ==$rowNum){
			$returnSeqInfos = $returnSeqInfos."</tr>";
			$rowCount =0;
		}
		$seqStart += $seqLength;
	}
	while($rowCount > 0 && $rowCount < $rowNum){
		$rowCount += 1;
		$returnSeqInfos = $returnSeqInfos."<td></td>";

		if($rowCount ==$rowNum){
			$returnSeqInfos = $returnSeqInfos."</tr>";
			$rowCount =0;
		}
	}
	$returnSeqInfos = $returnSeqInfos."</tbody></table></div>";
	return $returnSeqInfos;
}

function drugBankStructureUrl($drugId){
	return 'https://go.drugbank.com/structures/'.rawurlencode(trim($drugId)).'/image.svg';
}

function drugBankDrugUrl($drugId){
	return 'https://go.drugbank.com/drugs/'.rawurlencode(trim($drugId));
}

function displayDrugBankStructure($drugId){
	$drugId = trim($drugId);
	if($drugId === '' || $drugId === '-'){
		return '-';
	}
	$structureUrl = drugBankStructureUrl($drugId);
	$drugUrl = drugBankDrugUrl($drugId);
	$safeDrugId = htmlspecialchars($drugId, ENT_QUOTES, 'UTF-8');
	$safeStructureUrl = htmlspecialchars($structureUrl, ENT_QUOTES, 'UTF-8');
	$safeDrugUrl = htmlspecialchars($drugUrl, ENT_QUOTES, 'UTF-8');
	return "<a href='".$safeDrugUrl."' target='_blank' rel='noopener noreferrer'><img src='".$safeStructureUrl."' class='drug-structure-thumb' width='50' height='50' loading='lazy' alt='".$safeDrugId." structure' onerror=\"this.classList.add('is-broken');this.alt='Structure unavailable'\"></a>";
}

function displayDrugBankLink(){
	return "<a href='https://go.drugbank.com/' target='_blank' rel='noopener noreferrer'>DrugBank</a>";
}

require_once __DIR__.'/agent_sqlite.php';

/**
 * Parse one enzyme annotation chunk.
 * Supports:
 *   Exp:  GENE@Source@detail#drugs
 *   GPS:  hierarchy#GENE@score#drugs   (or hierarchy#GENE#drugs)
 *   Ub:   E3GENE@class@pmids#
 *   legacy: LABEL#drugs
 */
function parseEnzymeChunk($chunk){
	$chunk = trim((string)$chunk);
	$empty = array(
		'label' => '',
		'gene' => '',
		'score' => '',
		'source' => '',
		'detail' => '',
		'pmids' => array(),
		'drugs' => array(),
	);
	if($chunk === ''){
		return $empty;
	}

	$drugs = array();
	$meta = $chunk;
	if(strpos($chunk, '#') !== false){
		$parts = explode('#', $chunk);
		$last = $parts[count($parts) - 1];
		$looksLikeDrugs = ($last === '' || preg_match('/^(DB\d+)(,DB\d+)*$/i', $last));
		if($looksLikeDrugs){
			array_pop($parts);
			$meta = implode('#', $parts);
			if($last !== ''){
				foreach(explode(',', $last) as $d){
					$d = trim($d);
					if($d !== ''){
						$drugs[] = $d;
					}
				}
			}
		}
	}

	$score = '';
	$source = '';
	$detail = '';
	$pmids = array();
	$label = $meta;
	$gene = '';

	// GPS with score: hierarchy#GENE@score
	if(substr_count($meta, '@') === 1 && preg_match('/^(.*)#([^@#]+)@(.+)$/', $meta, $m)){
		$hier = $m[1];
		$gene = $m[2];
		$maybeScore = $m[3];
		if(is_numeric($maybeScore) || preg_match('/^\d+(\.\d+)?(e[+-]?\d+)?$/i', $maybeScore)){
			$score = $maybeScore;
			$label = $hier.'#'.$gene;
			$source = 'GPS';
			return array(
				'label' => $label,
				'gene' => $gene,
				'score' => $score,
				'source' => $source,
				'detail' => '',
				'pmids' => array(),
				'drugs' => $drugs,
			);
		}
	}

	// Exp / Ub style: GENE@Source@detail (two @; detail/pmids may be empty)
	if(substr_count($meta, '@') >= 2 && preg_match('/^([^@]+)@([^@]*)@(.*)$/', $meta, $m)){
		$gene = $m[1];
		$source = $m[2];
		$detail = $m[3];
		$label = $gene;
		$pmidRaw = str_replace(array('|', ','), ';', $detail);
		foreach(explode(';', $pmidRaw) as $p){
			$p = trim($p);
			if(ctype_digit($p)){
				$pmids[] = $p;
			}
		}
		return array(
			'label' => $label,
			'gene' => $gene,
			'score' => '',
			'source' => $source,
			'detail' => $detail,
			'pmids' => $pmids,
			'drugs' => $drugs,
		);
	}

	// GPS without score / legacy: hierarchy#GENE or LABEL
	if(strpos($meta, '#') !== false){
		$bits = explode('#', $meta);
		$gene = trim($bits[count($bits) - 1]);
		$label = $meta;
		return array(
			'label' => $label,
			'gene' => $gene,
			'score' => '',
			'source' => '',
			'detail' => '',
			'pmids' => array(),
			'drugs' => $drugs,
		);
	}

	$gene = $meta;
	$label = $meta;
	return array(
		'label' => $label,
		'gene' => $gene,
		'score' => '',
		'source' => '',
		'detail' => '',
		'pmids' => array(),
		'drugs' => $drugs,
	);
}

function formatPmidLinks(array $pmids, $sep = ', '){
	if(!$pmids){
		return '-';
	}
	$links = array();
	foreach($pmids as $p){
		$safe = htmlspecialchars($p, ENT_QUOTES, 'UTF-8');
		$links[] = "<a href='https://pubmed.ncbi.nlm.nih.gov/".$safe."/' target='_blank' rel='noopener'>".$safe."</a>";
	}
	return implode($sep, $links);
}

function formatEnzymeEvidence($parsed, $omitPmids = false){
	$source = isset($parsed['source']) ? $parsed['source'] : '';
	$detail = isset($parsed['detail']) ? $parsed['detail'] : '';
	$pmids = isset($parsed['pmids']) ? $parsed['pmids'] : array();
	if($pmids){
		if($source === 'eKPI' && $omitPmids){
			// PMID shown in dedicated column
		}elseif($source !== '' && !in_array($source, array('PhosphoSitePlus', 'eKPI', 'GPS', 'GPS-Uber'), true)){
			return htmlspecialchars($source, ENT_QUOTES, 'UTF-8').'; '.formatPmidLinks($pmids);
		}elseif($source === 'eKPI'){
			return "<a href='https://ekpi.omicsbio.info/' target='_blank' rel='noopener'>eKPI</a>; ".formatPmidLinks($pmids, '; ');
		}else{
			$src = $source !== '' ? htmlspecialchars($source, ENT_QUOTES, 'UTF-8').': ' : '';
			return $src.formatPmidLinks($pmids);
		}
	}
	if($source === 'PhosphoSitePlus'){
		return "<a href='https://www.phosphosite.org' target='_blank' rel='noopener'>PhosphoSitePlus</a>";
	}
	if($source === 'GPS'){
		return "<a href='https://gps.biocuckoo.cn' target='_blank' rel='noopener'>GPS</a>";
	}
	if($source === 'eKPI'){
		return "<a href='https://ekpi.omicsbio.info/' target='_blank' rel='noopener'>eKPI</a>";
	}
	if($source === 'WERAM'){
		return "<a href='http://weram.biocuckoo.org' target='_blank' rel='noopener'>WERAM</a>";
	}
	if($source === 'Deep-PLA' || $source === 'Exp.' || $source === 'Exp'){
		return "<a href='http://deeppla.omicsbio.info/index.php' target='_blank' rel='noopener'>Deep-PLA</a>";
	}
	if($source !== ''){
		$out = htmlspecialchars($source, ENT_QUOTES, 'UTF-8');
		if($detail !== '' && !preg_match('/^\d/', $detail)){
			$out .= ' ('.htmlspecialchars($detail, ENT_QUOTES, 'UTF-8').')';
		}
		return $out;
	}
	return '-';
}

function formatEnzymePmidCell($parsed){
	$source = isset($parsed['source']) ? $parsed['source'] : '';
	$pmids = isset($parsed['pmids']) ? $parsed['pmids'] : array();
	if($source === 'eKPI' && $pmids){
		return formatPmidLinks($pmids, '; ');
	}
	return '-';
}

function clinicalStatusBadgeClass($status){
	$l = strtolower(trim((string)$status));
	if(strpos($l, 'approved') !== false){
		return 'clinical-approved';
	}
	if(strpos($l, 'investigational') !== false){
		return 'clinical-investigational';
	}
	if(strpos($l, 'withdrawn') !== false){
		return 'clinical-withdrawn';
	}
	if(strpos($l, 'experimental') !== false){
		return 'clinical-experimental';
	}
	return 'clinical-other';
}

function clinicalStatusBadge($status){
	$status = trim((string)$status);
	if($status === '' || $status === '-'){
		return '-';
	}
	$parts = preg_split('/\s*,\s*/', $status);
	$parts = array_values(array_filter(array_map('trim', $parts), 'strlen'));
	if(!$parts){
		return '-';
	}
	$badges = array();
	foreach($parts as $part){
		$class = clinicalStatusBadgeClass($part);
		$badges[] = "<span class='clinical-badge ".$class."'>".htmlspecialchars($part, ENT_QUOTES, 'UTF-8')."</span>";
	}
	if(count($badges) === 1){
		return $badges[0];
	}
	return "<span class='clinical-badge-stack'>".implode('', $badges)."</span>";
}

/**
 * Rich enzyme table.
 * $opts: show_score, show_evidence (evidence content shown in Source column)
 */
function aceRegulatorRoleClass($parsed){
	$source = isset($parsed['source']) ? $parsed['source'] : '';
	if($source === 'WERAM'){
		$parts = explode(';', (string)(isset($parsed['detail']) ? $parsed['detail'] : ''));
		$role = isset($parts[0]) ? trim($parts[0]) : '';
		$family = isset($parts[1]) ? trim($parts[1]) : '';
		$roleLabel = $role !== '' ? ucfirst(strtolower($role)) : '-';
		$classLabel = $family !== '' ? $family : '-';
		return array($roleLabel, $classLabel);
	}
	if($source === 'Deep-PLA' || $source === 'Exp.' || $source === 'Exp'){
		return array('Writer/Eraser', 'HATs/HDACs');
	}
	return array('-', '-');
}

/**
 * Resolve DrugBank inhibitor IDs for a WERAM enzyme row (gene → UniProt → DrugBank).
 * $modification: acetylation | methylation | '' (any)
 */
function aceEnzymeDrugIdsForParsed($parsed, $modification = ''){
	if(!is_array($parsed) || !empty($parsed['drugs'])){
		return isset($parsed['drugs']) ? $parsed['drugs'] : array();
	}
	static $cache = array();
	$gene = isset($parsed['gene']) && $parsed['gene'] !== '' ? $parsed['gene'] : (isset($parsed['label']) ? $parsed['label'] : '');
	$gene = trim((string)$gene);
	if($gene === ''){
		return array();
	}
	if(strpos($gene, '#') !== false){
		$bits = explode('#', $gene);
		$gene = trim($bits[count($bits) - 1]);
	}
	$modKey = strtolower(trim((string)$modification));
	$key = strtoupper($gene).'|'.$modKey;
	if(isset($cache[$key])){
		return $cache[$key];
	}
	$uniprot = lookupWeramUniprot($gene, $modKey);
	if($uniprot === ''){
		$cache[$key] = array();
		return $cache[$key];
	}
	$csv = lookupDrugBankIdsByUniprot($uniprot);
	if($csv === ''){
		$cache[$key] = array();
		return $cache[$key];
	}
	$cache[$key] = array_values(array_filter(array_map('trim', explode(',', $csv)), 'strlen'));
	return $cache[$key];
}

function displayAceEnzymeTable($enzymeInfo, $modification = 'acetylation'){
	$chunks = array_filter(array_map('trim', explode('|', (string)$enzymeInfo)), 'strlen');
	if(!$chunks){
		return '-';
	}
	$parsedList = array();
	$allDrugs = array();
	foreach($chunks as $chunk){
		$p = parseEnzymeChunk($chunk);
		if($p['label'] === '' && $p['gene'] === ''){
			continue;
		}
		if(!$p['drugs']){
			$p['drugs'] = aceEnzymeDrugIdsForParsed($p, $modification);
		}
		$parsedList[] = $p;
		foreach($p['drugs'] as $d){
			$allDrugs[] = $d;
		}
	}
	if(!$parsedList){
		return '-';
	}
	$clinical = lookupDrugBankClinical($allDrugs);
	$thead = "<tr><th>Enzyme</th><th>Role</th><th>Class</th><th>Inhibitor</th><th>Clinical status</th><th>Source</th></tr>";
	$html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'>".$thead."</thead><tbody>";
	foreach($parsedList as $p){
		$label = htmlspecialchars($p['label'] !== '' ? $p['label'] : $p['gene'], ENT_QUOTES, 'UTF-8');
		list($roleInner, $classInner) = aceRegulatorRoleClass($p);
		$roleInner = htmlspecialchars($roleInner, ENT_QUOTES, 'UTF-8');
		$classInner = htmlspecialchars($classInner, ENT_QUOTES, 'UTF-8');
		$parts = array();
		if(true){
			$ev = formatEnzymeEvidence($p);
			if($ev !== '' && $ev !== '-'){
				$parts[] = $ev;
			}
		}
		if($p['drugs']){
			$parts[] = displayDrugBankLink();
		}
		$sourceInner = $parts ? implode('; ', $parts) : '-';
		$drugs = $p['drugs'];
		if(!$drugs){
			$html .= "<tr><td>".$label."</td><td>".$roleInner."</td><td>".$classInner."</td><td>-</td><td>-</td><td>".$sourceInner."</td></tr>";
			continue;
		}
		$rowspan = count($drugs);
		$rs = " rowspan='".$rowspan."'";
		for($i = 0; $i < $rowspan; $i++){
			$drug = $drugs[$i];
			$clin = isset($clinical[$drug]) ? $clinical[$drug]['status'] : '-';
			$drugLabel = htmlspecialchars($drug, ENT_QUOTES, 'UTF-8');
			if(isset($clinical[$drug]['name']) && $clinical[$drug]['name'] !== ''){
				$drugLabel .= " <span class='drug-name'>(".htmlspecialchars($clinical[$drug]['name'], ENT_QUOTES, 'UTF-8').")</span>";
			}
			if($i === 0){
				$html .= "<tr><td".$rs.">".$label."</td><td".$rs.">".$roleInner."</td><td".$rs.">".$classInner."</td>";
				$html .= "<td>".$drugLabel."</td><td>".clinicalStatusBadge($clin)."</td><td".$rs.">".$sourceInner."</td></tr>";
			}else{
				$html .= "<tr><td>".$drugLabel."</td><td>".clinicalStatusBadge($clin)."</td></tr>";
			}
		}
	}
	$html .= "</tbody></table></div>";
	return $html;
}

function displayEnzymeTable($enzymeInfo, $enzymeType, $opts = array()){
	$showScore = !empty($opts['show_score']);
	$showEvidence = !empty($opts['show_evidence']);
	$showPmid = !empty($opts['show_pmid']);
	$chunks = array_filter(array_map('trim', explode('|', (string)$enzymeInfo)), 'strlen');
	if(!$chunks){
		return '-';
	}

	$parsedList = array();
	$allDrugs = array();
	foreach($chunks as $chunk){
		$p = parseEnzymeChunk($chunk);
		if($p['label'] === '' && $p['gene'] === ''){
			continue;
		}
		$parsedList[] = $p;
		foreach($p['drugs'] as $d){
			$allDrugs[] = $d;
		}
	}
	if($showScore){
		usort($parsedList, function($a, $b){
			$sa = is_numeric($a['score']) ? (float)$a['score'] : -1;
			$sb = is_numeric($b['score']) ? (float)$b['score'] : -1;
			if($sa == $sb){
				return 0;
			}
			return ($sa < $sb) ? 1 : -1;
		});
	}

	$clinical = lookupDrugBankClinical($allDrugs);

	$thead = "<tr><th>".$enzymeType."</th>";
	if($showScore){
		$thead .= "<th>GPS_score</th>";
	}
	$thead .= "<th>Inhibitor</th><th>Clinical status</th>";
	if($showPmid){
		$thead .= "<th>PMID</th>";
	}
	$thead .= "<th>Source</th></tr>";

	$html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'>".$thead."</thead><tbody>";

	foreach($parsedList as $p){
		$label = htmlspecialchars($p['label'] !== '' ? $p['label'] : $p['gene'], ENT_QUOTES, 'UTF-8');
		$scoreInner = ($p['score'] !== '') ? htmlspecialchars($p['score'], ENT_QUOTES, 'UTF-8') : '-';
		$drugs = $p['drugs'];
		$parts = array();
		if($showEvidence){
			$ev = formatEnzymeEvidence($p, $showPmid);
			if($ev !== '' && $ev !== '-'){
				$parts[] = $ev;
			}
		}
		if($drugs){
			$parts[] = displayDrugBankLink();
		}
		$sourceInner = $parts ? implode('; ', $parts) : '-';
		$pmidInner = $showPmid ? formatEnzymePmidCell($p) : '';
		if(!$drugs){
			$html .= "<tr><td>".$label."</td>";
			if($showScore){
				$html .= "<td>".$scoreInner."</td>";
			}
			$html .= "<td>-</td><td>-</td>";
			if($showPmid){
				$html .= "<td>".$pmidInner."</td>";
			}
			$html .= "<td>".$sourceInner."</td></tr>";
			continue;
		}
		$rowspan = count($drugs);
		$rs = " rowspan='".$rowspan."'";
		for($i = 0; $i < $rowspan; $i++){
			$drug = $drugs[$i];
			$clin = isset($clinical[$drug]) ? $clinical[$drug]['status'] : '-';
			$drugLabel = htmlspecialchars($drug, ENT_QUOTES, 'UTF-8');
			if(isset($clinical[$drug]['name']) && $clinical[$drug]['name'] !== ''){
				$drugLabel .= " <span class='drug-name'>(".htmlspecialchars($clinical[$drug]['name'], ENT_QUOTES, 'UTF-8').")</span>";
			}
			if($i === 0){
				$html .= "<tr><td".$rs.">".$label."</td>";
				if($showScore){
					$html .= "<td".$rs.">".$scoreInner."</td>";
				}
				$html .= "<td>".$drugLabel."</td><td>".clinicalStatusBadge($clin)."</td>";
				if($showPmid){
					$html .= "<td".$rs.">".$pmidInner."</td>";
				}
				$html .= "<td".$rs.">".$sourceInner."</td></tr>";
			}else{
				$html .= "<tr><td>".$drugLabel."</td><td>".clinicalStatusBadge($clin)."</td></tr>";
			}
		}
	}
	$html .= "</tbody></table></div>";
	return $html;
}

/*------ Display available enzyme information (legacy wrapper)------*/
function displayEnzyme($enzymeInfo,$enzymeType){
	$opts = array('show_evidence' => true);
	if(stripos($enzymeType, 'GPS') !== false || (!empty($enzymeInfo) && preg_match('/@\d/', $enzymeInfo))){
		$opts['show_score'] = true;
	}
	return displayEnzymeTable($enzymeInfo, $enzymeType, $opts);
}

function displaySumoEvidence($evidenceRaw){
	$evidenceRaw = trim((string)$evidenceRaw);
	if($evidenceRaw === ''){
		return '-';
	}
	$pmidPart = $evidenceRaw;
	$src = '';
	if(strpos($evidenceRaw, '@') !== false){
		list($pmidPart, $src) = explode('@', $evidenceRaw, 2);
	}
	$pmids = array();
	foreach(explode(';', $pmidPart) as $p){
		$p = trim($p);
		if(ctype_digit($p)){
			$pmids[] = $p;
		}
	}
	$html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'><tr><th>Evidence</th><th>Source databases</th></tr></thead><tbody>";
	$html .= "<tr><td>".formatPmidLinks($pmids)."</td><td>".($src !== '' ? htmlspecialchars($src, ENT_QUOTES, 'UTF-8') : 'GPS-SUMO')."</td></tr>";
	$html .= "</tbody></table></div>";
	return $html;
}

function displayUbE3Table($e3Raw, $substratePos = ''){
	$chunks = array_filter(array_map('trim', explode('|', (string)$e3Raw)), 'strlen');
	if(!$chunks){
		return '-';
	}
	$posLabel = ($substratePos !== '' && $substratePos !== null) ? htmlspecialchars((string)$substratePos, ENT_QUOTES, 'UTF-8') : '-';
	$html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'>"
		."<tr><th>E3 ligase</th><th>Position (Substrate)</th><th>Class</th><th>PMID</th><th>Source</th></tr>"
		."</thead><tbody>";
	foreach($chunks as $chunk){
		$p = parseUbE3Chunk($chunk);
		$gene = htmlspecialchars($p['gene'], ENT_QUOTES, 'UTF-8');
		$cls = ($p['class'] !== '') ? htmlspecialchars($p['class'], ENT_QUOTES, 'UTF-8') : '-';
		$pmidHtml = $p['pmids'] ? formatPmidLinks($p['pmids']) : '-';
		$html .= "<tr><td>".$gene."</td><td>".$posLabel."</td><td>".$cls."</td><td>".$pmidHtml."</td>"
			."<td><a href='http://gpsuber.biocuckoo.cn/' target='_blank' rel='noopener'>GPS-Uber</a></td></tr>";
	}
	$html .= "</tbody></table></div>";
	return $html;
}

function displayUbiBrowserTable($uniprot){
	$rows = lookupUbiBrowserInteractions($uniprot, 50);
	if(!$rows){
		return '-';
	}
	$html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'>"
		."<tr><th>Enzyme type</th><th>E3/DUB ligase</th><th>Class</th><th>PMID</th><th>Source</th></tr>"
		."</thead><tbody>";
	foreach($rows as $r){
		$type = htmlspecialchars($r['enzyme_type'] !== '' ? $r['enzyme_type'] : '-', ENT_QUOTES, 'UTF-8');
		$gene = htmlspecialchars($r['enzyme_gene'] !== '' ? $r['enzyme_gene'] : '-', ENT_QUOTES, 'UTF-8');
		$fam = htmlspecialchars($r['family'] !== '' ? $r['family'] : '-', ENT_QUOTES, 'UTF-8');
		$pmidHtml = '-';
		if($r['pmid'] !== '' && ctype_digit($r['pmid'])){
			$pmidHtml = formatPmidLinks(array($r['pmid']));
		}elseif($r['pmid'] !== ''){
			$pmids = array();
			foreach(preg_split('/[|;,\s]+/', $r['pmid']) as $p){
				if(ctype_digit($p)){
					$pmids[] = $p;
				}
			}
			$pmidHtml = $pmids ? formatPmidLinks($pmids) : htmlspecialchars($r['pmid'], ENT_QUOTES, 'UTF-8');
		}
		$html .= "<tr><td>".$type."</td><td>".$gene."</td><td>".$fam."</td><td>".$pmidHtml."</td>"
			."<td><a href='http://ubibrowser.bio-it.cn/ubibrowser_v3/home/index' target='_blank' rel='noopener'>UbiBrowser</a></td></tr>";
	}
	$html .= "</tbody></table></div>";
	return $html;
}

/**
 * Protein-level GPS-Uber (by substrate UniProt) + UbiBrowser E3/DUB evidence as one Experimental table.
 * Pass precomputed $rows from collectUbExperimentalRows() to avoid a second lookup.
 */
function displayUbExperimentalTable($uniprot, $rows = null){
	if($rows === null){
		$rows = collectUbExperimentalRows($uniprot);
	}
	if(!$rows){
		return '-';
	}

	$html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'>"
		."<tr><th>Enzyme type</th><th>E3/DUB ligase</th><th>Class</th><th>PMID</th><th>Source</th></tr>"
		."</thead><tbody>";
	foreach($rows as $r){
		$type = htmlspecialchars($r['type'], ENT_QUOTES, 'UTF-8');
		$gene = htmlspecialchars($r['gene'], ENT_QUOTES, 'UTF-8');
		$cls = htmlspecialchars($r['class'], ENT_QUOTES, 'UTF-8');
		if($r['pmids']){
			$pmidHtml = formatPmidLinks($r['pmids']);
		}elseif($r['pmid_raw'] !== '' && ctype_digit($r['pmid_raw'])){
			$pmidHtml = formatPmidLinks(array($r['pmid_raw']));
		}elseif($r['pmid_raw'] !== ''){
			$pmids = array();
			foreach(preg_split('/[|;,\s]+/', $r['pmid_raw']) as $p){
				if(ctype_digit($p)){
					$pmids[] = $p;
				}
			}
			$pmidHtml = $pmids ? formatPmidLinks($pmids) : htmlspecialchars($r['pmid_raw'], ENT_QUOTES, 'UTF-8');
		}else{
			$pmidHtml = '-';
		}
		$html .= "<tr><td>".$type."</td><td>".$gene."</td><td>".$cls."</td><td>".$pmidHtml."</td><td>".$r['source']."</td></tr>";
	}
	$html .= "</tbody></table></div>";
	return $html;
}

/** Normalize aceenz legacy GENE#drugs into GENE@Source@detail#drugs */
function normalizeAceEnzymeChunk($chunk, $defaultSource, $modification = 'acetylation'){
	$p = parseEnzymeChunk($chunk);
	$gene = $p['gene'] !== '' ? $p['gene'] : $p['label'];
	$gene = trim((string)$gene);
	if($gene === ''){
		return '';
	}
	// legacy hierarchy#GENE → use trailing gene token only
	if(strpos($gene, '#') !== false){
		$bits = explode('#', $gene);
		$gene = trim($bits[count($bits) - 1]);
	}
	if($gene === ''){
		return '';
	}
	$source = $p['source'] !== '' ? $p['source'] : $defaultSource;
	$detail = str_replace(array('@', '#'), array('/', '/'), (string)$p['detail']);
	$drugs = implode(',', $p['drugs']);
	if($drugs === ''){
		$drugs = implode(',', aceEnzymeDrugIdsForParsed($p, $modification));
	}
	return $gene.'@'.$source.'@'.$detail.'#'.$drugs;
}

/**
 * Merge site-specific enzyme chunks with WERAM regulators for a modification.
 * $weramEvidence: collected | predicted
 * $modification: acetylation | methylation
 */
function buildWeramEnzymeMergedInfo($siteRaw, $defaultSource, $weramEvidence, $modification = 'acetylation'){
	$chunks = array();
	$seen = array();
	foreach(array_filter(array_map('trim', explode('|', (string)$siteRaw)), 'strlen') as $chunk){
		$norm = normalizeAceEnzymeChunk($chunk, $defaultSource, $modification);
		if($norm === ''){
			continue;
		}
		$p = parseEnzymeChunk($norm);
		$key = strtoupper(($p['gene'] !== '' ? $p['gene'] : $p['label']).'|'.$p['source'].'|'.$p['detail']);
		if(isset($seen[$key])){
			continue;
		}
		$seen[$key] = true;
		$chunks[] = $norm;
	}
	foreach(lookupWeramRegulators($modification, $weramEvidence, 400) as $r){
		$gene = trim((string)$r['gene']);
		if($gene === ''){
			continue;
		}
		$detailParts = array();
		foreach(array($r['role'], $r['family']) as $bit){
			$bit = trim((string)$bit);
			if($bit !== ''){
				$detailParts[] = str_replace(array('@', '#', ';'), array('/', '/', '/'), $bit);
			}
		}
		$detail = implode(';', $detailParts);
		$drugs = lookupDrugBankIdsByUniprot(isset($r['uniprot']) ? $r['uniprot'] : '');
		$norm = $gene.'@WERAM@'.$detail.'#'.$drugs;
		$key = strtoupper($gene.'|WERAM|'.$detail);
		if(isset($seen[$key])){
			continue;
		}
		$seen[$key] = true;
		$chunks[] = $norm;
	}
	return implode('|', $chunks);
}

/**
 * Merge site-specific aceenz chunks with WERAM acetylation regulators.
 * $weramEvidence: collected | predicted
 */
function buildAceEnzymeMergedInfo($siteRaw, $defaultSource, $weramEvidence){
	return buildWeramEnzymeMergedInfo($siteRaw, $defaultSource, $weramEvidence, 'acetylation');
}

/** Parse Ub chunk: E3GENE@E3UNIPROT@class@pmid# (also accepts legacy E3GENE@class@pmid#) */
function parseUbE3Chunk($chunk){
	$chunk = trim((string)$chunk);
	$out = array('gene' => '', 'uniprot' => '', 'class' => '', 'pmids' => array());
	if($chunk === ''){
		return $out;
	}
	if(substr($chunk, -1) === '#'){
		$chunk = substr($chunk, 0, -1);
	}
	$parts = explode('@', $chunk);
	if(count($parts) >= 4){
		$out['gene'] = trim($parts[0]);
		$out['uniprot'] = trim($parts[1]);
		$out['class'] = trim($parts[2]);
		$pmidRaw = implode('@', array_slice($parts, 3));
	}elseif(count($parts) >= 3){
		// legacy: GENE@class@pmid
		$out['gene'] = trim($parts[0]);
		$out['class'] = trim($parts[1]);
		$pmidRaw = implode('@', array_slice($parts, 2));
	}else{
		$out['gene'] = trim($parts[0]);
		$pmidRaw = '';
	}
	foreach(preg_split('/[|;,]+/', $pmidRaw) as $p){
		$p = trim($p);
		if(ctype_digit($p)){
			$out['pmids'][] = $p;
		}
	}
	return $out;
}

function detailExpandAction($hasContent, $mode = 'table'){
	if(!$hasContent){
		return "<td class='detail-action'></td>";
	}
	$class = ($mode === 'text') ? 'show-text' : 'show-table';
	$label = ($mode === 'text') ? 'Expand text' : 'Expand table';
	return "<td class='detail-action'><button type='button' class='detail-toggle ".$class."' aria-label='".$label."'><i class='ri-add-circle-fill'></i></button></td>";
}

/** Count valid enzyme annotation chunks (pipe-separated). */
function countEnzymeChunks($enzymeInfo){
	$n = 0;
	foreach(array_filter(array_map('trim', explode('|', (string)$enzymeInfo)), 'strlen') as $chunk){
		$p = parseEnzymeChunk($chunk);
		if($p['label'] !== '' || $p['gene'] !== ''){
			$n++;
		}
	}
	return $n;
}

function detailCountHtml($count){
	return "<br><span class='detail-count'>(Count: ".(int)$count.")</span>";
}

/**
 * One external-database chip link.
 */
function extLinkChip($label, $url){
	$label = htmlspecialchars((string)$label, ENT_QUOTES, 'UTF-8');
	$url = htmlspecialchars((string)$url, ENT_QUOTES, 'UTF-8');
	return "<a class='ext-link-chip' href='".$url."' target='_blank' rel='noopener'>".$label."</a>";
}

/**
 * External links panel (Protein information), grouped by research aspect.
 */
function buildExternalLinksHtml($uniprot, $geneName){
	$up = preg_replace('/-\d+$/', '', trim((string)$uniprot));
	$gene = primaryGeneSymbol($geneName);
	$upQ = $up !== '' ? rawurlencode($up) : '';
	$geneQ = $gene !== '' ? rawurlencode($gene) : $upQ;
	$searchQ = $geneQ !== '' ? $geneQ : $upQ;

	$groups = array(
		'Protein' => array(
			array('UniProt', $up !== '' ? 'https://www.uniprot.org/uniprotkb/'.$up : 'https://www.uniprot.org'),
			array('AlphaFold DB', $up !== '' ? 'https://alphafold.ebi.ac.uk/entry/'.$up : 'https://alphafold.ebi.ac.uk'),
			array('PDB', $up !== '' ? 'https://www.ebi.ac.uk/pdbe/pdbe-kb/proteins/'.$up : 'https://www.rcsb.org'),
			array('ProteomeXchange', $searchQ !== '' ? 'https://proteomecentral.proteomexchange.org/cgi/GetDataset?search='.$searchQ : 'https://www.proteomexchange.org/'),
			array('CPTAC', 'https://proteomics.cancer.gov/programs/cptac'),
		),
		'PTM' => array(
			array('qPTM', $up !== '' ? 'result.php?type=browse&tag=up&keyword='.rawurlencode($up) : 'index.php'),
			array('PhosphoSitePlus', $searchQ !== '' ? 'https://www.phosphosite.org/simpleSearchSubmitAction.action?searchStr='.$searchQ : 'https://www.phosphosite.org'),
			array('dbPTM', 'https://biomics.lab.nycu.edu.tw/dbPTM/'),
			array('CPLM', 'http://cplm.biocuckoo.cn/'),
			array('PTMAtlas', 'https://deepmvp.ptmax.org/'),
		),
		'Regulators' => array(
			array('eKPI', 'https://ekpi.omicsbio.info/'),
			array('GPS 6.0', 'https://gps.biocuckoo.cn'),
			array('GPS-Uber', 'http://gpsuber.biocuckoo.cn/'),
			array('iPTMnet', $up !== '' ? 'https://research.bioinformatics.udel.edu/iptmnet/entry/'.$up : 'https://research.bioinformatics.udel.edu/iptmnet/'),
			array('UbiBrowser', 'http://ubibrowser.bio-it.cn/ubibrowser_v3/home/index'),
		),
		'Interaction' => array(
			array('PTMint', 'https://ptmint.sjtu.edu.cn/'),
			array('PTMcode2', 'http://ptmcode.embl.de'),
			array('IntAct', $up !== '' ? 'https://www.ebi.ac.uk/intact/search?query='.$upQ : 'https://www.ebi.ac.uk/intact'),
			array('BioGRID', $searchQ !== '' ? 'https://thebiogrid.org/search.php?search='.$searchQ.'&organism=all' : 'https://thebiogrid.org'),
			array('STRING', $up !== '' ? 'https://string-db.org/cgi/network?identifiers='.$upQ : 'https://string-db.org'),
		),
		'Function' => array(
			array('GO', $up !== '' ? 'https://www.ebi.ac.uk/QuickGO/annotations?geneProductId='.$upQ : 'https://www.ebi.ac.uk/QuickGO/'),
			array('KEGG', $searchQ !== '' ? 'https://www.kegg.jp/kegg-bin/search_organism_menu?org_name=hsa&keyword='.$searchQ : 'https://www.kegg.jp'),
			array('PathBank', $searchQ !== '' ? 'https://pathbank.org/#search?query='.$searchQ : 'https://pathbank.org'),
			array('Reactome', $up !== '' ? 'https://reactome.org/content/query?q='.$upQ.'&types=Protein' : 'https://reactome.org'),
			array('FunscoR', 'https://evocellnet.github.io/funscoR/'),
		),
		'Disease and drug' => array(
			array('PTMD', 'https://ptmd.biocuckoo.cn/'),
			array('ActiveDriverDB', $gene !== '' ? 'https://activedriverdb.org/gene/'.$gene.'/' : ($up !== '' ? 'https://activedriverdb.org/protein/'.$up.'/' : 'https://activedriverdb.org')),
			array('CancerProteome', 'http://bio-bigdata.hrbmu.edu.cn/CancerProteome'),
			array('PMADS', 'https://pmads-db.org'),
		),
		'Compartment' => array(
			array('HPA', $gene !== '' ? 'https://www.proteinatlas.org/search/'.$geneQ : 'https://www.proteinatlas.org'),
			array('OpenCell', 'https://opencell.czbiohub.org/'),
			array('iNuLoC', 'http://inuloc.omicsbio.info/'),
			array('PTMPhaSe', 'https://ptmphase.sjtu.edu.cn'),
			array('SubCELL', 'https://subcell.idrblab.cn/'),
		),
	);

	$html = "<div class='ext-links'>";
	foreach($groups as $cat => $links){
		$html .= "<div class='ext-links-row'>";
		$html .= "<span class='ext-links-cat'>".htmlspecialchars($cat, ENT_QUOTES, 'UTF-8')."</span>";
		$html .= "<span class='ext-links-chips'>";
		foreach($links as $item){
			$html .= extLinkChip($item[0], $item[1]);
		}
		$html .= "</span></div>";
	}
	$html .= "</div>";
	return $html;
}

/**
 * Collect Ub Experimental rows (GPS-Uber + UbiBrowser) for a substrate UniProt.
 */
function collectUbExperimentalRows($uniprot){
	$rows = array();
	foreach(lookupGpsUberE3BySubstrate($uniprot) as $r){
		$cls = ($r['class'] !== '' && $r['class'] !== 'unclassified') ? $r['class'] : '-';
		$rows[] = array(
			'type' => 'E3',
			'gene' => $r['gene'],
			'class' => $cls,
			'pmids' => $r['pmids'],
			'pmid_raw' => '',
			'source' => "<a href='http://gpsuber.biocuckoo.cn/' target='_blank' rel='noopener'>GPS-Uber</a>",
		);
	}
	foreach(lookupUbiBrowserInteractions($uniprot, 50) as $r){
		$rows[] = array(
			'type' => ($r['enzyme_type'] !== '' ? $r['enzyme_type'] : '-'),
			'gene' => ($r['enzyme_gene'] !== '' ? $r['enzyme_gene'] : '-'),
			'class' => ($r['family'] !== '' ? $r['family'] : '-'),
			'pmids' => array(),
			'pmid_raw' => isset($r['pmid']) ? (string)$r['pmid'] : '',
			'source' => "<a href='http://ubibrowser.bio-it.cn/ubibrowser_v3/home/index' target='_blank' rel='noopener'>UbiBrowser</a>",
		);
	}
	return $rows;
}

function buildEkpiPlaceholder($uniprot, $pos, $line){
	$up = htmlspecialchars($uniprot, ENT_QUOTES, 'UTF-8');
	$ps = htmlspecialchars((string)$pos, ENT_QUOTES, 'UTF-8');
	$ln = htmlspecialchars((string)$line, ENT_QUOTES, 'UTF-8');
	return "<div class='ekpi-quant-block' data-up='".$up."' data-pos='".$ps."' data-line='".$ln."' data-loaded='0'>"
		."<div class='ekpi-quant-status text-muted'>Open this tab to load inferred correlations…</div>"
		."<div class='ekpi-quant-table-wrap'></div>"
		."<div class='ekpi-quant-note text-muted' style='display:none'>Source: <a href='https://ekpi.omicsbio.info/' target='_blank' rel='noopener'>eKPI</a>--Inferring kinase–phosphosite regulation from phosphoproteome-enriched cancer multi-omics datasets. (listed top 10 kinase–phosphosite pairs)</div>"
		."</div>";
}

/*------ Display drug information in a table------*/
function displayDrug($drugInfo, $drugType){
	$drugInfos = explode(';', $drugInfo);
	$returnDrugInfos = "<table class='table table-bordered hide-table hide-more'><thead class='thead-dark'><tr><th style='width:20%'>DrugBank ID</th><th style='width:20%'>Structure</th><th style='width:40%'>".$drugType."</th><th style='width:20%'>Source</th></tr></thead><tbody>";
	foreach($drugInfos as $drugInfo){
		$singleInfo = explode('@', $drugInfo);
		$returnDrugInfos = $returnDrugInfos."<tr><td>".$singleInfo[0]."</td><td>".displayDrugBankStructure($singleInfo[0])."</td><td>".str_replace(',', ', ', $singleInfo[1])."</td><td>".displayDrugBankLink()."</td></tr>";

	}
	$returnDrugInfos = $returnDrugInfos."</tbody></table>";
	return $returnDrugInfos;
}

function resolveTimeCourseFile($timeFile, $pmid = ''){
	$baseDir = __DIR__.'/time_course_mat/';
	$timeFile = trim((string)$timeFile);
	$pmid = trim((string)$pmid);
	if($timeFile === ''){
		return '';
	}
	$candidates = array($timeFile);
	// DB timefile may omit PMID, while files are named "{pmid}#{timefile}.txt"
	if($pmid !== '' && strpos($timeFile, $pmid.'#') !== 0){
		$candidates[] = $pmid.'#'.$timeFile;
	}
	foreach($candidates as $name){
		$path = $baseDir.$name.'.txt';
		if(is_file($path)){
			return $path;
		}
	}
	return '';
}

function showTimeCourse($UniProtID, $pos, $mod, $pmid, $timeFile,$timeType,$thisCon){
	$path = resolveTimeCourseFile($timeFile, $pmid);
	if($path === ''){
		return '-';
	}
	$file = fopen($path, 'r');
	if(!$file){
		return '-';
	}
	$title = explode("\t",str_replace(array("\n","\r"), "", fgets($file)));
	$cons = array_slice($title, 1);
	while(!feof($file)){
		$thisline = fgets($file);
		$thislineInfo = explode("\t",str_replace(array("\n","\r"), "", $thisline));
		if(count($thislineInfo) > 1){
			if($thislineInfo[0] == $UniProtID.'#'.$pos.'#'.$mod){
				$values = array_slice($thislineInfo, 1);
				break;
			}
	    }
	}
	if(!isset($values)){
		return '-';
	}
	$newcon	 = array();
	$timeLabels = array();
	foreach ($cons as $con) {
		$parts = explode('#', $con);
		array_push($newcon, $parts[0]);
		array_push($timeLabels, isset($parts[1]) ? $parts[1] : $parts[0]);
	}
	$markers = array();
	if($timeType == 1){
		for($i=0;$i<count($newcon);$i++){
			if($newcon[$i] == $thisCon){
				array_push($markers,array('name'=>$cons[$i],'value'=>explode('#',$cons[$i])[1],'xAxis'=>$newcon[$i],'yAxis'=>$values[$i]));
			}
		}
	}else{
		$thiConPieces = explode(', ',$thisCon);
		if(count($thiConPieces) == 1){
			$header = '';
		}else{
			$header = implode(', ', array_slice($thiConPieces,-2));
		}
		$times = explode('/', $thiConPieces[count($thiConPieces)-1]);
		foreach($times as $time){
			for($i=0;$i<count($newcon);$i++){
				if($header != ''){
					$time = $header.', '.$time;
				}
				if(strstr($newcon[$i], $time) != false){
					array_push($markers,array('name'=>$cons[$i],'value'=>explode('#',$cons[$i])[1],'xAxis'=>$newcon[$i],'yAxis'=>$values[$i]));
				}
			}
		}
	}
	fclose($file);
	return json_encode(array('condition'=>$newcon,'timeLabels'=>$timeLabels,'values'=>$values,'conMarker'=>$markers,'timeType'=>$timeType));
}

/*------ Load protein annotation file ------*/
function loadProteinInfo($uniprot){
	$upi = array();
	$uniprot = trim((string)$uniprot);
	if($uniprot === ''){
		return $upi;
	}
	$candidates = array($uniprot);
	$base = preg_replace('/-\d+$/', '', $uniprot);
	if($base !== '' && $base !== $uniprot){
		$candidates[] = $base;
	}
	foreach($candidates as $id){
		$filePath = __DIR__.'/proinfo/'.$id.'.txt';
		$file = @fopen($filePath, 'r');
		if(!$file){
			continue;
		}
		while(!feof($file)){
			$thisline = fgets($file);
			$thislineInfo = explode("\t",str_replace("\n", "", $thisline));
			if(count($thislineInfo) > 1){
				$upi[$thislineInfo[0]] = $thislineInfo[1];
			}
		}
		fclose($file);
		if($upi){
			return $upi;
		}
	}
	return $upi;
}

/*------ Map qevent organism labels to properties species keys ------*/
function organismToSpecies($organism){
	$organism = trim((string)$organism);
	if($organism === ''){
		return '';
	}
	$map = array(
		'human' => 'human',
		'mouse' => 'mouse',
		'rat' => 'rat',
		'yeast' => 'yeast',
		'homo sapiens' => 'human',
		'mus musculus' => 'mouse',
		'rattus norvegicus' => 'rat',
		'saccharomyces cerevisiae' => 'yeast'
	);
	$key = strtolower($organism);
	if(isset($map[$key])){
		return $map[$key];
	}
	if(stripos($organism, 'human') !== false || stripos($organism, 'sapiens') !== false){
		return 'human';
	}
	if(stripos($organism, 'mouse') !== false || stripos($organism, 'musculus') !== false){
		return 'mouse';
	}
	if(stripos($organism, 'rat') !== false || stripos($organism, 'norvegicus') !== false){
		return 'rat';
	}
	if(stripos($organism, 'yeast') !== false || stripos($organism, 'cerevisiae') !== false){
		return 'yeast';
	}
	return $key;
}

/*------ Load sequence/structure properties from resource/properties ------*/
function loadProteinProperties($uniprot, $organism = ''){
	$props = array();
	$uniprot = trim((string)$uniprot);
	if($uniprot === ''){
		return $props;
	}

	$dbPath = __DIR__.'/properties/properties.sqlite';
	if(!is_file($dbPath) || !class_exists('SQLite3')){
		return $props;
	}

	try{
		$db = new SQLite3($dbPath, SQLITE3_OPEN_READONLY);
	}catch(Exception $e){
		return $props;
	}

	$species = organismToSpecies($organism);
	$row = null;
	if($species !== ''){
		$stmt = $db->prepare('SELECT * FROM protein_properties WHERE uniprot_id = :id AND species = :species LIMIT 1');
		if($stmt){
			$stmt->bindValue(':id', $uniprot, SQLITE3_TEXT);
			$stmt->bindValue(':species', $species, SQLITE3_TEXT);
			$result = $stmt->execute();
			if($result){
				$row = $result->fetchArray(SQLITE3_ASSOC);
			}
		}
	}
	if(!$row){
		$stmt = $db->prepare('SELECT * FROM protein_properties WHERE uniprot_id = :id LIMIT 1');
		if($stmt){
			$stmt->bindValue(':id', $uniprot, SQLITE3_TEXT);
			$result = $stmt->execute();
			if($result){
				$row = $result->fetchArray(SQLITE3_ASSOC);
			}
		}
	}
	$db->close();

	if(!$row){
		return $props;
	}

	$props['Sequence'] = isset($row['sequence']) ? $row['sequence'] : '';
	$props['Disorder'] = isset($row['Disorder']) ? $row['Disorder'] : '';
	$props['ExposeBuried'] = isset($row['ExposeBuried']) ? $row['ExposeBuried'] : '';
	$props['SurfaceAccessbility'] = isset($row['SurfaceAccessbility']) ? $row['SurfaceAccessbility'] : '';
	$props['Surface'] = $props['SurfaceAccessbility'];
	$props['Second'] = isset($row['Second']) ? $row['Second'] : '';
	$props['SecondStructure'] = $props['Second'];
	$props['Hydropathy'] = isset($row['Hydropathy']) ? $row['Hydropathy'] : '';
	$props['Polar'] = isset($row['Polar']) ? $row['Polar'] : '';
	$props['Charge'] = isset($row['Charge']) ? $row['Charge'] : '';
	return $props;
}

/*------ Merge properties into protein annotation for structure views ------*/
function mergeProteinStructureProperties($upi, $props){
	if(!is_array($upi)){
		$upi = array();
	}
	if(!is_array($props) || !$props){
		return $upi;
	}
	foreach(array('Sequence', 'Disorder', 'ExposeBuried', 'SurfaceAccessbility', 'Surface', 'Second', 'SecondStructure', 'Hydropathy', 'Polar', 'Charge') as $key){
		if(isset($props[$key]) && $props[$key] !== ''){
			$upi[$key] = $props[$key];
		}
	}
	return $upi;
}

/*------ Build PTM track string for structure charts from qevent ------*/
function buildQptmPtminfo($uniprot){
	$uniprot = trim((string)$uniprot);
	if($uniprot === ''){
		return '';
	}
	$base = preg_replace('/-\d+$/', '', $uniprot);
	$cacheIds = array_values(array_unique(array_filter(array($uniprot, $base))));
	$cacheDir = __DIR__.'/cache/ptm_qptm';
	foreach($cacheIds as $cacheId){
		$cacheFile = $cacheDir.'/'.$cacheId.'.txt';
		if(is_file($cacheFile)){
			$cached = trim((string)@file_get_contents($cacheFile));
			if($cached !== ''){
				return $cached;
			}
		}
	}

	$db = connectDB();
	$esc = $db->real_escape_string($uniprot);
	// Avoid ORDER BY CAST(...) here — it forces a filesort on large proteins.
	$queryRes = $db->query("select mods, pos from qevent where up = '{$esc}' group by mods, pos");
	$grouped = array();
	if($queryRes){
		while($row = $queryRes->fetch_assoc()){
			$mod = $row['mods'];
			$pos = $row['pos'];
			if($mod === '' || $pos === ''){
				continue;
			}
			if(!isset($grouped[$mod])){
				$grouped[$mod] = array();
			}
			$grouped[$mod][] = $pos;
		}
	}
	$db->close();
	if(!$grouped){
		return '';
	}
	$parts = array();
	ksort($grouped, SORT_STRING);
	foreach($grouped as $mod => $positions){
		$positions = array_map('intval', $positions);
		sort($positions, SORT_NUMERIC);
		$parts[] = $mod.':'.implode(',', $positions);
	}
	$result = implode(';', $parts);
	if($result !== '' && (@is_dir($cacheDir) || @mkdir($cacheDir, 0755, true))){
		$cacheWriteId = ($base !== '' ? $base : $uniprot);
		@file_put_contents($cacheDir.'/'.$cacheWriteId.'.txt', $result, LOCK_EX);
	}
	return $result;
}

function htmlAttr($value){
	return htmlspecialchars($value, ENT_QUOTES, 'UTF-8');
}

/*------ Known localization (SwissBioPics) from proinfo Localization ------*/
function parseLocalizationNames($localization){
	$localization = trim((string)$localization);
	if($localization === ''){
		return array();
	}
	$parts = preg_split('/\s*;\s*/', $localization);
	$names = array();
	$seen = array();
	foreach($parts as $part){
		$name = trim($part);
		if($name === ''){
			continue;
		}
		$key = strtolower($name);
		if(isset($seen[$key])){
			continue;
		}
		$seen[$key] = true;
		$names[] = $name;
	}
	return $names;
}

function buildKnownLocalizationHtml($localization, $taxid, $lineId){
	$names = parseLocalizationNames($localization);
	if(count($names) === 0){
		return '-';
	}
	$taxid = preg_replace('/\D+/', '', (string)$taxid);
	if($taxid === ''){
		$taxid = '9606';
	}
	$locAttr = htmlAttr(implode('; ', $names));
	return "<div class='known-localization' id='known-loc-".$lineId."' data-locations='".$locAttr."' data-taxid='".htmlAttr($taxid)."' data-rendered='0'>"
		."<div class='subcellular-known-visual'>"
		."<div class='cell-figure' aria-label='Subcellular localization map'></div>"
		."<div class='cell-location-list'></div>"
		."</div>"
		."</div>";
}

function buildProteinStructureHtml($uniprot, $sitePos, $lineId, $hasSequence){
	if(!$hasSequence){
		return '-';
	}
	$uniprot = trim((string)$uniprot);
	if($uniprot === ''){
		return '-';
	}
	$sitePos = preg_replace('/\D+/', '', (string)$sitePos);
	return "<div class='protein-structure-panel' id='protein-structure-".$lineId."' data-uniprot='".htmlAttr($uniprot)."' data-site-pos='".htmlAttr($sitePos)."' data-line='".htmlAttr($lineId)."' data-rendered='0'>"
		."<div class='protein-structure-viewer-box'>"
		."<div class='protein-structure-viewer-stage'>"
		."<div class='structure-box-plot' id='structure-box-plot-".$lineId."'></div>"
		."<div class='structure-viewer-status' id='structure-viewer-status-".$lineId."' hidden></div>"
		."</div>"
		."<div class='protein-pdb-choose'>"
		."<span class='protein-pdb-label'>Select PDB:</span>"
		."<select class='protein-pdb-select' id='pdb-select-".$lineId."'></select>"
		."</div>"
		."</div>"
		."</div>";
}

/*------ Site ±flank window and local sequence/structure features ------*/
function propValueAtPosition($csv, $pos){
	$pos = intval($pos);
	if($pos < 1 || $csv === null || $csv === ''){
		return '';
	}
	$parts = explode(',', (string)$csv);
	$idx = $pos - 1;
	if(!isset($parts[$idx])){
		return '';
	}
	return trim($parts[$idx]);
}

/**
 * Build ±$flank sequence window around a 1-based site position.
 * Missing terminal residues are padded with '_'.
 */
function buildSequenceWindowHtml($sequence, $pos, $flank = 7){
	$sequence = (string)$sequence;
	$pos = intval($pos);
	$flank = max(0, intval($flank));
	$len = strlen($sequence);
	if($pos < 1 || $len === 0 || $pos > $len){
		return '';
	}
	$start = $pos - $flank; // 1-based
	$end = $pos + $flank;
	$left = '';
	$center = $sequence[$pos - 1];
	$right = '';
	for($i = $start; $i < $pos; $i++){
		$left .= ($i >= 1 && $i <= $len) ? $sequence[$i - 1] : '_';
	}
	for($i = $pos + 1; $i <= $end; $i++){
		$right .= ($i >= 1 && $i <= $len) ? $sequence[$i - 1] : '_';
	}
	return "<span class='site-context-window couriernew'>"
		.htmlspecialchars($left, ENT_QUOTES, 'UTF-8')
		."<span class='site-context-res'>".htmlspecialchars($center, ENT_QUOTES, 'UTF-8')."</span>"
		.htmlspecialchars($right, ENT_QUOTES, 'UTF-8')
		."</span>";
}

function describeSecondStructure($code){
	$map = array(
		'A' => 'Alpha-helix',
		'B' => 'Beta-strand',
		'C' => 'Coil'
	);
	$code = strtoupper(trim((string)$code));
	if($code === ''){
		return '-';
	}
	return isset($map[$code]) ? $map[$code].' ('.$code.')' : $code;
}

function describeExposeBuried($code){
	$code = trim((string)$code);
	if($code === ''){
		return '-';
	}
	if($code === '1'){
		return 'Exposed';
	}
	if($code === '0'){
		return 'Buried';
	}
	return $code;
}

function buildSiteContextHtml($upi, $psite){
	$pos = intval(preg_replace('/\D+/', '', (string)$psite));

	$second = propValueAtPosition(isset($upi['Second']) ? $upi['Second'] : '', $pos);
	$disorder = propValueAtPosition(isset($upi['Disorder']) ? $upi['Disorder'] : '', $pos);
	$surface = propValueAtPosition(
		isset($upi['SurfaceAccessbility']) && $upi['SurfaceAccessbility'] !== ''
			? $upi['SurfaceAccessbility']
			: (isset($upi['Surface']) ? $upi['Surface'] : ''),
		$pos
	);
	$expose = propValueAtPosition(isset($upi['ExposeBuried']) ? $upi['ExposeBuried'] : '', $pos);
	$polar = propValueAtPosition(isset($upi['Polar']) ? $upi['Polar'] : '', $pos);
	$charge = propValueAtPosition(isset($upi['Charge']) ? $upi['Charge'] : '', $pos);
	$hydro = propValueAtPosition(isset($upi['Hydropathy']) ? $upi['Hydropathy'] : '', $pos);

	$fmtNum = function($v){
		$v = trim((string)$v);
		if($v === ''){
			return '-';
		}
		if(is_numeric($v)){
			return number_format((float)$v, 3, '.', '');
		}
		return htmlspecialchars($v);
	};

	$posLabel = $pos > 0 ? (string)$pos : '-';
	$aa = '';
	$seq = isset($upi['Sequence']) ? (string)$upi['Sequence'] : '';
	if($pos > 0 && $seq !== '' && $pos <= strlen($seq)){
		$aa = $seq[$pos - 1];
	}
	$windowHtml = ($seq !== '' && $pos > 0) ? buildSequenceWindowHtml($seq, $pos, 7) : '';
	$posHtml = "<div class='site-context-pos'>"
		."<span class='site-context-pos-label'>Site</span>"
		."<span class='site-context-pos-value'>".($aa !== '' ? htmlspecialchars($aa).$posLabel : $posLabel)."</span>";
	if($windowHtml !== ''){
		$posHtml .= "<span class='site-context-pos-label'>Sequence window</span>".$windowHtml;
	}
	$posHtml .= "</div>";

	$row1 = array(
		array('Disorder', $fmtNum($disorder)),
		array('Exposure', describeExposeBuried($expose)),
		array('Polar', $polar === '' ? '-' : htmlspecialchars($polar)),
		array('Charge', $charge === '' ? '-' : htmlspecialchars($charge)),
	);
	$row2 = array(
		array('Secondary structure', describeSecondStructure($second)),
		array('Surface accessibility', $fmtNum($surface)),
		array('Hydropathy', $fmtNum($hydro)),
	);

	$renderRow = function($features, $rowClass){
		$html = "<div class='site-context-features ".$rowClass."'>";
		foreach($features as $feat){
			$html .= "<div class='site-context-feat'><span class='site-context-k'>".$feat[0]."</span><span class='site-context-v'>".$feat[1]."</span></div>";
		}
		$html .= "</div>";
		return $html;
	};

	return "<div class='site-context'>".$posHtml.$renderRow($row1, 'site-context-row-4').$renderRow($row2, 'site-context-row-4')."</div>";
}

function displayDash($value){
	if($value === null){
		return '-';
	}
	$value = trim((string)$value);
	if($value === '' || strcasecmp($value, 'NA') === 0 || strcasecmp($value, 'NULL') === 0 || $value === '#N/A'){
		return '-';
	}
	return $value;
}

function displayDecimal($value, $decimals = 2){
	if($value === null){
		return '-';
	}
	$value = trim((string)$value);
	if($value === '' || strcasecmp($value, 'NA') === 0 || strcasecmp($value, 'NULL') === 0 || $value === '#N/A' || $value === '-'){
		return '-';
	}
	if(is_numeric($value)){
		return number_format((float)$value, $decimals, '.', '');
	}
	return $value;
}

/*------ Regulation: helpers & tables ------*/
function parsePmidList($raw){
	$pmids = array();
	foreach(preg_split('/[|;,\s]+/', (string)$raw) as $p){
		$p = trim($p);
		if($p !== '' && ctype_digit($p)){
			$pmids[] = $p;
		}
	}
	return array_values(array_unique($pmids));
}

function displayDashOrText($value){
	$value = trim((string)$value);
	if($value === '' || strcasecmp($value, 'none') === 0 || strcasecmp($value, 'na') === 0 || $value === '-'){
		return '-';
	}
	return htmlspecialchars($value, ENT_QUOTES, 'UTF-8');
}

function displayFuncscoreHtml($score){
	if($score === null || !is_numeric($score)){
		return '-';
	}
	$score = (float)$score;
	$pct = max(0, min(100, (int)round($score * 100)));
	$label = number_format($score, 3, '.', '');
	$level = 'low';
	if($score >= 0.7){
		$level = 'high';
	}elseif($score >= 0.4){
		$level = 'mid';
	}
	return "<div class='funcscore-wrap'>"
		."<span class='funcscore-value funcscore-".$level."'>".$label."</span>"
		."<span class='funcscore-bar' title='Functional score ".$label."'><span class='funcscore-bar-fill' style='width:".$pct."%'></span></span>"
		."<span class='funcscore-note'>higher is more likely functional</span>"
		."</div>";
}

function displayPspRegulatoryTable($rows){
	if(!$rows){
		return '-';
	}
	$html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'>"
		."<tr><th>On function</th><th>On process</th><th>PMID</th><th>Source</th></tr>"
		."</thead><tbody>";
	$src = "<a href='https://www.phosphosite.org' target='_blank' rel='noopener'>PhosphoSitePlus</a>";
	foreach($rows as $r){
		$fn = displayDashOrText(isset($r['on_function']) ? $r['on_function'] : '');
		$proc = displayDashOrText(isset($r['on_process']) ? $r['on_process'] : '');
		$pmidHtml = formatPmidLinks(parsePmidList(isset($r['pmids']) ? $r['pmids'] : ''));
		$html .= "<tr><td>".$fn."</td><td>".$proc."</td><td>".$pmidHtml."</td><td>".$src."</td></tr>";
	}
	$html .= "</tbody></table></div>";
	return $html;
}

function displayPtmintTable($rows){
	if(!$rows){
		return '-';
	}
	$html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'>"
		."<tr><th>Effect</th><th>Partner</th><th>Disease</th><th>Method</th><th>PMID</th><th>Source</th></tr>"
		."</thead><tbody>";
	$src = "<a href='https://ptmint.sjtu.edu.cn/' target='_blank' rel='noopener'>PTMint</a>";
	foreach($rows as $r){
		$partnerGene = trim((string)(isset($r['int_gene']) ? $r['int_gene'] : ''));
		$partnerUp = trim((string)(isset($r['int_uniprot']) ? $r['int_uniprot'] : ''));
		if($partnerGene !== '' && $partnerUp !== ''){
			$partner = htmlspecialchars($partnerGene, ENT_QUOTES, 'UTF-8')
				." (<a href='https://www.uniprot.org/uniprot/".htmlspecialchars($partnerUp, ENT_QUOTES, 'UTF-8')."' target='_blank' rel='noopener'>"
				.htmlspecialchars($partnerUp, ENT_QUOTES, 'UTF-8')."</a>)";
		}elseif($partnerGene !== ''){
			$partner = htmlspecialchars($partnerGene, ENT_QUOTES, 'UTF-8');
		}elseif($partnerUp !== ''){
			$partner = "<a href='https://www.uniprot.org/uniprot/".htmlspecialchars($partnerUp, ENT_QUOTES, 'UTF-8')."' target='_blank' rel='noopener'>"
				.htmlspecialchars($partnerUp, ENT_QUOTES, 'UTF-8')."</a>";
		}else{
			$partner = '-';
		}
		$effectRaw = trim((string)(isset($r['effect']) ? $r['effect'] : ''));
		$effectClass = 'reg-effect-other';
		if(stripos($effectRaw, 'enhance') !== false || stripos($effectRaw, 'promot') !== false){
			$effectClass = 'reg-effect-up';
		}elseif(stripos($effectRaw, 'inhibit') !== false || stripos($effectRaw, 'decreas') !== false){
			$effectClass = 'reg-effect-down';
		}
		$effect = $effectRaw !== ''
			? "<span class='reg-effect ".$effectClass."'>".htmlspecialchars($effectRaw, ENT_QUOTES, 'UTF-8')."</span>"
			: '-';
		$method = displayDashOrText(isset($r['method']) ? $r['method'] : '');
		$disease = displayDashOrText(isset($r['disease']) ? $r['disease'] : '');
		$pmidHtml = formatPmidLinks(parsePmidList(isset($r['pmid']) ? $r['pmid'] : ''));
		$html .= "<tr><td>".$effect."</td><td>".$partner."</td><td>".$disease."</td><td>".$method."</td><td>".$pmidHtml."</td><td>".$src."</td></tr>";
	}
	$html .= "</tbody></table></div>";
	return $html;
}

function displayPtmphaseTable($rows){
	if(!$rows){
		return '-';
	}
	$html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'>"
		."<tr><th>Effect</th><th>LLPS partners</th><th>Regions</th><th>MLOs</th><th>Disease</th><th>Method</th><th>PMID</th><th>Source</th></tr>"
		."</thead><tbody>";
	$src = "<a href='https://ptmphase.sjtu.edu.cn' target='_blank' rel='noopener'>PTMPhaSe</a>";
	foreach($rows as $r){
		$effectRaw = trim((string)(isset($r['effect']) ? $r['effect'] : ''));
		$effectClass = 'reg-effect-other';
		if(stripos($effectRaw, 'promot') !== false || stripos($effectRaw, 'enhance') !== false){
			$effectClass = 'reg-effect-up';
		}elseif(stripos($effectRaw, 'inhibit') !== false || stripos($effectRaw, 'repress') !== false){
			$effectClass = 'reg-effect-down';
		}
		$effect = $effectRaw !== ''
			? "<span class='reg-effect ".$effectClass."'>".htmlspecialchars($effectRaw, ENT_QUOTES, 'UTF-8')."</span>"
			: '-';
		$partners = displayDashOrText(isset($r['llps_partners']) ? $r['llps_partners'] : '');
		$regions = displayDashOrText(isset($r['llps_regions']) ? $r['llps_regions'] : '');
		$mlos = displayDashOrText(isset($r['mlos']) ? $r['mlos'] : '');
		$method = displayDashOrText(isset($r['methods']) ? $r['methods'] : '');
		$disease = displayDashOrText(isset($r['diseases']) ? $r['diseases'] : '');
		$pmidHtml = formatPmidLinks(parsePmidList(isset($r['pmid']) ? $r['pmid'] : ''));
		$html .= "<tr><td>".$effect."</td><td>".$partners."</td><td>".$regions."</td><td>".$mlos."</td><td>".$disease."</td><td>".$method."</td><td>".$pmidHtml."</td><td>".$src."</td></tr>";
	}
	$html .= "</tbody></table></div>";
	return $html;
}

function ptmcodeEvidenceLabels($row){
	$labels = array();
	if(!empty($row['manual']) && (string)$row['manual'] !== '0'){
		$labels[] = 'Manual';
	}
	if(!empty($row['structure']) && (string)$row['structure'] !== '0'){
		$labels[] = 'Structure';
	}
	if(!empty($row['same_residue']) && (string)$row['same_residue'] !== '0'){
		$labels[] = 'Same residue';
	}
	if(!empty($row['coevolution']) && (string)$row['coevolution'] !== '0'){
		$labels[] = 'Coevolution';
	}
	return $labels ? implode('; ', $labels) : '-';
}

function displayPtmcodeTable($withinRows, $betweenRows){
	$rows = array();
	foreach($withinRows as $r){
		$rows[] = $r;
	}
	foreach($betweenRows as $r){
		$rows[] = $r;
	}
	if(!$rows){
		return '-';
	}
	$html = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table enzyme-annot-table'><thead class='thead-dark'>"
		."<tr><th>Scope</th><th>Site A</th><th>Site B</th><th>Partner gene</th><th>Evidence</th><th>Source</th></tr>"
		."</thead><tbody>";
	$src = "<a href='http://ptmcode.embl.de' target='_blank' rel='noopener'>PTMcode2</a>";
	foreach($rows as $r){
		$scope = (isset($r['_scope']) && $r['_scope'] === 'between') ? 'Between proteins' : 'Within protein';
		$siteA = trim((string)(isset($r['residue1']) ? $r['residue1'] : ''));
		$ptm1 = trim((string)(isset($r['ptm1']) ? $r['ptm1'] : ''));
		if($siteA === '' && isset($r['position1'])){
			$siteA = (string)$r['position1'];
		}
		$siteALabel = htmlspecialchars(trim($siteA.($ptm1 !== '' ? ' ('.$ptm1.')' : '')), ENT_QUOTES, 'UTF-8');
		$siteB = trim((string)(isset($r['residue2']) ? $r['residue2'] : ''));
		$ptm2 = trim((string)(isset($r['ptm2']) ? $r['ptm2'] : ''));
		if($siteB === '' && isset($r['position2'])){
			$siteB = (string)$r['position2'];
		}
		$siteBLabel = htmlspecialchars(trim($siteB.($ptm2 !== '' ? ' ('.$ptm2.')' : '')), ENT_QUOTES, 'UTF-8');
		$partner = '-';
		if(isset($r['_scope']) && $r['_scope'] === 'between'){
			$g1 = trim((string)(isset($r['gene1']) ? $r['gene1'] : ''));
			$g2 = trim((string)(isset($r['gene2']) ? $r['gene2'] : ''));
			$partner = htmlspecialchars(($g1 !== '' && $g2 !== '') ? ($g1.' ↔ '.$g2) : ($g1 !== '' ? $g1 : $g2), ENT_QUOTES, 'UTF-8');
			if($partner === ''){
				$partner = '-';
			}
		}else{
			$partner = htmlspecialchars(isset($r['gene']) ? $r['gene'] : '-', ENT_QUOTES, 'UTF-8');
		}
		$evidence = htmlspecialchars(ptmcodeEvidenceLabels($r), ENT_QUOTES, 'UTF-8');
		$html .= "<tr><td>".$scope."</td><td>".$siteALabel."</td><td>".$siteBLabel."</td><td>".$partner."</td><td>".$evidence."</td><td>".$src."</td></tr>";
	}
	$html .= "</tbody></table></div>";
	return $html;
}

/**
 * Build Regulation detail section HTML for a site.
 * Returns array(html, has_any)
 */
function buildRegulationSection($uniprot, $psite, $geneName, $line, $ptmdCount = 0){
	$pspRows = lookupPspRegulatory($uniprot, $psite);
	$ptmintRows = lookupPtmintPpi($uniprot, $psite);
	$llpsRows = lookupPtmphaseLlps($uniprot, $psite);
	$gene = primaryGeneSymbol($geneName);
	if($gene === '' && $pspRows){
		$gene = primaryGeneSymbol(isset($pspRows[0]['gene']) ? $pspRows[0]['gene'] : '');
	}
	if($gene === '' && $ptmintRows){
		$gene = primaryGeneSymbol(isset($ptmintRows[0]['gene']) ? $ptmintRows[0]['gene'] : '');
	}
	$withinRows = $gene !== '' ? lookupPtmcodeWithin($gene, $psite) : array();
	$betweenRows = $gene !== '' ? lookupPtmcodeBetween($gene, $psite) : array();
	$funcScore = lookupFuncscore($uniprot, $psite);

	$ptmdCount = (int)$ptmdCount;
	$ptmdHas = ($ptmdCount > 0);

	$pspHas = count($pspRows) > 0;
	$ptmintHas = count($ptmintRows) > 0;
	$llpsHas = count($llpsRows) > 0;
	$crosstalkHas = (count($withinRows) + count($betweenRows)) > 0;
	$scoreHas = ($funcScore !== null);

	$pspHtml = $pspHas ? displayPspRegulatoryTable($pspRows) : '-';
	$ptmintHtml = $ptmintHas ? displayPtmintTable($ptmintRows) : '-';
	$llpsHtml = $llpsHas ? displayPtmphaseTable($llpsRows) : '-';
	$crosstalkHtml = $crosstalkHas ? displayPtmcodeTable($withinRows, $betweenRows) : '-';
	$scoreHtml = displayFuncscoreHtml($funcScore);
	$ptmdHtml = $ptmdHas ? lazyDetailTablePlaceholder('ptmd', $uniprot) : '-';

	$html = "<div class='more-info detail-section' id='div-reg-".$line."' style='display:none'>
		<table class='detail-table detail-table-actions'>
		<tbody>
			<tr><td>Functional score<br><span class='detail-count'>(Predicted, Ochoa et al.)</span></td><td class='detail-rich'>".$scoreHtml."</td><td class='detail-action'></td></tr>
			<tr><td>Disease and variants<br><span class='detail-count'>(Count: ".$ptmdCount.")</span></td><td class='detail-rich'>".$ptmdHtml."</td>".detailExpandAction($ptmdHas)."</tr>
			<tr><td>Molecular effects<br><span class='detail-count'>(Count: ".count($pspRows).")</span></td><td class='detail-rich'>".$pspHtml."</td>".detailExpandAction($pspHas)."</tr>
			<tr><td>Interaction effects<br><span class='detail-count'>(Count: ".count($ptmintRows).")</span></td><td class='detail-rich'>".$ptmintHtml."</td>".detailExpandAction($ptmintHas)."</tr>
			<tr><td>Phase separation<br><span class='detail-count'>(Count: ".count($llpsRows).")</span></td><td class='detail-rich'>".$llpsHtml."</td>".detailExpandAction($llpsHas)."</tr>
			<tr><td>Cross-talk<br><span class='detail-count'>(Count: ".(count($withinRows)+count($betweenRows)).")</span></td><td class='detail-rich'>".$crosstalkHtml."</td>".detailExpandAction($crosstalkHas)."</tr>
		</tbody>
		</table>
	</div>";

	return array(
		'html' => $html,
		'has_any' => ($pspHas || $ptmintHas || $llpsHas || $crosstalkHas || $scoreHas || $ptmdHas),
	);
}

/** Structure track payload for lazy chart rendering. */
function buildDetailStructurePayload($uniprot, $organism){
	$upi = loadProteinInfo($uniprot);
	$props = loadProteinProperties($uniprot, $organism);
	$upi = mergeProteinStructureProperties($upi, $props);
	if(!isset($upi['PTM_qPTM']) || $upi['PTM_qPTM'] === ''){
		$upi['PTM_qPTM'] = buildQptmPtminfo($uniprot);
	}
	$surfaceValue = '';
	if(isset($upi['SurfaceAccessbility']) && $upi['SurfaceAccessbility'] !== ''){
		$surfaceValue = $upi['SurfaceAccessbility'];
	}elseif(isset($upi['Surface']) && $upi['Surface'] !== ''){
		$surfaceValue = $upi['Surface'];
	}
	return array(
		'sequence' => isset($upi['Sequence']) ? $upi['Sequence'] : '',
		'ptminfo' => isset($upi['PTM_qPTM']) ? $upi['PTM_qPTM'] : '',
		'disorder' => isset($upi['Disorder']) ? $upi['Disorder'] : '',
		'exposeburied' => isset($upi['ExposeBuried']) ? $upi['ExposeBuried'] : '',
		'polar' => isset($upi['Polar']) ? $upi['Polar'] : '',
		'charge' => isset($upi['Charge']) ? $upi['Charge'] : '',
		'secondstr' => isset($upi['Second']) ? $upi['Second'] : '',
		'surface' => $surfaceValue,
		'hydropathy' => isset($upi['Hydropathy']) ? $upi['Hydropathy'] : '',
	);
}

/*------ Add some div to detail part ------*/
function addDetailDivInfo($rawdata){
	$rawInfo = explode('|', $rawdata);
	$mod = $rawInfo[0];
	$pmid = $rawInfo[1];
	$con = $rawInfo[2];
	$sample = $rawInfo[3];
	$line = $rawInfo[4];
	$uniprot = $rawInfo[5];
	$psite = $rawInfo[6];
	$seqwin = $rawInfo[7];
	$qratiopro = $rawInfo[8];
	$pvaluepro = $rawInfo[9];
	$timefile = $rawInfo[10];
	$timetype = $rawInfo[11];
	$organism = $rawInfo[12];
	$fdr = $rawInfo[13];

	$db = connectDB();
	$pmidEsc = $db->real_escape_string($pmid);
	$conEsc = $db->real_escape_string($con);
	$sampleEsc = $db->real_escape_string($sample);
	$modEsc = $db->real_escape_string($mod);
	$uniprotEsc = $db->real_escape_string($uniprot);
	$conQueryRes = $db->query("select * from contable where pmid='{$pmidEsc}' and con = '{$conEsc}'");
	$samQueryRes = $db->query("select * from samtable where sam = '{$sampleEsc}'");
	$expQueryRes = $db->query("select * from exptable where pmid='{$pmidEsc}' and mods = '{$modEsc}'");
	$ptmdCountRes = $db->query("select count(*) as c from ptmdtable where up='{$uniprotEsc}'");
	$scoreQueryRes = $db->query("select * from scoretable where scoreid = '".$db->real_escape_string($organism.'#'.$pmid.'#'.$uniprot.'#'.$psite.'#'.$mod)."' ");

	$PTMDqueryResNum = 0;
	if($ptmdCountRes){
		$ptmdCountRow = $ptmdCountRes->fetch_assoc();
		$PTMDqueryResNum = isset($ptmdCountRow['c']) ? (int)$ptmdCountRow['c'] : 0;
	}

	$coi = ($conQueryRes && $conQueryRes->num_rows) ? $conQueryRes->fetch_assoc() : null;
	$sai = ($samQueryRes && $samQueryRes->num_rows) ? $samQueryRes->fetch_assoc() : null;
	$exi = ($expQueryRes && $expQueryRes->num_rows) ? $expQueryRes->fetch_assoc() : null;
	$sci = ($scoreQueryRes && $scoreQueryRes->num_rows) ? $scoreQueryRes->fetch_assoc() : null;
	$conditionAnnRows = buildConditionAnnotationRows($db, $pmid, $con);
	$db->close();

	if(!is_array($coi)){ $coi = array('condetail' => '-'); }
	if(!is_array($sai)){ $sai = array('sampleurl' => '', 'samtype' => ''); }
	if(!is_array($exi)){ $exi = array('tit' => '-', 'labelmethod' => '-', 'enrichmethod' => '-', 'msmethod' => '-'); }

	$probDisplay = displayDash($sci ? str_replace('#', ': ', $sci['prob']) : '');
	$ispspDisplay = displayDash($sci ? $sci['ispsp'] : '');
	$isdbptmDisplay = displayDash($sci ? $sci['isdbptm'] : '');
	$isptmatlasDisplay = displayDash($sci ? (isset($sci['isptmatlas']) ? $sci['isptmatlas'] : '') : '');
	$qptmcountDisplay = displayDash($sci ? (isset($sci['qptmcount']) ? $sci['qptmcount'] : '') : '');
	$qratioproDisplay = displayDecimal($qratiopro);
	$pvalueproDisplay = displayDecimal($pvaluepro);
	if($qratioproDisplay === '-' && $pvalueproDisplay === '-'){
		$relatedProteinDisplay = '-';
	}elseif($pvalueproDisplay === '-'){
		$relatedProteinDisplay = $qratioproDisplay;
	}else{
		$relatedProteinDisplay = $qratioproDisplay.' (<i>P</i> value = '.$pvalueproDisplay.')';
	}

	$upi = loadProteinInfo($uniprot);
	if(!isset($upi['Sequence'])){ $upi['Sequence'] = ''; }
	if(!isset($upi['UniProtID'])){ $upi['UniProtID'] = ''; }
	if(!isset($upi['ProteinName'])){ $upi['ProteinName'] = ''; }
	if(!isset($upi['GeneName'])){ $upi['GeneName'] = ''; }
	if(!isset($upi['Organism'])){ $upi['Organism'] = ''; }
	if(!isset($upi['Taxonomy'])){ $upi['Taxonomy'] = ''; }
	if(!isset($upi['Function'])){ $upi['Function'] = ''; }
	// Load properties for site-context chips only; full track strings stay lazy for charts.
	$props = loadProteinProperties($uniprot, $organism);
	$upi = mergeProteinStructureProperties($upi, $props);
	$PTMqueryResNum = countPtmsOtherResource(isset($upi['PTMs_other_resource']) ? $upi['PTMs_other_resource'] : '');
	$hasStructureData = ($upi['Sequence'] !== '');

//Detail information about experiment
	$buttonGroup = "<div class='detail-tabs' role='tablist'><button type='button' class='detail-tab active' role='tab' id='exp-".$line."'>Experiment information</button><button type='button' class='detail-tab' role='tab' id='pro-".$line."'>Protein information</button><button type='button' class='detail-tab' role='tab' id='reg-".$line."'>Functional regulation</button>";
	
	if($mod == 'Phosphorylation'){
		$buttonGroup = $buttonGroup."<button type='button' class='detail-tab' role='tab' id='enz-".$line."'>Phosphorylation regulators and inhibitors</button>";
	}
	elseif($mod == 'Acetylation'){
		$buttonGroup = $buttonGroup."<button type='button' class='detail-tab' role='tab' id='enz-".$line."'>Acetylation regulators and inhibitors</button>";
	}
	elseif($mod == 'Methylation'){
		$buttonGroup = $buttonGroup."<button type='button' class='detail-tab' role='tab' id='enz-".$line."'>Methylation regulators and inhibitors</button>";
	}
	elseif($mod == 'Ubiquitylation'){
		$buttonGroup = $buttonGroup."<button type='button' class='detail-tab' role='tab' id='enz-".$line."'>E3/DUB ligases</button>";
	}
	$buttonGroup = $buttonGroup."</div>";

	$divGroup = "<div class='more-info detail-section' id='div-exp-".$line."'>
		<table class='detail-table'>
		<tbody>
			<tr><td>Resource</td><td colspan='6'>".displayText($exi['tit'])." (PMID: <a href='https://pubmed.ncbi.nlm.nih.gov/".$pmid."/' target='_blank' rel='noopener'>".$pmid."</a>)"."</td></tr>
			<tr><td>Detail condition</td><td colspan='6'>".displayText(fixCellCyclePhageDisplay($coi['condetail']))."</td></tr>
			".$conditionAnnRows."
			".($timetype=='0'
				? "<tr><td>Time course change</td><td colspan='6'>-</td></tr>"
				: "<tr><td>Time course change</td><td colspan='6'><span style='display:none' id='timeCourseData-".$line."'>".showTimeCourse($uniprot,$psite,$mod,$pmid,$timefile,$timetype,$con)."</span><div class='timeCourseShow detail-chart' id='timeCourseShow-".$line."'></div></td></tr>")."
			<tr><td>Related protein change</td><td colspan='6'>".$relatedProteinDisplay."</td></tr>
			<tr><td>Sample (type)</td><td colspan='6'>".sample2link($sample,$sai['sampleurl']).($sai['samtype']==''?'':(' ('.displayText($sai['samtype']).')'))."</td></tr>
			<tr><td>Label method</td><td colspan='6'>".displayText($exi['labelmethod'])."</td></tr>
			<tr><td>Enrichment method</td><td colspan='6'>".displayText($exi['enrichmethod'])."</td></tr>
			<tr><td>Mass spectrometer</td><td colspan='6'>".displayText($exi['msmethod'])."</td></tr>
			<tr><td>Reported PEP/Localization probability</td><td colspan='6'>".$probDisplay."</td></tr>
			<tr><td>Re-identified FDR</td><td colspan='6'>".displayDash($fdr)."</td></tr>
			<tr class='detail-subgrid'><td>Records in databases</td><td><span class='detail-sub-label'>Identified times in qPTM</span><span class='detail-sub-value'>".$qptmcountDisplay."</span></td><td><span class='detail-sub-label'>Collected in PhosphoSitePlus</span><span class='detail-sub-value'>".$ispspDisplay."</span></td><td><span class='detail-sub-label'>Collected in dbPTM</span><span class='detail-sub-value'>".$isdbptmDisplay."</span></td><td><span class='detail-sub-label'>Collected in PTMAtlas</span><span class='detail-sub-value'>".$isptmatlasDisplay."</span></td></tr>
		</tbody>
		</table>
	</div>";

//Detail information about protein (+ sequence properties / structure)
	$structureMessage = $hasStructureData
		? ''
		: "<div class='structure-empty'>Sequence property tracks are not available for this protein.</div>";
	$siteContextHtml = buildSiteContextHtml($upi, $psite);
	$ptmHtml = ($PTMqueryResNum > 0) ? lazyDetailTablePlaceholder('ptms', $uniprot) : '-';
	$orgEsc = htmlspecialchars($organism, ENT_QUOTES, 'UTF-8');
	$upEsc = htmlspecialchars($uniprot, ENT_QUOTES, 'UTF-8');

	$divGroup = $divGroup."<div class='more-info detail-section' id='div-pro-".$line."' style='display:none'>
		<table class='detail-table detail-table-actions'>
		<tbody>
			<tr><td>Uniprot accession</td><td>".($upi['UniProtID'] == ''?"-":ID2links('http://www.uniprot.org/uniprot/', explode(',', $upi['UniProtID'])))."</td><td class='detail-action'></td></tr>
			<tr><td>Protein name</td><td>".str_replace(',',', ',$upi['ProteinName'])."</td><td class='detail-action'></td></tr>
			<tr><td>Gene name</td><td>".($upi['GeneName'] == ''?"-" : str_replace(',',', ',$upi['GeneName']))."</td><td class='detail-action'></td></tr>
			<tr><td>Organism</td><td><em>".$upi['Organism']."</em> NCBI Taxa ID=".ID2links('http://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?lvl=0&id=', array($upi['Taxonomy']))."</td><td class='detail-action'></td></tr>
			<tr><td>Function</td><td class='detail-rich'><span class='hide-text text-less'>".($upi['Function'] == ''?"-":displayFuncDes($upi['Function']))."</span></td><td class='detail-action'><button type='button' class='detail-toggle show-text' aria-label='Expand text'><i class='ri-add-circle-fill'></i></button></td></tr>
			<tr class='known-localization-row'><td>Subcellular localization</td><td class='detail-rich detail-localization'>".buildKnownLocalizationHtml(isset($upi['Localization']) ? $upi['Localization'] : (isset($upi['Subcellular Location']) ? $upi['Subcellular Location'] : ''), isset($upi['Taxonomy']) ? $upi['Taxonomy'] : '9606', $line)."</td><td class='detail-action'></td></tr>
			<tr><td>PTMs for protein<br><span class='detail-count'>(Count: ".$PTMqueryResNum.")</span></td><td class='detail-rich'>".$ptmHtml."</td>".detailExpandAction($PTMqueryResNum > 0)."</tr>
			<tr class='sequence-structure-row'><td>Sequence and structure<br><span class='detail-count'>(Length: ".strlen($upi['Sequence']).")</span></td><td class='detail-rich'><div class='sequence-structure-grid'><div class='sequence-structure-3d'>".buildProteinStructureHtml($uniprot, $psite, $line, $hasStructureData)."</div><div class='sequence-structure-seq'>".($upi['Sequence'] == ''?"-":displaySequence($upi['Sequence']))."</div></div></td><td class='detail-action'><span class='detail-action-spacer' aria-hidden='true'></span></td></tr>
			<tr class='sequence-properties-row'><td>Sequence properties</td><td class='detail-rich'><div class='sequence-properties-block' data-line='".htmlspecialchars($line, ENT_QUOTES, 'UTF-8')."' data-up='".$upEsc."' data-org='".$orgEsc."' data-structure-loaded='0'>
			".$siteContextHtml."
			<div class='data' style='display:none;'></div>
			<div class='viewer detail-viewer'>
				".$structureMessage."
				<div class='structure-zoom' id='structure-zoom-".$line."'></div>
				<div class='detail-chart ptmshow' id='ptmshow-".$line."'></div>
				<div class='detail-chart disordershow' id='disordershow-".$line."'></div>
				<div class='detail-chart exposeshow' id='exposeshow-".$line."'></div>
				<div class='detail-chart polarshow' id='polarshow-".$line."'></div>
				<div class='detail-chart chargeshow' id='chargeshow-".$line."'></div>
				<div class='detail-chart secondstrshow' id='secondstrshow-".$line."'></div>
				<div class='detail-chart surfaceshow' id='surfaceshow-".$line."'></div>
				<div class='detail-chart hydropathyshow' id='hydropathyshow-".$line."'></div>
			</div>
		</div></td><td class='detail-action'></td></tr>
			<tr class='external-links-row'><td>External links</td><td class='detail-rich'>".buildExternalLinksHtml($uniprot, isset($upi['GeneName']) ? $upi['GeneName'] : '')."</td><td class='detail-action'></td></tr>
		</tbody>
		</table>
	</div>";

//Detail information about site regulation
	$geneForReg = isset($upi['GeneName']) ? $upi['GeneName'] : '';
	$regSection = buildRegulationSection($uniprot, $psite, $geneForReg, $line, $PTMDqueryResNum);
	$divGroup = $divGroup.$regSection['html'];

//Detail information about enzyme

	if($mod == 'Phosphorylation'){
		$db = connectDB();
		$enzQueryRes = $db->query("select * from phosenztable where up='{$uniprot}' and pos = '{$psite}'");

		if(!isset($enzQueryRes->num_rows)){
			$enzQueryResNum = 0;
		}
		else{
			$enzQueryResNum = $enzQueryRes->num_rows;
		}
		if($enzQueryResNum == 0){
			$enzi = array('up'=>$uniprot,'pos'=>$psite,'exp'=>'','igps'=>'','gps'=>'');
		}else{
			$enzi = $enzQueryRes->fetch_assoc();
		}

		$db->close();

		$expHas = trim((string)$enzi['exp']) !== '';
		$gpsRaw = isset($enzi['gps']) ? trim((string)$enzi['gps']) : '';
		$igpsRaw = isset($enzi['igps']) ? trim((string)$enzi['igps']) : '';
		$predParts = array();
		if($gpsRaw !== ''){
			$predParts[] = $gpsRaw;
		}
		if($igpsRaw !== ''){
			$predParts[] = $igpsRaw;
		}
		$predRaw = implode('|', $predParts);
		$predHas = ($predRaw !== '');
		$expCount = countEnzymeChunks($enzi['exp']);
		$predCount = countEnzymeChunks($predRaw);
		$expHtml = $expHas ? displayEnzymeTable($enzi['exp'], 'Kinase', array('show_evidence'=>true, 'show_pmid'=>true)) : '-';
		$predHtml = $predHas ? displayEnzymeTable($predRaw, 'Kinase', array('show_evidence'=>true)) : '-';
		$ekpiHtml = buildEkpiPlaceholder($uniprot, $psite, $line);

		$divGroup = $divGroup."<div class='more-info detail-section' id='div-enz-".$line."' style='display:none'>
		<table class='detail-table detail-table-actions'>
		<tbody>
			<tr><td>Experimental".detailCountHtml($expCount)."</td><td class='detail-rich'>".$expHtml."</td>".detailExpandAction($expHas)."</tr>
			<tr><td>Predicted".detailCountHtml($predCount)."</td><td class='detail-rich'>".$predHtml."</td>".detailExpandAction($predHas)."</tr>
			<tr><td>Inferred".detailCountHtml(10)."</td><td class='detail-rich'>".$ekpiHtml."</td>".detailExpandAction(true)."</tr>
		</tbody>
		</table>
	</div>";
	}
	elseif($mod == 'Acetylation'){
		$db = connectDB();
		$enzQueryRes = $db->query("select * from aceenztable where up='{$uniprot}' and pos = '{$psite}'");

		if(!isset($enzQueryRes->num_rows)){
			$enzQueryResNum = 0;
		}
		else{
			$enzQueryResNum = $enzQueryRes->num_rows;
		}
		if($enzQueryResNum == 0){
			$enzi = array('up'=>$uniprot,'pos'=>$psite,'exp'=>'','pla'=>'');
		}else{
			$enzi = $enzQueryRes->fetch_assoc();
		}

		$db->close();

		$aceExpMerged = buildAceEnzymeMergedInfo(isset($enzi['exp']) ? $enzi['exp'] : '', 'Deep-PLA', 'collected');
		$acePredMerged = buildAceEnzymeMergedInfo(isset($enzi['pla']) ? $enzi['pla'] : '', 'Deep-PLA', 'predicted');
		$aceExpHas = ($aceExpMerged !== '');
		$acePredHas = ($acePredMerged !== '');
		$aceExpCount = countEnzymeChunks($aceExpMerged);
		$acePredCount = countEnzymeChunks($acePredMerged);

		$divGroup = $divGroup."<div class='more-info detail-section' id='div-enz-".$line."' style='display:none'>
		<table class='detail-table detail-table-actions'>
		<tbody>
			<tr><td>Experimental".detailCountHtml($aceExpCount)."</td><td class='detail-rich'>".($aceExpHas ? displayAceEnzymeTable($aceExpMerged, 'acetylation') : '-')."</td>".detailExpandAction($aceExpHas)."</tr>
			<tr><td>Predicted".detailCountHtml($acePredCount)."</td><td class='detail-rich'>".($acePredHas ? displayAceEnzymeTable($acePredMerged, 'acetylation') : '-')."</td>".detailExpandAction($acePredHas)."</tr>
		</tbody>
		</table>
	</div>";
	}
	elseif($mod == 'Methylation'){
		$meExpMerged = buildWeramEnzymeMergedInfo('', 'WERAM', 'collected', 'methylation');
		$mePredMerged = buildWeramEnzymeMergedInfo('', 'WERAM', 'predicted', 'methylation');
		$meExpHas = ($meExpMerged !== '');
		$mePredHas = ($mePredMerged !== '');
		$meExpCount = countEnzymeChunks($meExpMerged);
		$mePredCount = countEnzymeChunks($mePredMerged);

		$divGroup = $divGroup."<div class='more-info detail-section' id='div-enz-".$line."' style='display:none'>
		<table class='detail-table detail-table-actions'>
		<tbody>
			<tr><td>Experimental".detailCountHtml($meExpCount)."</td><td class='detail-rich'>".($meExpHas ? displayAceEnzymeTable($meExpMerged, 'methylation') : '-')."</td>".detailExpandAction($meExpHas)."</tr>
			<tr><td>Predicted".detailCountHtml($mePredCount)."</td><td class='detail-rich'>".($mePredHas ? displayAceEnzymeTable($mePredMerged, 'methylation') : '-')."</td>".detailExpandAction($mePredHas)."</tr>
		</tbody>
		</table>
	</div>";
	}
	elseif($mod == 'Ubiquitylation'){
		$ubRows = collectUbExperimentalRows($uniprot);
		$ubExpCount = count($ubRows);
		$ubExpHas = ($ubExpCount > 0);
		$ubExpHtml = $ubExpHas ? displayUbExperimentalTable($uniprot, $ubRows) : '-';
		$divGroup = $divGroup."<div class='more-info detail-section' id='div-enz-".$line."' style='display:none'>
		<table class='detail-table detail-table-actions'>
		<tbody>
			<tr><td>Experimental".detailCountHtml($ubExpCount)."</td><td class='detail-rich'>".$ubExpHtml."</td>".detailExpandAction($ubExpHas)."</tr>
		</tbody>
		</table>
	</div>";
	}

	return "<div class='detail-wrap'>".$buttonGroup."<div class='detail-panel'><span class='detail-panel-caret' aria-hidden='true'></span>".$divGroup."</div></div>";
}

/*------ Browse table show ------*/
function showBrowseTable($showBrowseItems, $rowNumber, $tableType){
	$showBrowseItemsNum = count($showBrowseItems);

	$returnLine = '';
	for($i=0;$i<$showBrowseItemsNum;$i++){
        $showBrowseItem = $showBrowseItems[$i];
        $itemName = str_replace('+', '%2B', $showBrowseItem);
        $returnLine = $returnLine."<tr><td><a href='result.php?type=browse&tag=".$tableType."&keyword=".$itemName."' target='_blank'>".$showBrowseItem."</a></td></tr>";
    }
    for($i=$showBrowseItemsNum;$i<$rowNumber;$i++){
        $returnLine = $returnLine."<tr><td></td></tr>"; 
    }
    return $returnLine;
}

/*------ Display browse table ------*/
function displayBrowseTable($tableType){
	$rowNumber = 10;
	$nowPage = 1;
	echo "<table class='browse-table table text-left' id='".$tableType."-table'>
	<thead><tr><th></th></tr></thead>";
	$file = fopen("./resource/count/".$tableType."/".$tableType."_A.txt",'r');
    $allBrowseItems = explode("\t",fgets($file));
    fclose($file);
    /*----- 文件最后一个是多余的，故总数需要减一 -----*/
    array_pop($allBrowseItems);
    $showBrowseItems = array_slice($allBrowseItems, ($nowPage-1)*$rowNumber, $rowNumber);
    $allBrowseItemsNum = count($allBrowseItems);

    echo "<tbody id='".$tableType."-tableChange'>".showBrowseTable($showBrowseItems, $rowNumber, $tableType)."</tbody>"; 

	echo "</table>";
	echo "<div class='card-body'><span id='".$tableType."-pageInfo'>".showPageInfo($allBrowseItemsNum, $nowPage, $rowNumber)."</span></div>";
	echo "<div class='card-body pageButton' id='".$tableType."-pageButton'>".showPageButton($allBrowseItemsNum, $nowPage, $rowNumber)."</div>";
}

/*------ Display qKinAct table ------*/
function showQKATable($queryRes){

	$returnLine = '';
	foreach($queryRes as $row){
		$arr = explode("\t",$row);
		$returnLine = $returnLine."<tr><td><p><a href='result.php?type=browse&tag=up&keyword=$arr[0]' target='_blank'>$arr[0]</a></p></td><td align='center'><p>$arr[1]</p></td><td align='center'><p>$arr[2]</p></td><td align='center'><p>$arr[3]</p></td><td align='center'><p>$arr[4]</p></td><td align='center'><p>$arr[5]</p></td><td align='center'><p>$arr[6]</p></td></tr>";
	}
    return $returnLine;
}

/*------ Display qKinAct result ------*/
function qkinactDisplay($tempFile){
	echo "<span id='queryInfoFile' style='display:none'>".$tempFile."</span>";
	echo "<div class='card-body alert-primary'>The kinase activation query result are shown as follows:</div>";
	exec("perl ./resource/deal.pl ".$tempFile,$queryResAll);
	$queryResNum = count($queryResAll);
    if($queryResNum == 0){
		echo "<div class='card-body alert-danger'>Sorry, we haven't find any results with your peptide(s)!</div>";
	}
	else{
		echo "<div class='card-body alert-success'>There are ".$queryResNum." entries with your peptide(s).</div>";
		$nowPage = 1;
		$rowNumber = 10;
		$queryRes = array_slice($queryResAll, ($nowPage-1)*$rowNumber, $rowNumber);

/*------ Result table part start------*/
/*------ Fixed table head------*/
		echo "
		<table class='table table-responsive-sm text-center resultTable'>
		<thead class='thead-dark'><tr>
			<th width='8%'>UniProt</th>
    		<th width='8%'>Position</th>
    		<th width='8%'>Code</th>
    		<th width='8%'>Gene</th>
            <th width='8%'>Indication</th>
    		<th width='20%'>Raw Peptide</th>
    		<th width='20%'>User Info</th>
		</tr></thead>
		<tbody id='tableChange'>
			".showQKATable($queryRes)."
		</tbody>
		</table>";
/*------ Changed page button------*/
		echo "<div class='card-body'><div class='row'>
		<div class='col-md-6'>
			<span id='pageInfo'>".showPageInfo($queryResNum, $nowPage, $rowNumber)."</span><span>, <select id='selectRowNumber'><option value='10'>10</option><option value='20'>20</option><option value='50'>50</option><option value='100'>100</option></select> entries per page</span>
		</div>
		<div class='col-md-6' id='pageButton'>
			".showPageButton($queryResNum, $nowPage, $rowNumber)."
		</div>
		</div></div>";
	}
}


/*------ Do function by type ------*/
if(isset($_POST["type"])){
	$type = $_POST["type"];
	if($type == "search"){
		$mods = $_POST["simple_search_mod"];
		$orgs = $_POST["simple_search_org"];
		$links = array();
		$tags = array();
		$keywords = array(); 
		$num = 1;
		array_push($links, '');
		array_push($tags, $_POST["simple_search_tag0"]);
		array_push($keywords, $_POST["simple_search_input0"]);
		while(isset($_POST['simple_search_tag'.$num])){
			if($_POST['simple_search_input'.$num]!=''){
				array_push($links, $_POST["simple_search_link".$num]);
				array_push($tags, $_POST["simple_search_tag".$num]);
			  	array_push($keywords, $_POST["simple_search_input".$num]);
			}
			$num+=1;
		}
		searchDB($links, $tags, $keywords, $mods, $orgs);
	}
	elseif($type == "buildquery"){
		header('Content-Type: application/json; charset=utf-8');
		$mods = isset($_POST["simple_search_mod"]) ? $_POST["simple_search_mod"] : 'All';
		$orgs = isset($_POST["simple_search_org"]) ? $_POST["simple_search_org"] : 'All';
		$tag = isset($_POST["simple_search_tag0"]) ? $_POST["simple_search_tag0"] : '';
		$keyword = isset($_POST["simple_search_input0"]) ? $_POST["simple_search_input0"] : '';
		$browseTags = array('gene', 'condition', 'sample', 'up');

		if($keyword == ''){
			echo json_encode(array('error' => 'Please provide a search keyword.'));
		}
		elseif(in_array($tag, $browseTags, true)){
			$buildResult = buildBrowseQueryInfo($tag, $keyword, $mods, $orgs);
			if(!isset($buildResult['error'])){
				$buildResult = appendQueryCount($buildResult);
			}
			echo json_encode($buildResult);
		}
		else{
			$links = array('');
			$tags = array($tag);
			$keywords = array($keyword);
			$num = 1;
			while(isset($_POST['simple_search_tag'.$num])){
				if($_POST['simple_search_input'.$num] != ''){
					array_push($links, isset($_POST["simple_search_link".$num]) ? $_POST["simple_search_link".$num] : 'and');
					array_push($tags, $_POST["simple_search_tag".$num]);
					array_push($keywords, $_POST["simple_search_input".$num]);
				}
				$num += 1;
			}
			$buildResult = buildSearchQueryInfo($links, $tags, $keywords, $mods, $orgs);
			echo json_encode($buildResult);
		}
	}
	elseif($type == "filteroptions"){
		header('Content-Type: application/json; charset=utf-8');
		$mainQueryInfo = isset($_POST['mainQueryInfo']) ? $_POST['mainQueryInfo'] : '';
		$appliedFilters = array();
		if(isset($_POST['appliedFilters']) && $_POST['appliedFilters'] !== ''){
			$decoded = json_decode($_POST['appliedFilters'], true);
			if(is_array($decoded)){
				$appliedFilters = $decoded;
			}
		}
		if($mainQueryInfo === ''){
			echo json_encode(array('error' => 'Missing query.'));
		}else{
			echo json_encode(getResultFilterOptions($mainQueryInfo, $appliedFilters));
		}
	}
	elseif($type == "change"){
		header('Content-Type: application/json; charset=utf-8');
		$changeQueryInfo = $_POST["newQueryInfo"];
		$orderInfo = $_POST["orderInfo"];
		$nowPage = $_POST["nowPage"];
		$rowNumber = $_POST["rowNumber"];
		$db = connectDB();
		$queryRes = $db->query("select * from qevent where (".$changeQueryInfo.") order by ".$orderInfo." limit ".(($nowPage-1)*$rowNumber).','.$rowNumber);
		//echo "select * from qevent where (".$changeQueryInfo.") order by ".$orderInfo." limit ".(($nowPage-1)*$rowNumber).','.$rowNumber;
		$queryResAll = $db->query("select count(*) from qevent where (".$changeQueryInfo.")");
		if(!isset($queryResAll->num_rows)){
			$queryResNum = 0;
		}
		else{
			$queryResNum = $queryResAll->fetch_assoc()['count(*)'];
		}
		if($queryResNum == 0){
			$tableChange = "<tr><td colspan='10'><div class='status-msg'>Sorry, no matching records found.</div></td></tr>";
		}
		else{
			$tableChange = showResTable($queryRes);
		}
		$pageInfoChange = showPageInfo($queryResNum, $nowPage, $rowNumber);
		$pageButtonChange = showPageButton($queryResNum, $nowPage, $rowNumber);
		$allChangeInfo = array("tableChange" => $tableChange, "pageInfoChange" => $pageInfoChange, "pageButtonChange" => $pageButtonChange, "queryResNum" => $queryResNum, "nowPage" => (int)$nowPage);
		$db -> close();
		echo json_encode($allChangeInfo);
	}
	elseif($type == "detail"){
		header('Content-Type: text/html; charset=utf-8');
		$rawdata = $_POST["rawdata"];
		echo addDetailDivInfo($rawdata);
	}
	elseif($type == "detail_ptms"){
		header('Content-Type: text/html; charset=utf-8');
		$uniprot = isset($_POST['uniprot']) ? trim((string)$_POST['uniprot']) : '';
		$upi = loadProteinInfo($uniprot);
		$ptmRows = parsePtmsOtherResource(isset($upi['PTMs_other_resource']) ? $upi['PTMs_other_resource'] : '');
		echo displayPTM($ptmRows);
	}
	elseif($type == "detail_ptmd"){
		header('Content-Type: text/html; charset=utf-8');
		$uniprot = isset($_POST['uniprot']) ? trim((string)$_POST['uniprot']) : '';
		$db = connectDB();
		$esc = $db->real_escape_string($uniprot);
		$ptmdQueryRes = $db->query("select * from ptmdtable where up='{$esc}' order by pos, mods, disease");
		$ptmdRows = fetchPtmdRows($ptmdQueryRes);
		$db->close();
		echo displayPTMD($ptmdRows);
	}
	elseif($type == "detail_structure"){
		header('Content-Type: application/json; charset=utf-8');
		$uniprot = isset($_POST['uniprot']) ? trim((string)$_POST['uniprot']) : '';
		$organism = isset($_POST['organism']) ? trim((string)$_POST['organism']) : '';
		$flags = JSON_UNESCAPED_UNICODE;
		if(defined('JSON_INVALID_UTF8_SUBSTITUTE')){
			$flags = $flags | JSON_INVALID_UTF8_SUBSTITUTE;
		}
		echo json_encode(buildDetailStructurePayload($uniprot, $organism), $flags);
	}
	elseif($type == 'browseFword'){
		$org = isset($_POST['org']) ? (string)$_POST['org'] : '';
		$mod = isset($_POST['mod']) ? (string)$_POST['mod'] : '';
		$btype = isset($_POST['btype']) ? (string)$_POST['btype'] : '';
		$contrastType = isset($_POST['contrast_type']) ? trim((string)$_POST['contrast_type']) : '';
		$agentKey = isset($_POST['agent_key']) ? trim((string)$_POST['agent_key']) : '';
		$db = connectDB();
		$orgEsc = $db->real_escape_string($org);
		$modEsc = $db->real_escape_string($mod);
		$btypeEsc = $db->real_escape_string($btype);
		$sql = "SELECT b.fword FROM browsetable b";
		$where = " WHERE b.org = '{$orgEsc}' AND b.mods = '{$modEsc}' AND b.btype = '{$btypeEsc}'";
		if($btype === 'condition' && ($contrastType !== '' || $agentKey !== '')){
			$sql .= " INNER JOIN con_annotation a ON a.con = b.cont";
			if($contrastType !== ''){
				$ctEsc = $db->real_escape_string($contrastType);
				$where .= " AND a.contrast_type = '{$ctEsc}'";
			}
			if($agentKey !== ''){
				$akEsc = $db->real_escape_string($agentKey);
				$where .= " AND a.agent_key = '{$akEsc}'";
			}
		}
		$sql .= $where." GROUP BY b.fword ORDER BY b.fword";
		$allQueryFirstWord = mysqli_fetch_all($db->query($sql), MYSQLI_NUM);
		$db->close();
		$returnFirstWordList = array();
		if(is_array($allQueryFirstWord)){
			foreach($allQueryFirstWord as $singleFirstWord){
				array_push($returnFirstWordList, $singleFirstWord[0]);
			}
		}
		echo json_encode($returnFirstWordList);
	}
	elseif($type == 'browseOption'){
		$org = isset($_POST['org']) ? (string)$_POST['org'] : '';
		$mod = isset($_POST['mod']) ? (string)$_POST['mod'] : '';
		$btype = isset($_POST['btype']) ? (string)$_POST['btype'] : '';
		$firstWord = isset($_POST['firstWord']) ? (string)$_POST['firstWord'] : '';
		$optionNumber = isset($_POST['optionNumber']) ? intval($_POST['optionNumber']) : 50;
		$nowPage = isset($_POST['nowPage']) ? intval($_POST['nowPage']) : 1;
		if($optionNumber < 1){ $optionNumber = 50; }
		if($nowPage < 1){ $nowPage = 1; }
		$contrastType = isset($_POST['contrast_type']) ? trim((string)$_POST['contrast_type']) : '';
		$agentKey = isset($_POST['agent_key']) ? trim((string)$_POST['agent_key']) : '';
		$db = connectDB();
		$orgEsc = $db->real_escape_string($org);
		$modEsc = $db->real_escape_string($mod);
		$btypeEsc = $db->real_escape_string($btype);
		$useAnn = ($btype === 'condition' && ($contrastType !== '' || $agentKey !== ''));
		$joinSql = $useAnn ? " INNER JOIN con_annotation a ON a.con = b.cont" : "";
		$extraWhere = "";
		if($useAnn && $contrastType !== ''){
			$ctEsc = $db->real_escape_string($contrastType);
			$extraWhere .= " AND a.contrast_type = '{$ctEsc}'";
		}
		if($useAnn && $agentKey !== ''){
			$akEsc = $db->real_escape_string($agentKey);
			$extraWhere .= " AND a.agent_key = '{$akEsc}'";
		}
		$baseWhere = "b.org = '{$orgEsc}' AND b.mods = '{$modEsc}' AND b.btype = '{$btypeEsc}'".$extraWhere;
		if($firstWord == ''){
			$fwRes = mysqli_fetch_all($db->query(
				"SELECT b.fword FROM browsetable b{$joinSql} WHERE {$baseWhere} GROUP BY b.fword ORDER BY b.fword"
			), MYSQLI_NUM);
			$firstWord = (is_array($fwRes) && isset($fwRes[0][0])) ? $fwRes[0][0] : '';
		}
		$fwEsc = $db->real_escape_string($firstWord);
		$offset = ($nowPage - 1) * $optionNumber;
		$contentSql = "SELECT DISTINCT b.cont FROM browsetable b{$joinSql}"
			." WHERE {$baseWhere} AND b.fword = '{$fwEsc}'"
			." ORDER BY b.cont LIMIT {$offset},{$optionNumber}";
		$allQueryContent = mysqli_fetch_all($db->query($contentSql), MYSQLI_NUM);
		$countSql = "SELECT COUNT(DISTINCT b.cont) AS cnt FROM browsetable b{$joinSql}"
			." WHERE {$baseWhere} AND b.fword = '{$fwEsc}'";
		$queryResAll = $db->query($countSql);
		$queryResNum = 0;
		if($queryResAll){
			$rowCnt = $queryResAll->fetch_assoc();
			$queryResNum = isset($rowCnt['cnt']) ? intval($rowCnt['cnt']) : 0;
		}
		$db->close();
		$returnContentList = array();
		if(is_array($allQueryContent)){
			foreach($allQueryContent as $singleQueryContent){
				array_push($returnContentList, trim($singleQueryContent[0]));
			}
		}
		echo json_encode(array('totalNum'=>$queryResNum,'nowList'=>$returnContentList));
	}
	elseif($type == 'browseConFacets'){
		header('Content-Type: application/json; charset=utf-8');
		$org = isset($_POST['org']) ? (string)$_POST['org'] : '';
		$mod = isset($_POST['mod']) ? (string)$_POST['mod'] : '';
		$contrastType = isset($_POST['contrast_type']) ? trim((string)$_POST['contrast_type']) : '';
		$db = connectDB();
		$orgEsc = $db->real_escape_string($org);
		$modEsc = $db->real_escape_string($mod);
		$labels = array(
			'pharmacological' => 'Pharmacological',
			'genetic' => 'Genetic',
			'physical' => 'Physical',
			'disease' => 'Disease',
			'cell_state' => 'Cell state',
			'other' => 'Other'
		);
		// Fixed display order; Other always last (not alphabetical / not by count).
		$typeRows = mysqli_fetch_all($db->query(
			"SELECT a.contrast_type AS value, COUNT(DISTINCT b.cont) AS cnt
			 FROM browsetable b
			 INNER JOIN con_annotation a ON a.con = b.cont
			 WHERE b.org = '{$orgEsc}' AND b.mods = '{$modEsc}' AND b.btype = 'condition'
			 GROUP BY a.contrast_type"
		), MYSQLI_ASSOC);
		$countByType = array();
		$totalTypes = 0;
		if(is_array($typeRows)){
			foreach($typeRows as $tr){
				$v = isset($tr['value']) ? (string)$tr['value'] : '';
				$c = isset($tr['cnt']) ? intval($tr['cnt']) : 0;
				if($v === ''){ continue; }
				$countByType[$v] = $c;
				$totalTypes += $c;
			}
		}
		$contrastTypes = array(array('value' => '', 'label' => 'All types', 'count' => $totalTypes));
		$mainOrder = array('pharmacological', 'genetic', 'physical', 'disease', 'cell_state');
		foreach($mainOrder as $v){
			if(!isset($countByType[$v])){ continue; }
			$contrastTypes[] = array(
				'value' => $v,
				'label' => isset($labels[$v]) ? $labels[$v] : $v,
				'count' => $countByType[$v]
			);
			unset($countByType[$v]);
		}
		// Unexpected types (if any) before Other.
		$otherCount = isset($countByType['other']) ? $countByType['other'] : null;
		unset($countByType['other']);
		foreach($countByType as $v => $c){
			$contrastTypes[] = array(
				'value' => $v,
				'label' => isset($labels[$v]) ? $labels[$v] : $v,
				'count' => $c
			);
		}
		if($otherCount !== null){
			$contrastTypes[] = array(
				'value' => 'other',
				'label' => $labels['other'],
				'count' => $otherCount
			);
		}

		$agentWhere = "b.org = '{$orgEsc}' AND b.mods = '{$modEsc}' AND b.btype = 'condition'"
			." AND a.agent_key IS NOT NULL AND a.agent_key <> ''";
		if($contrastType !== ''){
			$ctEsc = $db->real_escape_string($contrastType);
			$agentWhere .= " AND a.contrast_type = '{$ctEsc}'";
		}
		$agentRows = mysqli_fetch_all($db->query(
			"SELECT a.agent_key AS value,
			        COALESCE(NULLIF(d.preferred_name, ''), NULLIF(a.agent_raw, ''), a.agent_key) AS label,
			        COUNT(DISTINCT b.cont) AS cnt
			 FROM browsetable b
			 INNER JOIN con_annotation a ON a.con = b.cont
			 LEFT JOIN agent_dictionary d ON d.agent_key = a.agent_key
			 WHERE {$agentWhere}
			 GROUP BY a.agent_key, label
			 ORDER BY cnt DESC, label
			 LIMIT 400"
		), MYSQLI_ASSOC);
		$agents = array(array('value' => '', 'label' => 'All ontologies', 'count' => 0));
		if(is_array($agentRows)){
			foreach($agentRows as $ar){
				$agents[] = array(
					'value' => isset($ar['value']) ? (string)$ar['value'] : '',
					'label' => isset($ar['label']) ? (string)$ar['label'] : '',
					'count' => isset($ar['cnt']) ? intval($ar['cnt']) : 0
				);
			}
		}
		$db->close();
		echo json_encode(array(
			'contrast_types' => $contrastTypes,
			'agents' => $agents
		));
	}
	elseif($type == "download"){
		$downloadQueryInfo = $_POST["newQueryInfo"];
		$db = connectDB();
		$queryRes = $db->query("select * from qevent where ($downloadQueryInfo) order by timetype desc, qptmscore desc, up, pos");
		$downloadDir = __DIR__ . '/download';
		if(!is_dir($downloadDir)){
			mkdir($downloadDir, 0755, true);
		}
		$tmpfname = tempnam($downloadDir, 'tmp');
		if($tmpfname === false){
			$db->close();
			http_response_code(500);
			echo '';
			exit;
		}
		$handle = fopen($tmpfname, "w");
		fwrite($handle, implode("\t", downloadResultHeader())."\n");
		if($queryRes && isset($queryRes->num_rows) && $queryRes->num_rows > 0){
			$maps = loadDownloadExperimentalMaps($db);
			$batch = array();
			$batchSize = 1000;
			while($row = $queryRes->fetch_assoc()){
				$batch[] = $row;
				if(count($batch) >= $batchSize){
					writeDownloadResultBatch($handle, $db, $batch, $maps);
					$batch = array();
				}
			}
			if(!empty($batch)){
				writeDownloadResultBatch($handle, $db, $batch, $maps);
			}
		}
		fclose($handle);
		$filename = basename($tmpfname);
		chmod($tmpfname, 0644);
		$db->close();
		echo $filename;
		
	}
	elseif($type == "browsechange"){
		$tableType = $_POST["tableType"];
		$nowPage = $_POST["nowPage"];
		$firstWord = $_POST["firstWord"];
		$rowNumber = 10;

		$file = fopen("./count/".$tableType."/".$tableType."_".$firstWord.".txt",'r');
	    $allBrowseItems = explode("\t",fgets($file));
	    fclose($file);
	    /*----- 文件最后一个是多余的，故总数需要减一 -----*/
	    array_pop($allBrowseItems);
	    $showBrowseItems = array_slice($allBrowseItems, ($nowPage-1)*$rowNumber, $rowNumber);
	    $allBrowseItemsNum = count($allBrowseItems);

	    $tableChange = showBrowseTable($showBrowseItems, $rowNumber, $tableType);
		$pageInfoChange = showPageInfo($allBrowseItemsNum, $nowPage, $rowNumber);
		$pageButtonChange = showPageButton($allBrowseItemsNum, $nowPage, $rowNumber);
		$allChangeInfo = array("tableChange" => $tableChange, "pageInfoChange" => $pageInfoChange, "pageButtonChange" => $pageButtonChange);
		echo json_encode($allChangeInfo);
	}
	elseif($type == "qkinact"){

		$tempFile = tempnam("./resource/tmp", "qptm");
        $handle = fopen($tempFile , "w");
        fwrite($handle, $_POST["mpepInput"]);
        fclose($handle);
        chmod($tempFile, 0777);
        qkinactDisplay($tempFile);
/*		if (file_exists($tempFile)) {
            $isDel = unlink($tempFile);
        }*/
    }

    elseif($type == "qkinactchange"){
		$tempFile = $_POST['queryInfoFile'];
        $nowPage = $_POST["nowPage"];
		$rowNumber = $_POST["rowNumber"];
//deal.pl 需要修改成绝对路径
		exec("perl ./deal.pl ".$tempFile,$queryResAll);
		$queryResNum = count($queryResAll);
        $queryRes = array_slice($queryResAll, ($nowPage-1)*$rowNumber, $rowNumber);
        $tableChange = showQKATable($queryRes);
        $pageInfoChange = showPageInfo($queryResNum, $nowPage, $rowNumber);
		$pageButtonChange = showPageButton($queryResNum, $nowPage, $rowNumber);
		$allChangeInfo = array("tableChange" => $tableChange, "pageInfoChange" => $pageInfoChange, "pageButtonChange" => $pageButtonChange);
		echo json_encode($allChangeInfo);
    }
    elseif($type == "browse"){
    	$mods = $_POST["simple_search_mod"];
		$orgs = $_POST["simple_search_org"];
		$tag = $_POST["simple_search_tag"];
		$keyword = $_POST["simple_search_input"];
		$tag2tableIndex = array("condition"=>"samplecondition","gene"=>"gene","sample"=>"sample","up"=>'up');
		$tag2item = array("condition"=>"Condition","gene"=>"Gene name","sample"=>"Sample","up"=>"UniProt ID");
		$mainQueryInfo = $tag2tableIndex[$tag]." = '".$keyword."'";
		$queryContent = 'Search content: '.$tag2item[$tag]." = ".$keyword.'; Organism: '.$orgs.'; Modification: '.$mods;
		if($mods != 'All'){
			$mainQueryInfo = $mainQueryInfo." and mods ='".$mods."'";
		}
		if($orgs != 'All'){
			$mainQueryInfo = $mainQueryInfo." and org ='".$orgs."'";
		}
		queryAndDisplay($mainQueryInfo, $queryContent);
    }
}
elseif(isset($_GET["type"])){
	$type = $_GET["type"];
	if($type == "browse"){
		$tag = $_GET["tag"];
		$keyword = $_GET["keyword"];
		$tag2tableIndex = array("condition"=>"samplecondition","gene"=>"gene","sample"=>"sample","up"=>'up');
		$tag2item = array("condition"=>"Condition","gene"=>"Gene name","sample"=>"Sample","up"=>"UniProt ID");
		$mainQueryInfo = $tag2tableIndex[$tag]." = '".$keyword."'";
		$queryContent = $tag2item[$tag]." = ".$keyword;
		queryAndDisplay($mainQueryInfo, $queryContent);
	}
}
?>
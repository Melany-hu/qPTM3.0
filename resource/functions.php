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
        return $db;
    }
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
			echo "<tr><td>".$row['up']."</td><td>".$row['gene']."</td><td>".$row['sample']."</td><td>".$row['samplecondition']."</td><td>".$row['mods']."</td><td><a target='_blank' href='result.php?uniprot=".$row['up']."'><i class='ri-external-link-fill'></i></a></td></tr>";
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
	if($tag == 'Context'){
		$contableRes = subQuery('con condetail', $keyword, 'contable', 'con', 'samplecondition');
		$samtableRes = subQuery('samdetail', $keyword, 'samtable', 'sam', 'sample');
		$protableRes = subQuery('uniprotaccs genename proteinname func', $keyword, 'protable', 'primaryacc', 'up');

		//$returnQueryInfos = array_merge($returnQueryInfos, subQuery('con condetail', $keyword, 'contable', 'con', 'samplecondition'), subQuery('samdetail', $keyword, 'samtable', 'sam', 'sample'), subQuery('uniprotaccs genename proteinname func', $keyword, 'protable', 'primaryacc', 'up'));
	}	
	elseif($tag == 'con condetail'){
		$contableRes = subQuery($tag, $keyword, 'contable', 'con', 'samplecondition');
		//$returnQueryInfos = array_merge($returnQueryInfos, subQuery($tag, $keyword, 'contable', 'con', 'samplecondition'));
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
		//$returnQueryInfos = array();
		//$returnQueryInfos = array_merge($returnQueryInfos, $protableRes, $samtableRes, $contableRes);	
		return '('.implode(' or ', array_merge($protableRes, $samtableRes, $contableRes)).')';
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

function getResultFilterOptions($mainQueryInfo){
	$db = connectDB();
	$filterFields = array(
		'pos' => 'pos',
		'mods' => 'mods',
		'sample' => 'sample',
		'samplecondition' => 'samplecondition',
		'qptmscore' => 'qptmscore'
	);
	$filterOptions = array();
	foreach($filterFields as $key => $column){
		$orderBy = ($column === 'pos') ? 'CAST(pos AS UNSIGNED) asc' : $column.' desc';
		$queryRes = $db->query("select ".$column." from qevent where (".$mainQueryInfo.") group by ".$column." order by ".$orderBy);
		$values = array();
		if($queryRes){
			while($row = $queryRes->fetch_assoc()){
				$values[] = $row[$column];
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
		$rawdata = $row['mods'].'|'.$row['pmid'].'|'.$row['samplecondition'].'|'.$row['sample'].'|'.$i.'|'.$row['up'].'|'.$row['pos'].'|'.$row['pep'].'|'.$row['qratiopro'].'|'.$row['pvaluepro'].'|'.$row['timefile'].'|'.$row['timetype'].'|'.$row['org'].'|'.$row['fdr'];
		$returnLine = $returnLine."<tr class='Table-line'>
			<td class='col-detail'><button type='button' class='detail-toggle' aria-label='Toggle detail' value=\"".$rawdata."\"><i class='ri-add-circle-fill'></i></button></td>
			<td class='col-uniprot'><a class='result-link' href='https://www.uniprot.org/uniprot/".$row['up']."' target='_blank' rel='noopener'>".$row['up']."</a></td>
			<td class='col-gene'><span class='result-gene'>".$row['gene']."</span></td>
			<td class='col-pos'>".$row['pos']."</td>
            <td class='col-mod'>".showModBadge($row['mods'])."</td>
            <td class='col-pep'>".showPep($row['pep'], $row['mods'])."</td>
            <td class='col-sample'>".$row['sample']."</td>
            <td class='col-condition'>".$row['samplecondition']."</td>
            <td class='col-ratio'>".displayDecimal($row['qratio'])."</td>
            <td class='col-pvalue'>".displayDecimal($row['pvalue'])."</td>
            <td class='col-score'><span class='result-score'>".showPTMscore($row['qptmscore'], $row['fdr'])."</span></td>
		</tr>
		<tr class='Detail-line'>
			<td colspan='11'><div class='detail-loading'><div class='typing-dots' aria-hidden='true'><span></span><span></span><span></span></div>Loading detail...</div></td>
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
	$tag2item = array("Context"=>"Any Field","uniprotaccs"=>"UniProt Accession","genename"=>"Gene Name","proteinname"=>"Protein Name","pos"=>"Position","func"=>"Function","con condetail"=>"Condition","samdetail"=>"Sample");
	$queryContents = array();
	for($i=0;$i<count($tags);$i++){
		array_push($queryContents, ' '.$links[$i].' ');
		array_push($queryContents, $tag2item[$tags[$i]].' = '.$keywords[$i]);

		array_push($mainQueryInfos, ' '.$links[$i].' ');
		$createMainQueryInfoRes = createMainQueryInfo($tags[$i], $keywords[$i]);
		if($createMainQueryInfoRes === false){
			return array('error' => "There are too many matched records with your keyword(s) in '".$tag2item[$tags[$i]]."', please provide a more detailed search plan!");
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
	$queryRes = $db->query("select * from qevent where (".$mainQueryInfo.") order by qptmscore desc, up, pos limit 0, 10");
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
            <th class='arrange' value='mods' width='11%'>Modification<i class='arrow ri-arrow-up-down-fill'></i></th>
    		<th class='arrange' value='pep' width='14%'>SequenceWindow<i class='arrow ri-arrow-up-down-fill'></i></th>
    		<th class='arrange' value='sample' width='9%'>Sample<i class='arrow ri-arrow-up-down-fill'></i></th>       		
    		<th class='arrange' value='samplecondition' width='12%'>Condition<i class='arrow ri-arrow-up-down-fill'></i></th>       		
            <th class='arrange' value='qratio' width='8%'>Log2Ratio<i class='arrow ri-arrow-up-down-fill'></i></th>
    		<th class='arrange' value='pvalue' width='8%'><i>P</i>&nbspvalue<i class='arrow ri-arrow-up-down-fill'></i></th>
    		<th class='arrange' value='qptmscore' width='10%'>Reliability<i class='arrow ri-arrow-up-down-fill'></i></th>
		</tr></thead>
		<thead class='table-light table-sm'><tr>
			<th><div class='form-control form-control-sm border-0'><i class='ri-search-line'></i></div></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='up'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='gene'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='pos'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='mods'></th>
            <th><input class='search-line form-control form-control-sm' type='text' name='pep'></th>
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

/*------ Display external PTM resources in a table ------*/
function displayPTM($ptmRows){
	if(!is_array($ptmRows) || count($ptmRows) === 0){
		return '-';
	}
	$returnPTMInfos = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table'><thead class='thead-dark'><tr><th style='width:45%'>Modification</th><th style='width:20%'>Position</th><th style='width:35%'>Source</th></tr></thead><tbody>";
	foreach($ptmRows as $row){
		$returnPTMInfos = $returnPTMInfos."<tr><td>".htmlspecialchars($row['mods'])."</td><td>".htmlspecialchars($row['pos'])."</td><td>".htmlspecialchars($row['source'])."</td></tr>";
	}
	$returnPTMInfos = $returnPTMInfos."</tbody></table></div>";
	return $returnPTMInfos;
}


/*------ Display PTMD information in a table------*/
function formatPtmdSource($source){
	$source = trim((string)$source);
	if($source === ''){
		return '-';
	}
	$parts = preg_split('/[;,]/', $source);
	$links = array();
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
			$links[] = "<a href='https://ptmd.biocuckoo.cn/' target='_blank' rel='noopener'>".htmlspecialchars($part)."</a>";
		}else{
			$links[] = htmlspecialchars($part);
		}
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
	$rowNum = 10;
	$rowCount = 0;
	$returnSeqInfos = "<table class='table-borderless hide-table hide-more seq-table'><thead><tr>";
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
	$returnSeqInfos = $returnSeqInfos."</tbody></table>";
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

/*------ Display available enzyme information------*/
function displayEnzyme($enzymeInfo,$enzymeType){
	$enzymeInfos = explode('|', $enzymeInfo);
	$returnInfos = "<div class='detail-table-scroll hide-more'><table class='table table-bordered hide-table'><thead class='thead-dark'><tr><th style='width:40%'>".$enzymeType."</th><th style='width:20%'>Inhibitor</th><th style='width:20%'>Structure</th><th style='width:20%'>Source</th></tr></thead><tbody>";
	foreach($enzymeInfos as $singleEnzymeInfo){
		$thisInfo = explode('#', $singleEnzymeInfo);
		if($thisInfo[1] == ''){
			$returnInfos = $returnInfos."<tr><td>".$thisInfo[0]."</td><td>-</td><td>-</td><td>-</td></tr>";
		}else{
			$drugs = explode(',',$thisInfo[1]);
			for($i=0;$i<count($drugs);$i++){
				$drug = $drugs[$i];
				if($i==0){
					$returnInfos = $returnInfos."<tr><td rowspan=".count($drugs).">".$thisInfo[0]."</td><td>".$drug."</td><td>".displayDrugBankStructure($drug)."</td><td>".displayDrugBankLink()."</td></tr>";
				}
				else{
					$returnInfos = $returnInfos."<tr><td>".$drug."</td><td>".displayDrugBankStructure($drug)."</td><td>".displayDrugBankLink()."</td></tr>";
				}
			}
			
		}

	}
	$returnInfos = $returnInfos."</tbody></table></div>";
	return $returnInfos;

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

function showTimeCourse($UniProtID, $pos, $mod, $pmid, $timeFile,$timeType,$thisCon){
	$file = fopen(__DIR__.'/time_course_mat/'.$timeFile.'.txt','r');
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
	$filePath = __DIR__.'/proinfo/'.$uniprot.'.txt';
	$file = @fopen($filePath, 'r');
	if(!$file){
		return $upi;
	}
	while(!feof($file)){
		$thisline = fgets($file);
		$thislineInfo = explode("\t",str_replace("\n", "", $thisline));
		if(count($thislineInfo) > 1){
			$upi[$thislineInfo[0]] = $thislineInfo[1];
	    }
	}
	fclose($file);
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
	$db = connectDB();
	$queryRes = $db->query("select mods, pos from qevent where up = '".$db->real_escape_string($uniprot)."' group by mods, pos order by mods, CAST(pos AS UNSIGNED)");
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
	foreach($grouped as $mod => $positions){
		$parts[] = $mod.':'.implode(',', $positions);
	}
	return implode(';', $parts);
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
	$conQueryRes = $db->query("select * from contable where pmid='{$pmid}' and con = '{$con}'");
	$samQueryRes = $db->query("select * from samtable where sam = '{$sample}'");
	$expQueryRes = $db->query("select * from exptable where pmid='{$pmid}' and mods = '{$mod}'");
	$uniprotEsc = $db->real_escape_string($uniprot);
	$ptmdQueryRes = $db->query("select * from ptmdtable where up='{$uniprotEsc}' order by pos, mods, disease");
	$scoreQueryRes = $db->query("select * from scoretable where scoreid = '".$organism.'#'.$pmid.'#'.$uniprot.'#'.$psite.'#'.$mod."' ");

	// Buffer PTMD rows before closing DB (mysqli result is invalid after close)
	$ptmdRows = fetchPtmdRows($ptmdQueryRes);
	$PTMDqueryResNum = count($ptmdRows);

	$coi = ($conQueryRes && $conQueryRes->num_rows) ? $conQueryRes->fetch_assoc() : null;
	$sai = ($samQueryRes && $samQueryRes->num_rows) ? $samQueryRes->fetch_assoc() : null;
	$exi = ($expQueryRes && $expQueryRes->num_rows) ? $expQueryRes->fetch_assoc() : null;
	$sci = ($scoreQueryRes && $scoreQueryRes->num_rows) ? $scoreQueryRes->fetch_assoc() : null;
	$db->close();

	if(!is_array($coi)){ $coi = array('condetail' => '-'); }
	if(!is_array($sai)){ $sai = array('sampleurl' => '', 'samtype' => ''); }
	if(!is_array($exi)){ $exi = array('tit' => '-', 'labelmethod' => '-', 'enrichmethod' => '-', 'msmethod' => '-'); }

	$probDisplay = displayDash($sci ? str_replace('#', ': ', $sci['prob']) : '');
	$ispspDisplay = displayDash($sci ? $sci['ispsp'] : '');
	$isdbptmDisplay = displayDash($sci ? $sci['isdbptm'] : '');
	$qptmcountDisplay = displayDash($sci ? $sci['qptmcount'] : '');
	$qratioproDisplay = displayDecimal($qratiopro);
	$pvalueproDisplay = displayDecimal($pvaluepro);
	if($qratioproDisplay === '-' && $pvalueproDisplay === '-'){
		$relatedProteinDisplay = '-';
	}else{
		$relatedProteinDisplay = $qratioproDisplay.' (<i>P</i> value = '.$pvalueproDisplay.')';
	}

	$upi = loadProteinInfo($uniprot);
	$props = loadProteinProperties($uniprot, $organism);
	$upi = mergeProteinStructureProperties($upi, $props);
	if(!isset($upi['PTM_qPTM']) || $upi['PTM_qPTM'] === ''){
		$upi['PTM_qPTM'] = buildQptmPtminfo($uniprot);
	}
	$ptmRows = parsePtmsOtherResource(isset($upi['PTMs_other_resource']) ? $upi['PTMs_other_resource'] : '');
	$PTMqueryResNum = count($ptmRows);
	$hasStructureData = isset($upi['Sequence']) && $upi['Sequence'] !== '';

//Detail information about experiment
	$buttonGroup = "<div class='detail-tabs' role='tablist'><button type='button' class='detail-tab active' role='tab' id='exp-".$line."'>Experiment information</button><button type='button' class='detail-tab' role='tab' id='pro-".$line."'>Protein information</button>";
	
	if($mod == 'Phosphorylation'){
		$buttonGroup = $buttonGroup."<button type='button' class='detail-tab' role='tab' id='enz-".$line."'>Potential kinases and their inhibitors</button>";
	}
	elseif($mod == 'Acetylation'){
		$buttonGroup = $buttonGroup."<button type='button' class='detail-tab' role='tab' id='enz-".$line."'>Potential HATs/HDACs and their inhibitors</button>";
	}
	$buttonGroup = $buttonGroup."<button type='button' class='detail-tab show-str' role='tab' id='str-".$line."'>Protein properties</button></div>";

	$divGroup = "<div class='more-info detail-section' id='div-exp-".$line."'>
		<table class='detail-table'>
		<tbody>
			<tr><td>Resource</td><td colspan='6'>".$exi['tit']." (PMID: <a href='https://pubmed.ncbi.nlm.nih.gov/".$pmid."/' target='_blank' rel='noopener'>".$pmid."</a>)"."</td></tr>
			<tr><td>Detail condition</td><td colspan='6'>".$coi['condetail']."</td></tr>
			".($timetype=='0'?'':"<tr><td>Time course change</td><td colspan='6'><span style='display:none' id='timeCourseData-".$line."'>".showTimeCourse($uniprot,$psite,$mod,$pmid,$timefile,$timetype,$con)."</span><div class='timeCourseShow detail-chart' id='timeCourseShow-".$line."'></div></td></tr>")."
			<tr><td>Sample (type)</td><td colspan='6'>".sample2link($sample,$sai['sampleurl']).($sai['samtype']==''?'':" (".$sai['samtype'].")")."</td></tr>
			<tr><td>Label method</td><td colspan='6'>".$exi['labelmethod']."</td></tr>
			<tr><td>Enrichment method</td><td colspan='6'>".$exi['enrichmethod']."</td></tr>
			<tr><td>Mass spectrometer</td><td colspan='6'>".$exi['msmethod']."</td></tr>
			<tr><td>Raw peptide</td><td colspan='6'>".($seqwin === '' || $seqwin === '-' ? displayDash($seqwin) : "<span class='couriernew'>".$seqwin."</span>")."</td></tr>
			<tr><td>Reported PEP/Localization Probability</td><td colspan='6'>".$probDisplay."</td></tr>
			<tr><td>Re-identified FDR</td><td colspan='6'>".displayDash($fdr)."</td></tr>
			<tr class='detail-subgrid'><td>Records in databases</td><td><span class='detail-sub-label'>Collected in PhosphoSitePlus</span><span class='detail-sub-value'>".$ispspDisplay."</span></td><td><span class='detail-sub-label'>Collected in dbPTM</span><span class='detail-sub-value'>".$isdbptmDisplay."</span></td><td colspan='3'><span class='detail-sub-label'>Identified times in qPTM</span><span class='detail-sub-value'>".$qptmcountDisplay."</span></td></tr>
			<tr><td>Related protein change</td><td colspan='6'>".$relatedProteinDisplay."</td></tr>
		</tbody>
		</table>
	</div>";

//Detail information about protein
	$divGroup = $divGroup."<div class='more-info detail-section' id='div-pro-".$line."' style='display:none'>
		<table class='detail-table detail-table-actions'>
		<tbody>
			<tr><td>Uniprot accession</td><td>".($upi['UniProtID'] == ''?"-":ID2links('http://www.uniprot.org/uniprot/', explode(',', $upi['UniProtID'])))."</td><td class='detail-action'></td></tr>
			<tr><td>Protein name</td><td>".str_replace(',',', ',$upi['ProteinName'])."</td><td class='detail-action'></td></tr>
			<tr><td>Gene name</td><td>".($upi['GeneName'] == ''?"-" : str_replace(',',', ',$upi['GeneName']))."</td><td class='detail-action'></td></tr>
			<tr><td>Organism</td><td><em>".$upi['Organism']."</em> NCBI Taxa ID=".ID2links('http://www.ncbi.nlm.nih.gov/Taxonomy/Browser/wwwtax.cgi?lvl=0&id=', array($upi['Taxonomy']))."</td><td class='detail-action'></td></tr>
			<tr><td>Function</td><td class='detail-rich'><span class='hide-text text-less'>".($upi['Function'] == ''?"-":displayFuncDes($upi['Function']))."</span></td><td class='detail-action'><button type='button' class='detail-toggle show-text' aria-label='Expand text'><i class='ri-add-circle-fill'></i></button></td></tr>
			<tr class='known-localization-row'><td>Subcellular localization</td><td class='detail-rich detail-localization'>".buildKnownLocalizationHtml(isset($upi['Localization']) ? $upi['Localization'] : (isset($upi['Subcellular Location']) ? $upi['Subcellular Location'] : ''), isset($upi['Taxonomy']) ? $upi['Taxonomy'] : '9606', $line)."</td><td class='detail-action'></td></tr>
			<tr><td>PTMs for protein<br><span class='detail-count'>(Count: ".$PTMqueryResNum.")</span></td><td class='detail-rich'>".displayPTM($ptmRows)."</td><td class='detail-action'><button type='button' class='detail-toggle show-table' aria-label='Expand table'><i class='ri-add-circle-fill'></i></button></td></tr>
			<tr><td>PTMDs for protein<br><span class='detail-count'>(Count: ".$PTMDqueryResNum.")</span></td><td class='detail-rich'>".displayPTMD($ptmdRows)."</td><td class='detail-action'><button type='button' class='detail-toggle show-table' aria-label='Expand table'><i class='ri-add-circle-fill'></i></button></td></tr>
			<tr><td>Sequence<br><span class='detail-count'>(Length: ".strlen($upi['Sequence']).")</span></td><td class='detail-rich'>".($upi['Sequence'] == ''?"-":displaySequence($upi['Sequence']))."</td><td class='detail-action'><button type='button' class='detail-toggle show-table' aria-label='Expand table'><i class='ri-add-circle-fill'></i></button></td></tr>
			<tr class='protein-structure-row'><td>3D structure</td><td class='detail-rich detail-structure'>".buildProteinStructureHtml($uniprot, $psite, $line, $hasStructureData)."</td><td class='detail-action'></td></tr>
		</tbody>
		</table>
	</div>";

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

		$divGroup = $divGroup."<div class='more-info detail-section' id='div-enz-".$line."' style='display:none'>
		<table class='detail-table detail-table-actions'>
		<tbody>
			<tr><td>Exp.</td><td class='detail-rich'>".($enzi['exp']==''?'-':displayEnzyme($enzi['exp'],'Kinase'))."</td><td class='detail-action'><button type='button' class='detail-toggle show-table' aria-label='Expand table'><i class='ri-add-circle-fill'></i></button></td></tr>
			<tr><td>GPS</td><td class='detail-rich'>".($enzi['gps']==''?'-':displayEnzyme($enzi['gps'],'Kinase'))."</td><td class='detail-action'><button type='button' class='detail-toggle show-table' aria-label='Expand table'><i class='ri-add-circle-fill'></i></button></td></tr>
			<tr><td>iGPS</td><td class='detail-rich'>".($enzi['igps']==''?'-':displayEnzyme($enzi['igps'],'Kinase'))."</td><td class='detail-action'><button type='button' class='detail-toggle show-table' aria-label='Expand table'><i class='ri-add-circle-fill'></i></button></td></tr>
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

		$divGroup = $divGroup."<div class='more-info detail-section' id='div-enz-".$line."' style='display:none'>
		<table class='detail-table detail-table-actions'>
		<tbody>
			<tr><td>Exp.</td><td class='detail-rich'>".($enzi['exp']==''?'-':displayEnzyme($enzi['exp'],'HATs/HDACs'))."</td><td class='detail-action'><button type='button' class='detail-toggle show-table' aria-label='Expand table'><i class='ri-add-circle-fill'></i></button></td></tr>
			<tr><td>Deep-PLA</td><td class='detail-rich'>".($enzi['pla']==''?'-':displayEnzyme($enzi['pla'],'HATs/HDACs'))."</td><td class='detail-action'><button type='button' class='detail-toggle show-table' aria-label='Expand table'><i class='ri-add-circle-fill'></i></button></td></tr>
		</tbody>
		</table>
	</div>";
	}

//Detail information about protein structure
	$surfaceValue = '';
	if(isset($upi['SurfaceAccessbility']) && $upi['SurfaceAccessbility'] !== ''){
		$surfaceValue = $upi['SurfaceAccessbility'];
	}elseif(isset($upi['Surface']) && $upi['Surface'] !== ''){
		$surfaceValue = $upi['Surface'];
	}
	$structureDataInputs = $hasStructureData
		? "<input type='hidden' id='sequence-".$line."' value='".htmlAttr($upi['Sequence'])."'>
			        <input type='hidden' id='ptminfo-".$line."' value='".htmlAttr(isset($upi['PTM_qPTM']) ? $upi['PTM_qPTM'] : '')."'>
			        <input type='hidden' id='disorder-".$line."' value='".htmlAttr(isset($upi['Disorder']) ? $upi['Disorder'] : '')."'>
			        <input type='hidden' id='exposeburied-".$line."' value='".htmlAttr(isset($upi['ExposeBuried']) ? $upi['ExposeBuried'] : '')."'>
			        <input type='hidden' id='polar-".$line."' value='".htmlAttr(isset($upi['Polar']) ? $upi['Polar'] : '')."'>
			        <input type='hidden' id='charge-".$line."' value='".htmlAttr(isset($upi['Charge']) ? $upi['Charge'] : '')."'>
			        <input type='hidden' id='secondstr-".$line."' value='".htmlAttr(isset($upi['Second']) ? $upi['Second'] : '')."'>
			        <input type='hidden' id='surface-".$line."' value='".htmlAttr($surfaceValue)."'>
			        <input type='hidden' id='hydropathy-".$line."' value='".htmlAttr(isset($upi['Hydropathy']) ? $upi['Hydropathy'] : '')."'>"
		: '';
	$structureMessage = $hasStructureData
		? ''
		: "<div class='structure-empty'>Structure annotation is not available for this protein.</div>";

	$divGroup = $divGroup."<div class='more-info detail-section detail-section-str' id='div-str-".$line."' style='display:none'>
		<div class='data' style='display:none;'>
			".$structureDataInputs."
		</div>
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
	</div>";

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
				$buildResult['filterOptions'] = getResultFilterOptions($buildResult['mainQueryInfo']);
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
			if(!isset($buildResult['error'])){
				$buildResult['filterOptions'] = getResultFilterOptions($buildResult['mainQueryInfo']);
			}
			echo json_encode($buildResult);
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
			$tableChange = "<tr><td colspan='10'><div class='alert alert-warning'>Sorry, no matching records found.</div></td></tr>";
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
		$rawdata = $_POST["rawdata"];
		echo addDetailDivInfo($rawdata);
	}
	elseif($type == 'browseFword'){
		$org = $_POST['org'];
		$mod = $_POST['mod'];
		$btype = $_POST['btype'];
		$firstWord = $_POST['firstWord'];
		$db = connectDB();
		$allQueryFirstWord = mysqli_fetch_all($db->query("select fword from browsetable where org = '{$org}' and mods = '{$mod}' and btype = '$btype' group by fword"), MYSQLI_NUM);
		$db->close();
		$returnFirstWordList = array();
		foreach($allQueryFirstWord as $singleFirstWord){
			array_push($returnFirstWordList, $singleFirstWord[0]);
		}
		echo json_encode($returnFirstWordList);
	}
	elseif($type == 'browseOption'){
		$org = $_POST['org'];
		$mod = $_POST['mod'];
		$btype = $_POST['btype'];
		$firstWord = $_POST['firstWord'];
		$optionNumber = $_POST['optionNumber'];
		$nowPage = $_POST['nowPage'];
		$db = connectDB();
		if($firstWord == ''){
			$allQueryFirstWord = mysqli_fetch_all($db->query("select fword from browsetable where org = '{$org}' and mods = '{$mod}' and btype = '$btype' group by fword"), MYSQLI_NUM);
			$firstWord = $allQueryFirstWord[0][0];
		}
		$allQueryContent = mysqli_fetch_all($db->query("select cont from browsetable where org = '{$org}' and mods = '{$mod}' and btype = '$btype' and fword = '{$firstWord}' order by cont limit ".(($nowPage-1)*$optionNumber).','.$optionNumber), MYSQLI_NUM);

		$queryResAll = $db->query("select count(*) from browsetable where org = '{$org}' and mods = '{$mod}' and btype = '$btype' and fword = '{$firstWord}'");
		if(!isset($queryResAll->num_rows)){
			$queryResNum = 0;
		}
		else{
			$queryResNum = $queryResAll->fetch_assoc()['count(*)'];
		}

		$db->close();
		$returnContentList = array();
		foreach($allQueryContent as $singleQueryContent){
			array_push($returnContentList, trim($singleQueryContent[0]));
		}
		echo json_encode(array('totalNum'=>$queryResNum,'nowList'=>$returnContentList));
	}
	elseif($type == "download"){
		$downloadQueryInfo = $_POST["newQueryInfo"];
		$db = connectDB();
		$queryRes = $db->query("select * from qevent where ($downloadQueryInfo) order by qptmscore desc, up, pos");
		if(!isset($queryRes->num_rows) or $queryRes->num_rows == 0){
				$resultsNumber=0;
			}
		else{
			$resultsNumber = $queryRes->num_rows;
		}
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
		fwrite($handle, "UniProt\tGene\tPosition\tSequence window\tModification\tSample\tCondition\tLog2Ratio\tpvalue\tReliability\tsite-level FDR\n");
		for($i=0;$i<$resultsNumber;$i++) {
			$row = $queryRes->fetch_assoc();
			fwrite($handle, $row['up']."\t".$row['gene']."\t".$row['pos']."\t".$row['pep']."\t".$row['mods']."\t".$row['sample']."\t".$row['samplecondition']."\t".$row['qratio']."\t".$row['pvalue']."\t".$row['qptmscore']."\t".$row['fdr']."\n");
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
/*----- Check submit form -----*/
function check_simple_search_form()
{
	if($('#simple_search_input0').val()=='')
	{
		alert('Please input your keyword(s), thanks.');
		return false;
	}
}

function check_advance_search_form()
{
	if($('#advance_search_form #adv_simple_search_input0').val()=='')
	{
		alert('The first search row must have keyword(s), thanks.');
		return false;
	}
}

/*----- Get filter part information -----*/
function getFilterInfo(){
	var filterInfos = [];
	$(".filter-div").each(function(){
		var Tag = $(this).attr("value");
		var selected = [];
		$(this).find(".filter-tag.selected").each(function(){
			selected.push(Tag + " = '" + $(this).attr("data-val") + "'");
		});
		if(selected.length > 0){
			filterInfos.push('(' + selected.join(' or ') + ')');
		}
	});
	return filterInfos;
}

/*----- Get search part information -----*/
function getSearchInfo(){
	var searchInfos = [];
	$("input.search-line").each(function(){
		if($(this).val() != ''){
			searchInfos.push($(this).attr("name") + " like '%" + $(this).val() + "%'");
		}
	});
	return searchInfos;
}

/*----- Get order information -----*/
function getOrderInfo(){
	var orderTag = '';
	var orderSort = '';
	$('.arrow').each(function(){
		if($(this).hasClass('ri-sort-asc')){
			orderTag = $(this).closest('.arrange').attr('value');
			orderSort = 'asc';
		}
		else if($(this).hasClass('ri-sort-desc')){
			orderTag = $(this).closest('.arrange').attr('value');
			orderSort = 'desc';
		}
	})
	if(orderTag == ''){
		orderInfos = 'timetype desc, qptmscore desc, up, pos';
	}
	else{
		orderInfos = orderTag+' '+orderSort;
	}
	return orderInfos;
}

/*----- Main function for result page change -----*/
function changeResultTable(nowPage){
	var rawQueryInfo = [$('#rawQueryInfo').text()];
	var filterInfos = getFilterInfo();
	var searchInfos = getSearchInfo();
	var orderInfos = getOrderInfo();
	var rowNumber = Number($('#selectRowNumber').val());

	var newQueryInfos = [].concat(rawQueryInfo, filterInfos, searchInfos);
	var newQueryInfo = newQueryInfos.join(" and ");

	$.post("./resource/functions.php", {"type":"change", "newQueryInfo":newQueryInfo, "nowPage":nowPage, "rowNumber":rowNumber, "orderInfo":orderInfos}, function(returnInfo, status){
		if(status == 'success'){
			var changeInfo = JSON.parse(returnInfo);
			$("#tableChange").html(changeInfo["tableChange"]);
			$("#pageInfo").html(changeInfo["pageInfoChange"]);
			$("#pageButton").html(changeInfo["pageButtonChange"]);
		}
		else{
			alert('Failed, please try again!')
		}
	})
}

/*----- Download result table function -----*/
function downloadResultTable(){
	var rawQueryInfo = [$('#rawQueryInfo').text()];
	var filterInfos = getFilterInfo();
	var searchInfos = getSearchInfo();
	var newQueryInfos = [].concat(rawQueryInfo, filterInfos, searchInfos);
	var newQueryInfo = newQueryInfos.join(" and ");
	$.post("./resource/functions.php", {"type":"download", "newQueryInfo":newQueryInfo}, function(returnInfo, status){
		if(status == 'success'){
			let alink = document.createElement("a");
			alink.download="qPTM.result.txt";
			alink.href="./resource/download/"+returnInfo;
			alink.click();
		}
		else{
			alert('Failed, please try again!')
		}
	})
}

/*----- Main function for qkinact page change -----*/
function changeQueryTable(nowPage){
	var queryInfoFile = $('#queryInfoFile').text();
	var rowNumber = Number($('#selectRowNumber').val());
	if(!queryInfoFile){
		alert('Failed, please try again!');
	}
	else{
		$.post("./resource/functions.php", {"type":"qkinactchange", "queryInfoFile":queryInfoFile, "nowPage":nowPage, "rowNumber":rowNumber}, function(returnInfo, status){
			if(status == 'success'){
				var changeInfo = JSON.parse(returnInfo);
				$("#queryTableChange").html(changeInfo["tableChange"]);
				$("#queryPageInfo").html(changeInfo["pageInfoChange"]);
				$("#queryPageButton").html(changeInfo["pageButtonChange"]);
			}
			else{
				alert('Failed, please try again!')
			}
		})
	}
}

$(document).ready(function(){
	/*----- qKinAct row number -----*/
	$('#query #selectRowNumber').on('change',function(){
		changeQueryTable(1);
	})
	$(document).on('click','#query .page-item',function(){
		if(!$(this).hasClass("disabled") & !$(this).hasClass("active")){
			var choosePage = Number($(this).find("a").first().attr("value"));
			changeQueryTable(choosePage);
		}
	})
	/*----- Back to top -----*/
	$(window).scroll(function(){
		if($(this).scrollTop() > 300) $('.back-to-top').addClass('active');
		else $('.back-to-top').removeClass('active');
	});
	$('.back-to-top').on('click',function(e){
		e.preventDefault();
		$('html, body').animate({scrollTop:0}, 300);
	});
})

/*----- Tooltip -----*/
$(function () {
  if (window.initQptmTooltips) {
    window.initQptmTooltips();
  } else {
    $('[data-toggle="tooltip"]').tooltip({
      template: '<div class="tooltip qptm-tooltip" role="tooltip"><div class="arrow"></div><div class="tooltip-inner"></div></div>',
      delay: { show: 280, hide: 80 },
      container: 'body',
      boundary: 'window'
    });
  }
})

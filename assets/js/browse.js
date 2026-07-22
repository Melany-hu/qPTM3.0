/**
* Author: Qingfeng Zhang
* Version: 1.0
*/
// Define functions


function showPageInfo(totalNum,rowNumber,nowPage,btype){
  var lineStart = 0;
  if(totalNum > 0){
    var lineStart = (nowPage-1)*rowNumber+1;
  }
  var lineEnd = nowPage*rowNumber;
  if(lineEnd > totalNum){
    lineEnd = totalNum;
  }
  return "Showing "+lineStart+" to "+lineEnd+" of "+totalNum+" "+btype+"s";
}

function showSingleButton(buttonValue, buttonContain, nowPage, pageNumber){
  if(buttonContain == '<'){
    if(nowPage == 1){
      return "<li class='page-item disabled'><span class='page-link'>"+buttonContain+"</span></li>";
    }else{
      return "<li class='page-item'><a class='page-link' href='javascript:void(0)' value='"+(nowPage-1)+"'>"+buttonContain+"</a></li>";
    }
  }else if(buttonContain == '>'){
    if(nowPage == pageNumber){
      return "<li class='page-item disabled'><span class='page-link'>"+buttonContain+"</span></li>";
    }else{
      return "<li class='page-item'><a class='page-link' href='javascript:void(0)' value='"+(nowPage+1)+"'>"+buttonContain+"</a></li>";
    }
  }else if(buttonContain == '...'){
    return "<li class='page-item disabled'><span class='page-link'>"+buttonContain+"</span></li>";
  }else{
    if(buttonValue == nowPage){
      return "<li class='page-item active'><span class='page-link'>"+buttonContain+"</span></li>";
    }else{
      return "<li class='page-item'><a class='page-link' href='javascript:void(0)' value='"+buttonValue+"'>"+buttonContain+"</a></li>";
    }
  }
}

function showButtonInfo(totalNum,rowNumber,nowPage){
  var pageNumber = Math.ceil(totalNum/rowNumber);
  var retunButtonInfo = '';
  if(pageNumber>1){
    retunButtonInfo = retunButtonInfo+"<nav aria-label='Page navigation' class='float-right'><ul class='pagination'>";
    retunButtonInfo = retunButtonInfo+showSingleButton('', '<', nowPage, pageNumber);
    if(pageNumber<8){
      for(var i=1;i<pageNumber+1;i++){
        retunButtonInfo = retunButtonInfo+showSingleButton(i, i, nowPage, pageNumber);
      }
    }else if(nowPage<5){
      for(var i=1;i<6;i++){
        retunButtonInfo = retunButtonInfo+showSingleButton(i, i, nowPage, pageNumber);
      }
      retunButtonInfo = retunButtonInfo+showSingleButton('', '...', nowPage, pageNumber);
      retunButtonInfo = retunButtonInfo+showSingleButton(pageNumber, pageNumber, nowPage, pageNumber);
    }else if(nowPage>pageNumber-4){
      retunButtonInfo = retunButtonInfo+showSingleButton(1, 1, nowPage, pageNumber);
      retunButtonInfo = retunButtonInfo+showSingleButton('', '...', nowPage, pageNumber);
      for(var i=pageNumber-4;i<pageNumber+1;i++){
        retunButtonInfo = retunButtonInfo+showSingleButton(i, i, nowPage, pageNumber);
      }
    }else{
      retunButtonInfo = retunButtonInfo+showSingleButton(1, 1, nowPage, pageNumber);
      retunButtonInfo = retunButtonInfo+showSingleButton('', '...', nowPage, pageNumber);
      for(var i=nowPage-1;i<nowPage+2;i++){
        retunButtonInfo = retunButtonInfo+showSingleButton(i, i, nowPage, pageNumber);
      }
      retunButtonInfo = retunButtonInfo+showSingleButton('', '...', nowPage, pageNumber);
      retunButtonInfo = retunButtonInfo+showSingleButton(pageNumber, pageNumber, nowPage, pageNumber);
    }
    retunButtonInfo = retunButtonInfo+showSingleButton('', '>', nowPage, pageNumber);
    retunButtonInfo = retunButtonInfo+"</ul></nav>";
  }
    return retunButtonInfo;
}


function showBrowseFword(btype,fWordList){
  var returnHTML = '';
  for(var i in fWordList){
    returnHTML += '<span class="browseFilter '+(i==0?'active':'')+'" value="'+fWordList[i]+'">'+(fWordList[i]=='ZZ'?'#':fWordList[i])+'</span>';
  }
  $('#'+btype+'-fword').html(returnHTML);
}

function showBrowseOption(btype,optionList){
  var rowOptionNum = parseInt($('#'+btype+'-selectColNumber').val());
  var returnHTML = '';
  for(var i=0; i<optionList.length;i+=rowOptionNum){
    returnHTML += '<tr>';
    for(var j=i; j<i+rowOptionNum;j++){
      if(j < optionList.length){
        returnHTML += '<td><span class="browseRes">'+optionList[j]+'</span></td>';
      }
      else{
        returnHTML += '<td></td>';
      }
    }
    returnHTML += '</tr>';
  }
  $('#'+btype+'-option-show tbody').html(returnHTML);
}

//异步搜索并返回结果。
function browseFwordByAJAX(organism,mod,btype,firstWord){
  var formData = new FormData();
  formData.append('type','browseFword');
  formData.append('org',organism);
  formData.append('mod',mod);
  formData.append('btype',btype);
  formData.append('firstWord',firstWord);
  $.ajax({
    url:'./resource/functions.php',
    type:'post',
    data: formData,
    contentType: false,
    processData: false,
    success:function(res){
      //console.log(res);
      var returnInfo = JSON.parse(res);
      showBrowseFword(btype,returnInfo);
    },
    error:function(res){
      console.log(res);
      }
  })
}

function browseOptionByAJAX(organism,mod,btype,firstWord,nowPage){
  var optionNumber = $('#'+btype+'-selectColNumber').val()*$('#'+btype+'-selectRowNumber').val();
  var formData = new FormData();
  formData.append('type','browseOption');
  formData.append('org',organism);
  formData.append('mod',mod);
  formData.append('btype',btype);
  formData.append('firstWord',firstWord);
  formData.append('optionNumber',optionNumber);
  formData.append('nowPage',nowPage);
  $.ajax({
    url:'./resource/functions.php',
    type:'post',
    data: formData,
    contentType: false,
    processData: false,
    success:function(res){
      //console.log(res);
      var returnInfo = JSON.parse(res);
      $('#'+btype+'-pageInfo').html(showPageInfo(returnInfo['totalNum'],optionNumber,nowPage,btype));
      $('#'+btype+'-buttonInfo').html(showButtonInfo(returnInfo['totalNum'],optionNumber,nowPage));
      showBrowseOption(btype,returnInfo['nowList']);
    },
    error:function(res){
      console.log(res);
      }
  })
}

function createBOption(optionType, optionData, barColor){
  var option = {
    title: {
          text: "Summary for "+optionType,
          show:true,
          top:0,
          left: 50,
          textStyle: {
              color: '#595b5d',
              fontSize:15
          }
      },
      tooltip : {
          trigger: 'axis',
          axisPointer: {
                type: 'shadow'
            },
          textStyle:{align:'left'}                    
      },
      grid: {
          left: 50,
          right: 10,
          bottom: 80,
          top: 30,
          containLabel: false
      },
      xAxis : [
          {
            show:true,
            type : 'category',
            axisLabel: {  
               interval:0,  
               rotate:40  
            },
            data : optionData['name']
          }
      ],
      yAxis : [
          {
            show: true,
            type : 'value',
            axisTick: {
            show:true
          },
            axisLine: {
              show:true
            }
          }
      ],
      series : [
        {
          name:"Total Number",
          type:"bar",
          barWidth: "70%",
          itemStyle: {
            normal: {
              color: barColor
            }
          },
          data: optionData['value']
        }
      ],
      dataZoom: [
          {
            show: false,
            realtime: true,
            start:0,
            end:100
          },
          {
            type: 'inside',
            realtime: true
          }
      ]
  };
  return option;
}
function showBtypeStat(dataStat){
  var myChart0 = echarts.init(document.getElementById('gene-stat-plot'));
  var option0 = createBOption('Gene', dataStat['gene'], 'red');
  myChart0.setOption(option0);

  var myChart1 = echarts.init(document.getElementById('condition-stat-plot'));
  var option1 = createBOption('Condition', dataStat['condition'], 'blue');
  myChart1.setOption(option1);

  var myChart2 = echarts.init(document.getElementById('sample-stat-plot'));
  var option2 = createBOption('Sample', dataStat['sample'], 'green');
  myChart2.setOption(option2);
}

function showModOption(showMods){
  var returnHTML = '';
  for(var i in showMods){
    returnHTML += '<li class="nav-item">\
                    <a class="nav-link '+(i==0?'active':'')+'" value="'+showMods[i]+'" href="javascript:void(0);">'+showMods[i]+'</a>\
                </li>';
  }
  $('#browse-control-mod .nav-tabs').html(returnHTML);
}

function post(URL, PARAMS) {        
    var temp = document.createElement("form");
    temp.action = URL;
    temp.method = "post";
    temp.style.display = "none";
    temp.target = '_blank';
    for (var x in PARAMS) {
        var opt = document.createElement("textarea");
        opt.name = x;
        opt.value = PARAMS[x];
        temp.appendChild(opt);
    }
    document.body.appendChild(temp);
    temp.submit();
    return temp;
}

$(document).ready(function(){
  var browseData = {"Human": {"gene": {"name": ["Acetylation", "Glycosylation", "Methylation", "Phosphorylation", "SUMOylation", "Ubiquitylation"], "value": [6904, 2819, 17129, 17029, 7536, 9977]}, "condition": {"name": ["Acetylation", "Glycosylation", "Methylation", "Phosphorylation", "SUMOylation", "Ubiquitylation"], "value": [72, 97, 32, 1057, 30, 82]}, "sample": {"name": ["Acetylation", "Glycosylation", "Methylation", "Phosphorylation", "SUMOylation", "Ubiquitylation"], "value": [25, 41, 16, 564, 10, 27]}}, "Mouse": {"gene": {"name": ["Acetylation", "Glycosylation", "Methylation", "Phosphorylation", "SUMOylation", "Ubiquitylation"], "value": [6292, 1698, 3527, 10863, 56, 3136]}, "condition": {"name": ["Acetylation", "Glycosylation", "Methylation", "Phosphorylation", "SUMOylation", "Ubiquitylation"], "value": [64, 19, 6, 512, 1, 7]}, "sample": {"name": ["Acetylation", "Glycosylation", "Methylation", "Phosphorylation", "SUMOylation", "Ubiquitylation"], "value": [15, 7, 3, 86, 2, 5]}}, "Rat": {"gene": {"name": ["Acetylation", "Phosphorylation", "Ubiquitylation"], "value": [899, 3975, 286]}, "condition": {"name": ["Acetylation", "Phosphorylation", "Ubiquitylation"], "value": [19, 102, 3]}, "sample": {"name": ["Acetylation", "Phosphorylation", "Ubiquitylation"], "value": [7, 29, 1]}}, "Yeast": {"gene": {"name": ["Acetylation", "Glycosylation", "Phosphorylation", "Ubiquitylation"], "value": [6, 125, 4254, 2483]}, "condition": {"name": ["Acetylation", "Glycosylation", "Phosphorylation", "Ubiquitylation"], "value": [4, 2, 548, 10]}, "sample": {"name": ["Acetylation", "Glycosylation", "Phosphorylation", "Ubiquitylation"], "value": [1, 1, 22, 6]}}};
  var selectOrg = 'Human';
  var selectMod = browseData[selectOrg]['gene']['name'][0];

  $('.chooseOrg').text(selectOrg);
  $('.chooseMod').text(selectMod);

  var btype2firstWord = {'gene':'','condition':'','sample':''};
  var btype2page = {'gene':1,'condition':1,'sample':1};
  showBtypeStat(browseData[selectOrg]);
  showModOption(browseData[selectOrg]['gene']['name']);

  browseFwordByAJAX(selectOrg,selectMod,'gene',btype2firstWord['gene']);
  browseFwordByAJAX(selectOrg,selectMod,'condition',btype2firstWord['condition']);
  browseFwordByAJAX(selectOrg,selectMod,'sample',btype2firstWord['sample']);

  browseOptionByAJAX(selectOrg,selectMod,'gene',btype2firstWord['gene'],btype2page['gene']);
  browseOptionByAJAX(selectOrg,selectMod,'condition',btype2firstWord['condition'],btype2page['condition']);
  browseOptionByAJAX(selectOrg,selectMod,'sample',btype2firstWord['sample'],btype2page['sample']);


	$('#browse-control-org').on('click','.nav-link',function(){
        //browseChart.clear();
        if(!$(this).hasClass('active')){
            selectOrg = $(this).attr('value');
            selectMod = browseData[selectOrg]['gene']['name'][0];

            var btype2firstWord = {'gene':'','condition':'','sample':''};
            var btype2page = {'gene':1,'condition':1,'sample':1};

            $('.chooseOrg').text(selectOrg);
            $('.chooseMod').text(selectMod);

            //console.log(selectOrg);
            $('#browse-control-org .nav-link').removeClass('active');
            $(this).addClass('active');
            showBtypeStat(browseData[selectOrg]);
            showModOption(browseData[selectOrg]['gene']['name']);

            browseFwordByAJAX(selectOrg,selectMod,'gene',btype2firstWord['gene']);
            browseFwordByAJAX(selectOrg,selectMod,'condition',btype2firstWord['condition']);
            browseFwordByAJAX(selectOrg,selectMod,'sample',btype2firstWord['sample']);

            browseOptionByAJAX(selectOrg,selectMod,'gene',btype2firstWord['gene'],btype2page['gene']);
            browseOptionByAJAX(selectOrg,selectMod,'condition',btype2firstWord['condition'],btype2page['condition']);
            browseOptionByAJAX(selectOrg,selectMod,'sample',btype2firstWord['sample'],btype2page['sample']);
        }
   	})

  $('#browse-control-mod').on('click','.nav-link',function(){
        //browseChart.clear();
        if(!$(this).hasClass('active')){
            selectMod = $(this).attr('value');

            var btype2firstWord = {'gene':'','condition':'','sample':''};
            var btype2page = {'gene':1,'condition':1,'sample':1};

            $('.chooseMod').text(selectMod);

            //console.log(selectOrg);
            $('#browse-control-mod .nav-link').removeClass('active');
            $(this).addClass('active');
            browseFwordByAJAX(selectOrg,selectMod,'gene',btype2firstWord['gene']);
            browseFwordByAJAX(selectOrg,selectMod,'condition',btype2firstWord['condition']);
            browseFwordByAJAX(selectOrg,selectMod,'sample',btype2firstWord['sample']);

            browseOptionByAJAX(selectOrg,selectMod,'gene',btype2firstWord['gene'],btype2page['gene']);
            browseOptionByAJAX(selectOrg,selectMod,'condition',btype2firstWord['condition'],btype2page['condition']);
            browseOptionByAJAX(selectOrg,selectMod,'sample',btype2firstWord['sample'],btype2page['sample']);
          }
  })

  $(document).on('click','#browse .tab-pane .browseFilter', function(){

    if(! $(this).hasClass('active')){
      var thisbtype = $(this).closest('.tab-pane').attr('id').split('-')[0];
      btype2firstWord[thisbtype] = $(this).attr('value');
      $(this).closest('.tab-pane').find('.active').removeClass('active');
      $(this).addClass('active');
      btype2page[thisbtype] = 1;
      browseOptionByAJAX(selectOrg,selectMod,thisbtype,btype2firstWord[thisbtype],btype2page[thisbtype]);
    }
  })

   	/*----- Table row number change function -----*/
  $('#browse .selectRowNumber').on('change',function(){
    var thisbtype = $(this).attr('id').split('-')[0];
    btype2page[thisbtype] = 1;
    browseOptionByAJAX(selectOrg,selectMod,thisbtype,btype2firstWord[thisbtype],btype2page[thisbtype]);
  })

  /*----- Arrange the table -----*/
  /*
  $(document).on('click', '.arrange', function(){
    var changeClass = '';
    if($(this).find('.arrow').hasClass('ri-arrow-up-down-fill') | $(this).find('.arrow').hasClass('ri-sort-asc')){
      changeClass = 'ri-sort-desc';
      var orderSort = 'desc';
    }
    else{
      changeClass = 'ri-sort-asc';
      var orderSort = 'asc';
    }
    $('.arrange').find('.ri-sort-desc').removeClass('ri-sort-desc').addClass('ri-arrow-up-down-fill');
    $('.arrange').find('.ri-sort-asc').removeClass('ri-sort-asc').addClass('ri-arrow-up-down-fill');
    $(this).find('.arrow').removeClass('ri-arrow-up-down-fill').removeClass('ri-sort-desc').removeClass('ri-sort-asc').addClass(changeClass);

    var orderTag = $(this).attr('value');
    orderInfo = orderTag+' '+orderSort;
    browseResultByAJAX(selectOrg,rowNumber,nowPage,orderInfo);
  })
*/
  /*----- Page change function -----*/
  $(document).on('click','#browse .page-item',function(){
    if(!$(this).hasClass("disabled") & !$(this).hasClass("active")){
      var thisbtype = $(this).closest('.buttonInfo').attr('id').split('-')[0];
      //console.log($(this).closest('.buttonInfo'));
      btype2page[thisbtype] = parseInt($(this).find("a").first().attr("value"));
      //console.log(nowPage);
      browseOptionByAJAX(selectOrg,selectMod,thisbtype,btype2firstWord[thisbtype],btype2page[thisbtype]);
    }
  })

   /*----- Browse result -----*/
   $(document).on('click','#browse .browseRes',function(){
    var searchContent = $(this).text();
    var thisbtype = $(this).closest('.table').attr('id').split('-')[0];
    var data = {"type":"browse","simple_search_tag":thisbtype,"simple_search_input":searchContent,"simple_search_mod":selectMod,"simple_search_org":selectOrg};
    post('./result.php',data);
  })

})

//protein structure show 
function listLength(sequence){
  listSequence = [];
  for(var i=0;i<sequence.length;i++){
    listSequence.push(i+1);
  }
  return listSequence;
}

function showPTM(sequence,ptminfo){
  var mod_color ={'Hydroxyisobutyrylation':'#fda7ec','Acetylation':'#8fc3fb','Butyrylation':'#38e04d','Crotonylation':'#58a9f0','Methylation':'#f9c3c5','Phosphorylation':'#f0b952','Succinylation':'#d2a871','SUMOylation':'#d5d953','Ubiquitination':'#86d986','Ubiquitylation':'#86d986','Glycosylation':'#74d6ec'};
  var PTMreturn = [];
  var singlePTMs = ptminfo.split(';');
  for(var i=0;i<singlePTMs.length;i++){
    var singlePTMtype = singlePTMs[i].split(':')[0];
    var singlePTMInfo = singlePTMs[i].split(':')[1].split(',');
    var PTMsite = [];
    for(var j = 0;j<singlePTMInfo.length;j++){
      PTMsite.push(Number(singlePTMInfo[j])-1);
    }
    var singlePTMres = [];
    for(var j=0;j<sequence.length;j++){
      var residue = sequence[j]+(j+1);
      if(PTMsite.indexOf(j) > -1){
        singlePTMres.push([j,1,mod_color[singlePTMtype],residue]);
      }
      else{
        singlePTMres.push([j,0,mod_color[singlePTMtype],residue]);
      }
    }
    PTMreturn.push({"name":singlePTMtype,"type":"bar","barWidth": "5","stack": "total","itemStyle": {"normal": {"color": mod_color[singlePTMtype],}},"data":singlePTMres});
  }
  return PTMreturn;
}

function showDisorder(sequence,disorder){
  var singleDisorders = disorder.split(',');
  var singleDisordersD = [];
  var singleDisordersO = [];
  for(var i=0;i<sequence.length;i++){
    var score = parseFloat(singleDisorders[i]);
    if(score > 0.5){
      singleDisordersD.push(1);
      singleDisordersO.push(0);
    }else{
      singleDisordersD.push(0);
      singleDisordersO.push(1);
    }
  }
  return [singleDisordersD, singleDisordersO];
}

function showSecond(sequence,second){
  var singleStructures = second.split(',');
  var singleStructuresA = [];
  var singleStructuresB = [];
  var singleStructuresC = [];
  for(var i=0;i<sequence.length;i++){
    var struc = singleStructures[i];
    if(struc === 'A'){
      singleStructuresA.push(1);
      singleStructuresB.push(0);
      singleStructuresC.push(0);
    }else if(struc === 'B'){
      singleStructuresA.push(0);
      singleStructuresB.push(1);
      singleStructuresC.push(0);
    }else{
      singleStructuresA.push(0);
      singleStructuresB.push(0);
      singleStructuresC.push(1);
    }
  }
  return [singleStructuresA, singleStructuresB, singleStructuresC];
}

function showSurface(sequence,surface){
  singleSurfaces = surface.split(',');
  surfaceReturn = [];
  for(var i=0;i<singleSurfaces.length;i++){
    var labelinfo = sequence[i]+(i+1)+'<br> Score: '+singleSurfaces[i];
    surfaceReturn.push([i,Number(singleSurfaces[i]),labelinfo]);
  }
  return surfaceReturn;
}

function showExpose(sequence,expose){
  var singleEBs = expose.split(',');
  var singleEBE = [];
  var singleEBB = [];
  for(var i=0;i<sequence.length;i++){
    var score = parseInt(singleEBs[i], 10);
    if(score === 1){
      singleEBE.push(1);
      singleEBB.push(0);
    }else{
      singleEBE.push(0);
      singleEBB.push(1);
    }
  }
  return [singleEBE, singleEBB];
}

function showPolar(sequence,polar){
  var singlePolars = polar.split(',');
  var singlePolarP = [];
  var singlePolarN = [];
  for(var i=0;i<sequence.length;i++){
    var score = parseInt(singlePolars[i], 10);
    if(score === 1){
      singlePolarP.push(1);
      singlePolarN.push(0);
    }else{
      singlePolarP.push(0);
      singlePolarN.push(1);
    }
  }
  return [singlePolarP, singlePolarN];
}

function showCharge(sequence,charge){
  var singleCharges = charge.split(',');
  var singleChargeP = [];
  var singleChargeN = [];
  var singleChargeU = [];
  for(var i=0;i<sequence.length;i++){
    var score = parseInt(singleCharges[i], 10);
    if(score === 1){
      singleChargeP.push(1);
      singleChargeN.push(0);
      singleChargeU.push(0);
    }else if(score === -1){
      singleChargeP.push(0);
      singleChargeN.push(1);
      singleChargeU.push(0);
    }else{
      singleChargeP.push(0);
      singleChargeN.push(0);
      singleChargeU.push(1);
    }
  }
  return [singleChargeP, singleChargeN, singleChargeU];
}

function binaryBarTooltipFormatter(sequence){
  return function(params){
    var tipinfo = '<strong>'+sequence[parseInt(params[0].name, 10)-1]+params[0].name+'</strong>';
    for(var i=0;i<params.length;i++){
      if(params[i].value === 1){
        tipinfo = tipinfo+'<br>'+params[i].marker+params[i].seriesName;
      }
    }
    return tipinfo;
  };
}

function compactTitle(text){
  return {
    text: text,
    show: true,
    top: 10,
    left: 40,
    textStyle: {
      color: '#1a2330',
      fontSize: 14
    }
  };
}

function compactLegend(data){
  return {
    data: data,
    top: 10,
    right: 50,
    textStyle: {
      color: '#90979c',
      fontSize: 12
    }
  };
}

function compactGrid(){
  return {
    left: 50,
    right: 50,
    bottom: 5,
    top: 40,
    containLabel: false
  };
}

function ptmGrid(){
  return {
    left: 50,
    right: 50,
    bottom: 18,
    top: 40,
    containLabel: false
  };
}

function hiddenDataZoom(){
  return [{
    show: false,
    realtime: true,
    start: 0,
    end: 100
  }, {
    type: 'inside',
    realtime: true
  }];
}

function showStructureZoomOption(sequence){
  return {
    grid: {
      left: 50,
      right: 50,
      top: 0,
      bottom: 0,
      height: 0
    },
    xAxis: [{
      type: 'category',
      show: false,
      data: listLength(sequence),
      axisTick: {
        alignWithLabel: true
      }
    }],
    yAxis: [{
      type: 'value',
      show: false
    }],
    series: [{
      type: 'bar',
      data: [],
      silent: true
    }],
    dataZoom: [{
      show: true,
      realtime: true,
      start: 0,
      end: 100,
      left: 50,
      right: 50,
      top: 0,
      height: 30,
      handleColor: '#0e74d3',
      backgroundColor: '#ffffff'
    }, {
      type: 'inside',
      realtime: true
    }]
  };
}

function makeBinaryBarOption(title, legendData, seriesData, colors, sequence){
  var series = [];
  for(var i=0;i<legendData.length;i++){
    series.push({
      name: legendData[i],
      type: 'bar',
      barWidth: '100%',
      stack: 'total',
      xAxisIndex: 0,
      itemStyle: {
        normal: {
          color: colors[i]
        }
      },
      data: seriesData[i]
    });
  }
  return {
    title: compactTitle(title),
    tooltip: {
      trigger: 'axis',
      textStyle: {align: 'left'},
      formatter: binaryBarTooltipFormatter(sequence)
    },
    legend: compactLegend(legendData),
    grid: compactGrid(),
    xAxis: [{
      show: false,
      type: 'category',
      data: listLength(sequence),
      axisTick: {
        alignWithLabel: true
      }
    }],
    yAxis: [{
      type: 'value',
      show: false,
      min: 0,
      max: 1.02
    }],
    series: series,
    dataZoom: hiddenDataZoom()
  };
}

function showExposeOption(sequence, expose){
  var exposeInfo = showExpose(sequence, expose);
  return makeBinaryBarOption(
    'Exposed & Buried',
    ['Exposed', 'Buried'],
    exposeInfo,
    ['#4dabf7', '#dddddd'],
    sequence
  );
}

function showDisorderOption(sequence, disorder){
  var disorderInfo = showDisorder(sequence, disorder);
  return makeBinaryBarOption(
    'Disorder',
    ['Disordered', 'Ordered'],
    disorderInfo,
    ['#4dabf7', '#dddddd'],
    sequence
  );
}

function showSecondOption(sequence, second){
  var secondInfo = showSecond(sequence, second);
  return makeBinaryBarOption(
    'Second structure',
    ['Alpha-helix', 'Beta-strand', 'Coil'],
    secondInfo,
    ['#ff8787', '#3bc9db', '#4dabf7'],
    sequence
  );
}

function showPolarOption(sequence, polar){
  var polarInfo = showPolar(sequence, polar);
  return makeBinaryBarOption(
    'Polar',
    ['Polar', 'Nonpolar'],
    polarInfo,
    ['#4dabf7', '#dddddd'],
    sequence
  );
}

function showChargeOption(sequence, charge){
  var chargeInfo = showCharge(sequence, charge);
  return makeBinaryBarOption(
    'Charge',
    ['Positive', 'Negative', 'Uncharged'],
    chargeInfo,
    ['#ff8787', '#4dabf7', '#dee2e6'],
    sequence
  );
}

function showHydropathy(sequence,hydropathy){
  var singleHydropathy = hydropathy.split(',');
  var hydropathyReturn = [];
  for(var i=0;i<singleHydropathy.length;i++){
    var labelinfo = sequence[i]+(i+1)+'<br> Score: '+singleHydropathy[i];
    hydropathyReturn.push([i,Number(singleHydropathy[i]),labelinfo]);
  }
  return hydropathyReturn;
}

function showLegand(ptminfo){
  var Legandreturn = [];
  var singlePTMs = ptminfo.split(';');
  for(var i=0;i<singlePTMs.length;i++){
    var singlePTMtype = singlePTMs[i].split(':')[0];
    Legandreturn.push(singlePTMtype);
  }
  return Legandreturn;
}

function disposeStructureCharts(line) {
  ['structure-zoom', 'ptmshow', 'disordershow', 'exposeshow', 'polarshow', 'chargeshow', 'secondstrshow', 'surfaceshow', 'hydropathyshow'].forEach(function(prefix) {
    var chartDom = document.getElementById(prefix + '-' + line);
    if (!chartDom) {
      return;
    }
    var existingChart = echarts.getInstanceByDom(chartDom);
    if (existingChart) {
      existingChart.dispose();
    }
    chartDom.innerHTML = '';
    chartDom.removeAttribute('_echarts_instance_');
  });
}

var structureRenderTokens = {};

function initStructureChart(domId) {
  var chartDom = document.getElementById(domId);
  if (!chartDom) {
    return null;
  }
  return echarts.init(chartDom);
}

function isActiveChart(chart) {
  return chart && !(typeof chart.isDisposed === 'function' && chart.isDisposed());
}

function scheduleStructureResize(line, renderToken, charts) {
  window.requestAnimationFrame(function() {
    if (structureRenderTokens[line] !== renderToken) {
      return;
    }
    charts.forEach(function(chart) {
      if (!isActiveChart(chart)) {
        return;
      }
      try {
        chart.resize();
      } catch (e) {
        // Chart may have been disposed before resize runs.
      }
    });
  });
}

function get_mordetail(line){
  var ptminfo = $('#ptminfo-'+line).val() || '';
  var sequence = $('#sequence-'+line).val() || '';
  var disorder = $('#disorder-'+line).val() || '';
  var exposeburied = $('#exposeburied-'+line).val() || '';
  var polar = $('#polar-'+line).val() || '';
  var charge = $('#charge-'+line).val() || '';
  var surface = $('#surface-'+line).val() || '';
  var secondstr = $('#secondstr-'+line).val() || '';
  var hydropathy = $('#hydropathy-'+line).val() || '';

  if (!sequence) {
    $('#ptmshow-'+line).html('<div class="structure-empty">Structure annotation is not available for this protein.</div>');
    $('#structure-zoom-'+line).empty();
    $('#disordershow-'+line).empty();
    $('#exposeshow-'+line).empty();
    $('#polarshow-'+line).empty();
    $('#chargeshow-'+line).empty();
    $('#secondstrshow-'+line).empty();
    $('#surfaceshow-'+line).empty();
    $('#hydropathyshow-'+line).empty();
    return;
  }

  disposeStructureCharts(line);
  structureRenderTokens[line] = (structureRenderTokens[line] || 0) + 1;
  var renderToken = structureRenderTokens[line];
  var charts = [];

  var zoomChart = initStructureChart('structure-zoom-'+line);
  if (!zoomChart) {
    return;
  }
  zoomChart.setOption(showStructureZoomOption(sequence));
  charts.push(zoomChart);

  if (!ptminfo) {
    $('#ptmshow-'+line).html('<div class="structure-empty">No PTM annotation available.</div>');
  } else {
  var option0 = {
    title: compactTitle('PTMs'),
    tooltip : {
        trigger: 'axis',
        textStyle:{align:'left'},
        formatter: function (params) {
          var tipinfo = params[0].data[3];
          for(var i=0;i<params.length;i++){
            if(params[i].data[1] == 1){
              tipinfo = tipinfo+'<br><span style="display:inline-block;margin-right:5px;border-radius:10px;width:10px;height:10px;background-color:'+params[i].data[2]+'"></span>'+params[i].seriesName;
            }
          }
          return tipinfo;
        }
    },
    legend: compactLegend(showLegand(ptminfo)),
    grid: ptmGrid(),
    xAxis : [
        {
          type : 'category',
          show: true,
          data : listLength(sequence),
          axisTick: {
            alignWithLabel: true
          },
          axisLabel: {
            fontSize: 10,
            interval: 'auto'
          }
        }
    ],
    yAxis : [
        {
          type : 'value',
          show: false
        }
    ],
    series : showPTM(sequence,ptminfo),
    dataZoom: hiddenDataZoom()
  };
  var myChart0 = initStructureChart('ptmshow-'+line);
  if (myChart0) {
    myChart0.setOption(option0);
    charts.push(myChart0);
  }
  }

  function renderLineChart(domId, title, seriesName, seriesData, sequence){
    var option = {
      title: compactTitle(title),
      color: ['#5799e0'],
      tooltip : {
        confine:false,
        trigger: 'axis',
        textStyle:{align:'left'},
        formatter: function (params) {
          return params[0].data[2];
        }
      },
      grid: compactGrid(),
      xAxis : [
        {
          show:false,
          type : 'category',
          data : listLength(sequence),
          axisTick: {
            alignWithLabel: true
          }
        }
      ],
      yAxis : [
        {
          type : 'value',
          axisTick: { show: true },
          axisLine: { show: true }
        }
      ],
      series : [
        {
          symbolSize: 0,
          name: seriesName,
          type:'line',
          smooth: '0.2',
          data: seriesData
        }
      ],
      dataZoom: hiddenDataZoom()
    };
    var chart = initStructureChart(domId);
    if (!chart) {
      return null;
    }
    chart.setOption(option);
    return chart;
  }

  function toggleChartContainer(prefix, visible){
    var el = document.getElementById(prefix + '-' + line);
    if (el) {
      el.style.display = visible ? '' : 'none';
    }
  }

  if (disorder) {
    toggleChartContainer('disordershow', true);
    var myChart1 = initStructureChart('disordershow-'+line);
    if (myChart1) {
      myChart1.setOption(showDisorderOption(sequence, disorder));
      charts.push(myChart1);
    }
  } else {
    toggleChartContainer('disordershow', false);
  }

  if (exposeburied) {
    toggleChartContainer('exposeshow', true);
    var myChartExpose = initStructureChart('exposeshow-'+line);
    if (myChartExpose) {
      myChartExpose.setOption(showExposeOption(sequence, exposeburied));
      charts.push(myChartExpose);
    }
  } else {
    toggleChartContainer('exposeshow', false);
  }

  if (polar) {
    toggleChartContainer('polarshow', true);
    var myChartPolar = initStructureChart('polarshow-'+line);
    if (myChartPolar) {
      myChartPolar.setOption(showPolarOption(sequence, polar));
      charts.push(myChartPolar);
    }
  } else {
    toggleChartContainer('polarshow', false);
  }

  if (charge) {
    toggleChartContainer('chargeshow', true);
    var myChartCharge = initStructureChart('chargeshow-'+line);
    if (myChartCharge) {
      myChartCharge.setOption(showChargeOption(sequence, charge));
      charts.push(myChartCharge);
    }
  } else {
    toggleChartContainer('chargeshow', false);
  }

  if (secondstr) {
    toggleChartContainer('secondstrshow', true);
    var myChart2 = initStructureChart('secondstrshow-'+line);
    if (myChart2) {
      myChart2.setOption(showSecondOption(sequence, secondstr));
      charts.push(myChart2);
    }
  } else {
    toggleChartContainer('secondstrshow', false);
  }

  if (surface) {
    toggleChartContainer('surfaceshow', true);
    var surfaceChart = renderLineChart('surfaceshow-'+line, 'Surface accessibility', 'surface', showSurface(sequence, surface), sequence);
    if (surfaceChart) {
      charts.push(surfaceChart);
    }
  } else {
    toggleChartContainer('surfaceshow', false);
  }

  if (hydropathy) {
    toggleChartContainer('hydropathyshow', true);
    var hydropathyChart = renderLineChart('hydropathyshow-'+line, 'Hydropathy', 'Hydropathy', showHydropathy(sequence, hydropathy), sequence);
    if (hydropathyChart) {
      charts.push(hydropathyChart);
    }
  } else {
    toggleChartContainer('hydropathyshow', false);
  }

  var activeCharts = charts.filter(isActiveChart);
  if (activeCharts.length > 1) {
    echarts.connect(activeCharts);
  }
  scheduleStructureResize(line, renderToken, activeCharts);
}



function drawTimeCourse(drawDivID){
  var thisLine = drawDivID.split('-')[1];
  var $dataEl = $('#timeCourseData-'+thisLine);
  var $chartEl = $('#'+drawDivID);

  if($dataEl.text() === '-'){
    $chartEl.html('<span class="structure-empty">Time course data is not available.</span>');
    return;
  }

  var timeCourseData = JSON.parse($dataEl.text());
  var chartDom = document.getElementById(drawDivID);
  if(!chartDom){
    return;
  }

  var myChart = echarts.getInstanceByDom(chartDom) || echarts.init(chartDom);
  var conditions = timeCourseData.condition || [];
  var timeLabels = timeCourseData.timeLabels || conditions;
  var values = (timeCourseData.values || []).map(function(value){
    var num = parseFloat(value);
    return isNaN(num) ? null : num;
  });
  var highlightIndex = -1;

  if(timeCourseData.conMarker && timeCourseData.conMarker.length > 0){
    var marker = timeCourseData.conMarker[0];
    highlightIndex = conditions.indexOf(marker.xAxis);
    if(highlightIndex < 0 && marker.value){
      highlightIndex = timeLabels.indexOf(marker.value);
    }
  }

  var rotateLabels = timeLabels.length > 6;
  var option = {
    color: ['#0e74d3'],
    tooltip: {
      trigger: 'axis',
      confine: true,
      backgroundColor: 'rgba(255,255,255,0.96)',
      borderColor: '#d4e1f5',
      borderWidth: 1,
      padding: [10, 12],
      textStyle: {
        color: '#1a2330',
        fontSize: 12,
        align: 'left'
      },
      formatter: function(params){
        var point = params[0];
        var idx = point.dataIndex;
        var condition = conditions[idx] || point.name;
        var value = point.value;
        var valueText = (typeof value === 'number' && !isNaN(value)) ? value.toFixed(2) : '-';
        var marker = idx === highlightIndex ? '<br/><span style="color:#e03131;font-weight:600;">Current condition</span>' : '';
        return '<strong>' + condition + '</strong><br/>Log<sub>2</sub> Ratio: ' + valueText + marker;
      }
    },
    grid: {
      left: 12,
      right: 16,
      bottom: rotateLabels ? 28 : 16,
      top: 12,
      containLabel: true
    },
    xAxis: [{
      type: 'category',
      data: timeLabels,
      boundaryGap: false,
      axisLine: {
        lineStyle: { color: '#b3ccf5' }
      },
      axisTick: {
        alignWithLabel: true,
        lineStyle: { color: '#b3ccf5' }
      },
      axisLabel: {
        color: '#5c6b7a',
        fontSize: 11,
        interval: 0,
        rotate: rotateLabels ? 35 : 0,
        margin: 14
      }
    }],
    yAxis: [{
      type: 'value',
      name: 'Log2 Ratio',
      nameTextStyle: {
        color: '#5c6b7a',
        fontSize: 11
      },
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: {
        lineStyle: {
          color: '#e8effa',
          type: 'dashed'
        }
      },
      axisLabel: {
        color: '#5c6b7a',
        fontSize: 11
      }
    }],
    series: [{
      name: 'Log2 Ratio',
      type: 'line',
      smooth: 0.35,
      connectNulls: false,
      symbol: 'circle',
      symbolSize: function(value, params){
        return params.dataIndex === highlightIndex ? 10 : 6;
      },
      lineStyle: {
        width: 2.5,
        color: '#0e74d3'
      },
      itemStyle: {
        color: function(params){
          return params.dataIndex === highlightIndex ? '#e03131' : '#0e74d3';
        },
        borderColor: '#fff',
        borderWidth: 2
      },
      emphasis: {
        scale: true,
        itemStyle: {
          borderWidth: 3,
          shadowBlur: 8,
          shadowColor: 'rgba(14,116,211,0.35)'
        }
      },
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            { offset: 0, color: 'rgba(14,116,211,0.22)' },
            { offset: 1, color: 'rgba(14,116,211,0.02)' }
          ]
        }
      },
      markLine: {
        silent: true,
        symbol: 'none',
        lineStyle: {
          color: '#90979c',
          type: 'dashed',
          width: 1
        },
        label: { show: false },
        data: [{ yAxis: 0 }]
      },
      data: values
    }]
  };

  if(timeLabels.length > 12){
    option.dataZoom = hiddenDataZoom();
  }

  myChart.setOption(option, true);

  if(window.ResizeObserver && !chartDom._timeCourseObserved){
    chartDom._timeCourseObserved = true;
    var resizeObserver = new ResizeObserver(function(){
      myChart.resize();
    });
    resizeObserver.observe(chartDom);
  }

  window.requestAnimationFrame(function(){
    myChart.resize();
  });
}
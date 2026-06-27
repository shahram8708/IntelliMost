document.addEventListener('DOMContentLoaded',function(){
  var chart=null;var canvas=document.getElementById('analyticsChart');
  function build(){
    if(!canvas||!window.Chart)return;
    var metric=document.getElementById('metricSelect').value;
    var days=document.getElementById('daysSelect').value;
    var line=document.getElementById('lineSelect').value;
    var type=document.querySelector('input[name="chartType"]:checked').value;
    apiFetch('/analytics/data?metric='+metric+'&days='+days+'&line_id='+line)
      .then(function(r){return r.json();}).then(function(d){
        if(chart)chart.destroy();
        chart=new Chart(canvas,{type:type,data:d,options:{responsive:true,maintainAspectRatio:false}});
        renderTable(d);
      });
  }
  function renderTable(d){
    var tb=document.getElementById('dataTableBody');if(!tb)return;tb.innerHTML='';
    var vals=d.datasets[0].data;
    d.labels.forEach(function(l,i){tb.innerHTML+='<tr><td>'+l+'</td><td>'+vals[i]+'</td></tr>';});
  }
  ['metricSelect','daysSelect','lineSelect'].forEach(function(id){
    var el=document.getElementById(id);if(el)el.addEventListener('change',build);});
  document.querySelectorAll('input[name="chartType"]').forEach(function(r){r.addEventListener('change',build);});
  var exp=document.getElementById('exportChart');
  if(exp){exp.addEventListener('click',function(){if(chart){var a=document.createElement('a');a.href=chart.toBase64Image();a.download='chart.png';a.click();}});}
  build();
});

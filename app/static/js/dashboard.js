function readJSON(id){var el=document.getElementById(id);return el?JSON.parse(el.textContent):null;}
function makeChart(id,type,data,opts){var c=document.getElementById(id);if(!c||!window.Chart)return null;
  return new Chart(c,{type:type,data:data,options:Object.assign({responsive:true,maintainAspectRatio:false},opts||{})});}

document.addEventListener('DOMContentLoaded',function(){
  document.querySelectorAll('canvas[data-chart]').forEach(function(c){
    var d=readJSON(c.getAttribute('data-chart'));if(d){makeChart(c.id,c.getAttribute('data-type')||'bar',d);}
  });
  if(document.getElementById('kpi-oee')){
    setInterval(refreshMetrics,300000);
  }
});

function refreshMetrics(){
  apiFetch('/api/dashboard/metrics').then(function(r){return r.json();}).then(function(d){
    setText('kpi-oee',d.oee);setText('kpi-attainment',d.attainment_percent);
    setText('kpi-alerts',d.active_alerts);setText('kpi-downtime',d.active_downtime_events);
  }).catch(function(){});
}
function setText(id,v){var el=document.getElementById(id);if(el){el.textContent=v;}}

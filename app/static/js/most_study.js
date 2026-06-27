document.addEventListener('DOMContentLoaded',function(){
  var methodRadios=document.querySelectorAll('input[name="most_method"]');
  function showParams(){
    var m=document.querySelector('input[name="most_method"]:checked');
    if(!m)return;
    document.querySelectorAll('.param-group').forEach(function(g){g.style.display='none';});
    var grp=document.getElementById('params-'+m.value);
    if(grp)grp.style.display='';
    computeTmu();
  }
  methodRadios.forEach(function(r){r.addEventListener('change',showParams);});
  document.querySelectorAll('.most-idx,#idx_tool_tmu').forEach(function(s){s.addEventListener('change',computeTmu);});

  function computeTmu(){
    var m=document.querySelector('input[name="most_method"]:checked');
    if(!m)return;
    var grp=document.getElementById('params-'+m.value);
    if(!grp)return;
    var sum=0;
    grp.querySelectorAll('.most-idx').forEach(function(s){sum+=parseInt(s.value||0,10);});
    var tmu=sum*10;
    if(m.value==='tool_use'){var t=document.getElementById('idx_tool_tmu');if(t)tmu+=parseInt(t.value||0,10);}
    var out=document.getElementById('liveTmu');if(out)out.textContent=tmu;
  }
  showParams();

  var aiBtn=document.getElementById('aiSuggest');
  if(aiBtn){
    aiBtn.addEventListener('click',function(){
      var name=document.querySelector('[name="element_name"]').value;
      var desc=document.querySelector('[name="element_description"]').value;
      aiBtn.disabled=true;aiBtn.textContent='Thinking...';
      apiFetch('/api/most/suggest-indices',{method:'POST',body:JSON.stringify({element_name:name,element_description:desc})})
        .then(function(r){return r.json();}).then(function(d){
          var radio=document.querySelector('input[name="most_method"][value="'+d.method+'"]');
          if(radio){radio.checked=true;showParams();}
          var grp=document.getElementById('params-'+d.method);
          if(grp&&d.index_values){
            Object.keys(d.index_values).forEach(function(k){
              var sel=grp.querySelector('[name="idx_'+k+'"]');
              if(sel){sel.value=d.index_values[k];}
            });
          }
          computeTmu();
          var badge=document.getElementById('aiConfidence');
          if(badge){badge.style.display='';badge.textContent='AI confidence: '+Math.round((d.confidence||0)*100)+'%';}
          var hid=document.getElementById('ai_suggested');if(hid)hid.value='1';
        }).catch(function(){alert('AI suggestion failed.');})
        .finally(function(){aiBtn.disabled=false;aiBtn.textContent='Get AI Suggestion';});
    });
  }
});

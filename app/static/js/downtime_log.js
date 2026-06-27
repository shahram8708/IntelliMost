document.addEventListener('DOMContentLoaded',function(){
  document.querySelectorAll('.machine-tile').forEach(function(t){
    t.addEventListener('click',function(){
      document.querySelectorAll('.machine-tile').forEach(function(x){x.classList.remove('selected');});
      t.classList.add('selected');
      document.getElementById('machine_id').value=t.getAttribute('data-id');
    });
  });
  document.querySelectorAll('.etype-tile').forEach(function(t){
    t.addEventListener('click',function(){
      document.querySelectorAll('.etype-tile').forEach(function(x){x.classList.remove('selected');});
      t.classList.add('selected');
      document.getElementById('event_type').value=t.getAttribute('data-val');
    });
  });
  document.querySelectorAll('.reason-tile').forEach(function(t){
    t.addEventListener('click',function(){
      document.querySelectorAll('.reason-tile').forEach(function(x){x.classList.remove('selected');});
      t.classList.add('selected');
      document.getElementById('reason_code_id').value=t.getAttribute('data-id');
    });
  });
  var nowBtn=document.getElementById('startNow');
  if(nowBtn){nowBtn.addEventListener('click',function(){
    document.getElementById('start_time').value=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);});}
});

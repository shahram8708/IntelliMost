function getCSRF(){const m=document.querySelector('meta[name="csrf-token"]');return m?m.getAttribute('content'):'';}
window.apiFetch=function(url,opts){opts=opts||{};opts.headers=Object.assign({'Content-Type':'application/json','X-CSRFToken':getCSRF()},opts.headers||{});return fetch(url,opts);};

document.addEventListener('DOMContentLoaded',function(){
  var toggle=document.getElementById('sidebarToggle');
  var sb=document.getElementById('appSidebar');
  if(toggle&&sb){toggle.addEventListener('click',function(){sb.classList.toggle('open');});}

  document.querySelectorAll('.flash-msg').forEach(function(el){
    setTimeout(function(){el.style.transition='opacity .4s,transform .4s';el.style.opacity='0';el.style.transform='translateY(-8px)';setTimeout(function(){el.remove();},400);},5000);
  });

  document.querySelectorAll('[data-confirm]').forEach(function(f){
    f.addEventListener('submit',function(e){if(!confirm(f.getAttribute('data-confirm'))){e.preventDefault();}});
  });

  document.querySelectorAll('input[type="datetime-local"][data-now]').forEach(function(i){
    if(!i.value){i.value=new Date(Date.now()-new Date().getTimezoneOffset()*60000).toISOString().slice(0,16);}
  });

  if(window.bootstrap){
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function(t){new bootstrap.Tooltip(t);});
  }
});

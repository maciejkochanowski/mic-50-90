/* Offline controls shared by standalone reports and the sandboxed app view. */
(function(root){
 'use strict';
 const bound=new WeakSet();
 function save(blob,name){const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
 function svgText(button){const block=button.closest('.result-chart-block'),link=block.querySelector('[data-save-svg]');const href=link?.getAttribute('href')||'';if(href.startsWith('data:image/svg+xml;charset=utf-8,'))return decodeURIComponent(href.slice(href.indexOf(',')+1));return new XMLSerializer().serializeToString(block.querySelector('svg'));}
 function preparePrint(doc){
  if(document.getElementById('report-print-area'))return;
  document.getElementById('report-print-area')?.remove();
  const area=document.createElement('div');area.id='report-print-area';area.hidden=true;
  const source=doc.querySelector('main');
  if(source)area.append(source.cloneNode(true));
  else{const main=document.createElement('main');for(const child of doc.body.childNodes)main.append(child.cloneNode(true));area.append(main);}
  area.querySelectorAll('article').forEach(article=>{const metadata=article.querySelector('dl.metadata')?.closest('details');if(metadata)article.append(metadata);});
  area.querySelectorAll('script,iframe,button,.result-actions,.pager,.report-controls').forEach(el=>el.remove());
  area.querySelectorAll('details').forEach(el=>el.open=true);area.querySelectorAll('[hidden]').forEach(el=>el.hidden=false);
  document.body.append(area);document.documentElement.classList.add('mic-printing');
 }
 function finishPrint(){
  document.getElementById('report-print-area')?.remove();
  document.documentElement.classList.remove('mic-printing');
 }
 async function printReport(doc){
  await Promise.all([doc.fonts.ready,document.fonts.ready]);
  preparePrint(doc);await document.fonts.ready;root.print();
 }
 root.addEventListener('afterprint',finishPrint);
 function bind(doc,resize=()=>{}){
  if(bound.has(doc)){resize();return;}
  bound.add(doc);
  if(doc!==document)doc.body.classList.add('embedded-report');
  if(!doc.querySelector('[data-print-report]')){
   const actions=doc.createElement('div');actions.className='result-actions';
   const button=doc.createElement('button');button.type='button';button.dataset.printReport='';
   button.textContent='Print / save as PDF';actions.append(button);
   (doc.querySelector('main')||doc.body).prepend(actions);
  }
  doc.querySelectorAll('[data-save-svg]').forEach(button=>button.onclick=e=>{e.preventDefault();save(new Blob([svgText(button)],{type:'image/svg+xml;charset=utf-8'}),'MIC-50-90-chart.svg');});
  doc.querySelectorAll('[data-save-png]').forEach(button=>{button.hidden=false;button.onclick=async()=>{
   await doc.fonts.ready;
   const svg=button.closest('.result-chart-block').querySelector('svg'),box=svg.viewBox.baseVal,canvas=document.createElement('canvas');
   canvas.width=1840;canvas.height=Math.ceil(1840*box.height/box.width);const image=new Image();
   image.onload=()=>{const ctx=canvas.getContext('2d');ctx.fillStyle='white';ctx.fillRect(0,0,canvas.width,canvas.height);ctx.drawImage(image,0,0,canvas.width,canvas.height);canvas.toBlob(blob=>{if(blob)save(blob,'MIC-50-90-chart.png');},'image/png');};
   image.src='data:image/svg+xml;charset=utf-8,'+encodeURIComponent(svgText(button));
  };});
  doc.querySelectorAll('[data-print-report]').forEach(button=>{button.hidden=false;button.onclick=()=>printReport(doc);});
  const articles=[...doc.querySelectorAll('article')];
  if(articles.length>1&&!doc.querySelector('.report-controls')){
   const nav=doc.createElement('nav');nav.className='report-controls';nav.setAttribute('aria-label','Choose a sample');
   const label=doc.createElement('label');label.textContent='Sample: ';const select=doc.createElement('select');select.id='result-cohort';select.setAttribute('aria-label','Sample to display');
   select.add(new Option('All samples, 50 per page','all'));articles.forEach((article,i)=>select.add(new Option(article.querySelector('h2')?.textContent||'Sample '+(i+1),String(i))));
   label.append(select);nav.append(label);const previous=doc.createElement('button'),next=doc.createElement('button'),status=doc.createElement('span');previous.textContent='Previous page';next.textContent='Next page';nav.append(previous,status,next);
   articles[0].before(nav);let page=0;
   const show=()=>{const all=select.value==='all',pages=Math.ceil(articles.length/50);articles.forEach((article,i)=>article.hidden=all?Math.floor(i/50)!==page:i!==Number(select.value));previous.hidden=next.hidden=!all||pages===1;previous.disabled=page===0;next.disabled=page===pages-1;status.textContent=all?' Page '+(page+1)+' of '+pages+' · '+articles.length+' samples ':' One of '+articles.length+' samples ';resize();};
   select.onchange=()=>{page=0;show();};previous.onclick=()=>{page--;show();};next.onclick=()=>{page++;show();};doc.querySelectorAll('.pager').forEach(el=>el.hidden=true);
   const followHash=()=>{
    let id;try{id=decodeURIComponent(doc.defaultView.location.hash.slice(1));}catch{return;}
    if(!id)return;
    const target=doc.getElementById(id),index=articles.indexOf(target?.closest('article'));
    if(index<0)return;
    select.value=String(index);show();target.scrollIntoView({block:'start'});
   };
   doc.defaultView.addEventListener('hashchange',followHash);show();followHash();
  }
  doc.querySelectorAll('details').forEach(el=>el.addEventListener('toggle',resize));
  resize();
 }
 root.MIC50Report={bind,printReport};
 // The application binds from its host; scripts remain blocked inside its report iframe.
 if(root.top===root && document.getElementById('mic-report-controls')){
  const start=()=>bind(document);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});
  else start();
  root.addEventListener('beforeprint',()=>preparePrint(document));
 }
})(window);

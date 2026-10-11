/* The form prepares existing inputs; all scientific calculations run locally in Python. */
(function () {
  'use strict';
  const M=window.MicFormModel, $=id=>document.getElementById(id);
  const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  let payload=M.blank(),step=0,session=null,jobId=null,running=false,levelsDirty=false;
  let completedFiles=[],completedPayload=null,reportObserver=null;
  const fragment=new URLSearchParams(location.hash.slice(1));
  let token=fragment.get('token')||sessionStorage.getItem('mic-50-90-token')||'';
  if(token) sessionStorage.setItem('mic-50-90-token',token);
  if(location.hash) history.replaceState(null,'',location.pathname+location.search);
  function notice(message) { $('notice').hidden=!message;$('notice').textContent=message||''; }
  function guarded(fn) { return (...args)=>{try {const p=fn(...args);if(p&&p.catch)p.catch(e=>notice(e.message));} catch(e){notice(e.message);}}; }
  async function downloadReport(url,name) {
    const response=await fetch(url);
    if(!response.ok)throw new Error('The report could not be downloaded.');
    const objectUrl=URL.createObjectURL(await response.blob()),link=document.createElement('a');
    link.href=objectUrl;link.download=name;link.click();
    setTimeout(()=>URL.revokeObjectURL(objectUrl),1000);
  }
  async function api(route,body) {
    const response=await fetch(route,{method:body===undefined?'GET':'POST',headers:{Authorization:'Bearer '+token,...(body===undefined?{}:{'Content-Type':'application/json'})},body:body===undefined?undefined:JSON.stringify(body),cache:'no-store'});
    const data=await response.json();
    if(!response.ok) throw new Error(data.error||data.message||('The local request could not be completed ('+response.status+').'));
    return data;
  }
  function linkWithToken(url) { const target=new URL(url,location.origin);if(target.origin!==location.origin)throw new Error('An output link must remain local.');target.searchParams.set('token',token);return target.href; }
  function fieldValue(id) {return $(id).value;}
  function setValue(id,value) {$(id).value=value??'';}
  function selected(value,actual) {return String(value)===String(actual)?' selected':'';}
  function checked(value) {return value?' checked':'';}
  function categoryOptions(value,empty='Not supplied') {
    const labels=M.panelLabels(payload.config.panel||{});
    if(value!=null&&!labels.includes(String(value)))labels.push(String(value));
    return '<option value="">'+empty+'</option>'+labels.map(x=>'<option value="'+esc(x)+'"'+selected(x,value)+'>'+esc(x)+'</option>').join('');
  }
  function input(label,value,extra='') {return '<label>'+label+'<input value="'+esc(value)+'" '+extra+'></label>';}
  function removeButton(label,index) {return '<button type="button" class="quiet" data-remove="'+index+'" aria-label="Remove '+label+'">Remove</button>';}
  function setOptional(object,key,value) {if(value==null||value==='')delete object[key];else object[key]=value;}
  function invalidate() {$('validation').replaceChildren();notice('');if(!running&&!$('job').hidden)$('job-title').textContent='Previous report · the input has changed';}
  const isDocument=()=>payload.input_format==='tables'||payload.mode==='verify-report';
  function collect() {
    if(payload.mode==='verify-report'){
      const text=fieldValue('certificate-text');
      if(!text.trim()){delete payload.certificate;delete payload.certificate_json;throw new Error('Paste or open the received certificate before checking it.');}
      const imported=M.certificateInput(text);payload.certificate=imported.certificate;payload.certificate_json=text;
      return payload;
    }
    if(payload.input_format==='tables'){
      payload.mode=fieldValue('table-mode');payload.tables={};
      for(const name of ['input','panels','targets','additional_counts']){const text=fieldValue('table-'+name);if(text.trim())payload.tables[name]={text,delimiter:fieldValue('delimiter-'+name)};}
      if(payload.mode==='reporting-audit')payload.options.reporting_plan=$('table-reporting-plan').checked;
      else delete payload.options.reporting_plan;
      return payload;
    }
    const c=payload.config;
    c.cohort_id=fieldValue('cohort').trim()||'My sample';c.n=M.integer(fieldValue('n'));c.unit=fieldValue('unit');
    for(const [id,key] of [['organism','organism'],['antimicrobial','antimicrobial'],['panel-id','panel_id'],['source','source']])setOptional(c,key,fieldValue(id).trim());
    M.setSampleContext(c,{host_species:fieldValue('host-species'),specimen:fieldValue('specimen'),repeat_sampling:fieldValue('repeat-sampling'),grouping_notes:fieldValue('grouping-notes'),intended_population:fieldValue('intended-population')});
    if(levelsDirty&&fieldValue('panel-kind')==='levels')applyLevels();
    if(payload.mode!=='reporting-audit'){
      collectQuantiles($('quantiles'),c);
      [...$('variants').children].forEach((el,i)=>collectQuantiles(el,c.reporting_envelope.variants[i]));
      c.summaries ||= {};setOptional(c.summaries,'minimum',fieldValue('minimum'));setOptional(c.summaries,'maximum',fieldValue('maximum'));
      payload.options.precision_pp=M.number(fieldValue('precision'));
      payload.options.population_precision_pp=$('iid').checked?M.number(fieldValue('population-precision')):null;
      payload.options.population_count_plan=$('iid').checked&&$('population-count-plan').checked;
      payload.options.population_minimum_bins=M.integer(fieldValue('population-minimum-bins'));
      payload.options.population_method=fieldValue('population-method');
      payload.options.population_time_limit=M.number(fieldValue('time-limit'));
      payload.options.population_tolerance_pp=M.number(fieldValue('tolerance'));
      if(payload.mode==='batch'){payload.options.decision_plan=$('decision-plan').checked;payload.options.acquisition_plan=$('acquisition-plan').checked;}
    } else {
      $('histogram').querySelectorAll('input').forEach((el,i)=>{payload.histogram[i].count=M.integer(el.value);});
      payload.rank_convention=fieldValue('histogram-rank');payload.options.reporting_plan=$('reporting-plan').checked;
    }
    c.iid=$('iid').checked;c.confidence_level=M.number(fieldValue('confidence'));
    document.querySelectorAll('#targets .target-row').forEach((row,i)=>row.querySelectorAll('[data-target]').forEach(field=>{
      const key=field.dataset.target;M.setThresholdField(M.targets(payload)[i],key==='decision_percentage'?'decision_fraction':key,key==='threshold'?M.number(field.value):key==='decision_percentage'?M.percentToFraction(field.value):field.value);
    }));
    if(payload.mode!=='reporting-audit')document.querySelectorAll('#counts .count-row').forEach((row,i)=>row.querySelectorAll('[data-count]').forEach(field=>{
      const key=field.dataset.count;M.setCountField(payload.config.additional_counts[i],key,['source','relation','source_scale','rounding_rule','percentage','start_category','end_category'].includes(key)?field.value:key==='threshold'?M.number(field.value):M.integer(field.value));
    }));
    return payload;
  }
  function showStep(index) {
    collect();step=index;notice('');
    document.querySelectorAll('[data-panel]').forEach(el=>el.hidden=Number(el.dataset.panel)!==step);
    document.querySelectorAll('#steps button').forEach((el,i)=>{if(i===step)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current');});
    $('back').disabled=step===0;$('continue').hidden=step===4;$('step-count').textContent='Step '+(step+1)+' of 5';$('continue').textContent=['Next: test concentrations','Next: your results','Next: your report','Next: check and run','Continue'][step];
    if(step===2){renderQuantiles();renderHistogram();}
    if(step===4)renderReview();
    document.querySelector('[data-panel="'+step+'"] h2').setAttribute('tabindex','-1');
    document.querySelector('[data-panel="'+step+'"] h2').focus({preventScroll:true});
    $('workspace').scrollIntoView({behavior:'auto',block:'start'});
  }
  function openPayload(value) {
    if(running)throw new Error('Finish or cancel the current calculation before opening another analysis.');
    payload=M.importInput(value);payload.options||={};payload.targets||=[];payload.histogram||=[];
    if(!['distribution','reporting-audit','batch','verify-report'].includes(payload.mode))throw new Error('Choose distribution, threshold analysis, reporting audit or received-report verification.');
    step=0;levelsDirty=false;notice('');$('validation').replaceChildren();$('job').hidden=true;
    $('analysis-form').hidden=false;$('report-frame').hidden=true;$('result-actions').hidden=true;
    $('welcome').hidden=true;$('workspace').hidden=false;
    const documentMode=isDocument();$('document-editor').hidden=!documentMode;$('steps').hidden=documentMode;document.querySelector('.step-actions').hidden=documentMode;$('previous-editor').hidden=documentMode;
    $('run').textContent=payload.mode==='verify-report'?'Verify and create report':'Calculate and create report';
    if(documentMode){renderDocument();document.querySelectorAll('[data-panel]').forEach(el=>el.hidden=el.dataset.panel!=='4');renderReview();}
    else{renderAll();showStep(0);}
  }
  function renderAll() {
    const c=payload.config,audit=payload.mode==='reporting-audit';
    $('mode-label').textContent=audit?'Laboratory counts':payload.mode==='batch'?'Requests for additional counts':'Results from a publication';
    $('workspace-title').textContent=audit?'Prepare a useful laboratory report':'Understand the MIC results you have';
    $('sample-example-heading').textContent=audit?'Example from a laboratory record':'Example from a publication';
    $('sample-example-body').textContent=audit?'If the MIC categories contain 8, 10 and 2 isolates, enter 20 as the sample size. You will enter those three counts in step 3.':'If a row says “E. coli, ampicillin, n = 67”, enter 67 below. Do not enter the total for the whole paper if this row uses a smaller group.';
    for(const [id,key] of [['cohort','cohort_id'],['n','n'],['unit','unit'],['organism','organism'],['antimicrobial','antimicrobial'],['source','source'],['panel-id','panel_id']])setValue(id,c[key]);
    for(const [id,key] of [['host-species','host_species'],['specimen','specimen'],['grouping-notes','grouping_notes'],['intended-population','intended_population']])setValue(id,c.sample_context?.[key]);
    setValue('repeat-sampling',c.sample_context?.repeat_sampling||'unknown');
    $('sample-context').open=Boolean(c.sample_context&&Object.entries(c.sample_context).some(([key,value])=>value&&!(key==='repeat_sampling'&&value==='unknown')));
    setValue('panel-kind',c.panel?.categories?'categories':'levels');setValue('levels',c.panel?.levels?.join(', '));
    $('left-censored').checked=c.panel?.left_censored!==false;$('right-censored').checked=c.panel?.right_censored!==false;
    renderPanel();renderQuantiles();renderCounts();renderVariants();renderHistogram();renderTargets();
    $('summary-editor').hidden=audit;$('histogram-editor').hidden=!audit;
    $('information-lead').textContent=audit?'Copy the number of isolates in each MIC category, including zero. The program will compare these counts with a shorter report.':'Copy only what the source provides. MIC50/MIC90 and other counts can be used together; counts can also be used on their own.';
    setValue('histogram-rank',payload.rank_convention);
    setValue('analysis-goal',audit?'distribution':payload.mode);$('analysis-goal-label').hidden=audit;
    $('distribution-questions').hidden=payload.mode!=='distribution';$('audit-questions').hidden=false;
    $('target-title').textContent=audit?'Compare ways of reporting the sample':'Answer questions about recorded MIC above a concentration';
    $('target-description').textContent=audit?'Choose the concentrations of interest. The audit compares summaries, one additional count, all requested counts and the complete histogram.':'Optional questions use the summaries or counts you have. Enter each criterion as a percentage from 0 to 100; for example, 5 means 5%. Counts-only distribution questions do not require MIC50 or MIC90.';
    $('count-planning').hidden=payload.mode!=='batch';$('decision-plan').checked=payload.options.decision_plan===true;$('acquisition-plan').checked=payload.options.acquisition_plan===true;
    $('sufficient-planning').hidden=!audit;$('reporting-plan').checked=payload.options.reporting_plan===true;
    $('population-count-plan').checked=payload.options.population_count_plan===true;setValue('population-minimum-bins',payload.options.population_minimum_bins);setValue('population-precision',payload.options.population_precision_pp);setValue('precision',payload.options.precision_pp);$('iid').checked=c.iid===true;
    const confidence=String(c.confidence_level??.95);
    if(![...$('confidence').options].some(x=>x.value===confidence))$('confidence').add(new Option(Number(confidence)*100+'%',confidence));
    setValue('confidence',confidence);setValue('population-method',payload.options.population_method||'bonferroni');
    setValue('time-limit',payload.options.population_time_limit??30);setValue('tolerance',payload.options.population_tolerance_pp??.01);
    $('population-method-label').hidden=payload.mode!=='distribution';renderLayers();renderReview();
    $('sample-notes').open=Boolean(c.organism||c.antimicrobial||c.source||c.panel_id);
    $('range-details').open=Boolean(c.summaries?.minimum||c.summaries?.maximum);
    $('grouping-details').open=payload.options.precision_pp!=null;
    $('question-details').open=audit||payload.mode==='batch'||M.targets(payload).length>0;
    $('question-details').querySelector('summary').textContent=audit?'Which concentration should the shorter report answer?':'Add a question about a concentration (optional)';
    $('goal-details').hidden=audit;$('goal-details').open=payload.mode==='batch';
    $('inference-details').open=c.iid===true;$('calibration-details').open=Boolean(c.wasserstein_calibration_manifest);
    $('report-purpose').textContent=audit?'Choose a concentration of interest, such as 4 mg/L. The report will show how precisely different reporting choices answer that question.':'Your first report will show the possible number and percentage of isolates in each MIC group. The options below are not required for this sample description.';
  }
  function renderPanel() {
    const explicit=fieldValue('panel-kind')==='categories';$('levels-editor').hidden=explicit;$('categories-editor').hidden=!explicit;
    const labels=M.panelLabels(payload.config.panel||{});
    $('panel-preview').innerHTML=labels.length?labels.map(x=>'<span class="tag">'+esc(x)+'</span>').join(''):'No categories entered.';
    renderCategories();
    for(const id of ['minimum','maximum'])$(id).innerHTML=categoryOptions(payload.config.summaries?.[id]);
  }
  function applyLevels() {
    const values=fieldValue('levels').split(/[,;\s]+/).filter(Boolean).map(M.number);
    if(!values.length)throw new Error('Enter the tested concentrations before applying the panel.');
    if(values.some((x,i)=>x<=0||(i>0&&x<=values[i-1])))throw new Error('Concentrations must be positive and strictly increasing.');
    payload.config.panel={levels:values,left_censored:$('left-censored').checked,right_censored:$('right-censored').checked};
    levelsDirty=false;renderPanel();renderQuantiles();renderHistogram();invalidate();
  }
  function renderCategories() {
    const categories=payload.config.panel?.categories||[];
    $('categories').innerHTML=categories.map((row,i)=>'<div class="category-row"><div class="row-heading"><h3>Category '+(i+1)+'</h3>'+removeButton('category '+(i+1),i)+'</div><div class="mini-grid">'+input('Category label',row.label,'data-key="label"')+input('Lower bound',row.lower_bound,'type="number" step="any" data-key="lower_bound"')+input('Upper bound',row.upper_bound,'type="number" step="any" data-key="upper_bound"')+input('Recorded ordering value',row.panel_value,'type="number" step="any" data-key="panel_value"')+'<label><input type="checkbox" data-key="lower_closed"'+checked(row.lower_closed)+'> Include lower bound</label><label><input type="checkbox" data-key="upper_closed"'+checked(row.upper_closed)+'> Include upper bound</label></div></div>').join('');
    [...$('categories').children].forEach((el,i)=>{
      el.querySelector('[data-remove]').onclick=()=>{categories.splice(i,1);renderPanel();renderQuantiles();renderHistogram();invalidate();};
      el.querySelectorAll('[data-key]').forEach(field=>field.onchange=guarded(()=>{categories[i][field.dataset.key]=field.type==='checkbox'?field.checked:field.dataset.key==='label'?field.value:M.number(field.value);renderPanel();renderQuantiles();renderHistogram();invalidate();}));
    });
  }
  function quantileMarkup(q,probability,prefix) {
    const name=probability===.5?'MIC50':'MIC90',rank=q?.rank!=null?'explicit':q?.convention||'';
    return '<div class="quantile-entry" data-probability="'+probability+'"><label>'+prefix+name+'<select data-q="category">'+categoryOptions(q?.category)+'</select></label><div class="fields"><label data-rule-label'+(q?.category?'':' hidden')+'>'+name+' calculation rule<select data-q="convention"><option value="">Not stated / choose only when justified</option><option value="ceiling"'+selected(rank,'ceiling')+'>First observation reaching the percentage (ceiling)</option><option value="explicit"'+selected(rank,'explicit')+'>The source gives an observation number</option></select></label><label'+(rank==='explicit'?'':' hidden')+'>'+name+' observation number in sorted results<input type="number" min="1" step="1" data-q="rank" value="'+esc(q?.rank)+'"></label></div></div>';
  }
  function bindQuantiles(container,config) {
    container.querySelectorAll('.quantile-entry').forEach(el=>el.querySelectorAll('[data-q]').forEach(field=>field.onchange=guarded(()=>{
      const probability=Number(el.dataset.probability),category=el.querySelector('[data-q="category"]').value,convention=el.querySelector('[data-q="convention"]').value;
      const value={category};if(convention==='explicit')value.rank=M.integer(el.querySelector('[data-q="rank"]').value);else if(convention)value.convention=convention;
      M.setQuantile(config,probability,category?value:null);
      el.querySelector('[data-rule-label]').hidden=!category;el.querySelector('[data-q="rank"]').parentElement.hidden=!category||convention!=='explicit';invalidate();
    })));
  }
  function collectQuantiles(container,config){
    container.querySelectorAll('.quantile-entry').forEach(el=>{
      const category=el.querySelector('[data-q="category"]').value,convention=el.querySelector('[data-q="convention"]').value,value={category};
      if(category){if(convention==='explicit')value.rank=M.integer(el.querySelector('[data-q="rank"]').value);else if(convention)value.convention=convention;}
      M.setQuantile(config,Number(el.dataset.probability),category?value:null);
    });
  }
  function renderQuantiles() {
    $('quantiles').innerHTML=[.5,.9].map(p=>quantileMarkup(payload.config.summaries?.quantiles?.find(q=>M.sameDecimal(q.probability,p)),p,'')).join('');
    bindQuantiles($('quantiles'),payload.config);
  }
  function renderVariants() {
    const variants=payload.config.reporting_envelope?.variants||[];
    $('variants').innerHTML=variants.map((v,i)=>'<div class="variant-row"><div class="row-heading"><h3>Alternative '+(i+1)+'</h3>'+removeButton('variant '+(i+1),i)+'</div>'+input('Variant identifier',v.id,'data-variant-id')+'<div class="fields">'+[.5,.9].map(p=>quantileMarkup(v.summaries?.quantiles?.find(q=>M.sameDecimal(q.probability,p)),p,'Alternative ')).join('')+'</div></div>').join('');
    [...$('variants').children].forEach((el,i)=>{
      el.querySelector('[data-remove]').onclick=()=>{variants.splice(i,1);renderVariants();invalidate();};
      el.querySelector('[data-variant-id]').onchange=e=>{variants[i].id=e.target.value;invalidate();};bindQuantiles(el,variants[i]);
    });
  }
  function countType(row) {return M.countType(row);}
  function renderCounts() {
    const rows=payload.config.additional_counts||[];
    $('counts').innerHTML=rows.map((r,i)=>{
      const type=countType(r);
      const interval='start_category' in r;
      const selector='<label>Which results are counted?<select data-scope><option value="tail"'+selected(interval?'interval':'tail','tail')+'>Above or below one concentration</option><option value="interval"'+selected(interval?'interval':'tail','interval')+'>Inside a group of adjacent MIC categories</option></select></label>';
      const range=interval?'<label>First included category<select data-count="start_category">'+categoryOptions(r.start_category)+'</select></label><label>Last included category<select data-count="end_category">'+categoryOptions(r.end_category)+'</select></label>':input('MIC concentration ('+esc(payload.config.unit||'choose unit')+')',r.threshold,'type="number" step="any" data-count="threshold"')+'<label>The source says MIC is…<select data-count="relation">'+[['>','Strictly above (>)'],['>=','At or above (≥)'],['<','Strictly below (<)'],['<=','At or below (≤)']].map(([v,label])=>'<option value="'+esc(v)+'"'+selected(r.relation||'>',v)+'>'+esc(label)+'</option>').join('')+'</select></label>';
      const scale=interval?'':'<label>Meaning of this count<select data-count="source_scale">'+(!r.source_scale?'<option value="">As saved (unchanged interpretation)</option>':'')+[['recorded','Recorded MIC categories'],['interval','MIC within the measurement intervals']].map(([v,label])=>'<option value="'+esc(v)+'"'+selected(r.source_scale||'',v)+'>'+label+'</option>').join('')+'</select></label>';
      return '<div class="count-row"><div class="row-heading"><h3>Count '+(i+1)+'</h3>'+removeButton('count '+(i+1),i)+'</div>'+selector+scale+'<div class="mini-grid">'+range+input('Isolates in the source count',r.n,'type="number" step="1" min="1" data-count="n"')+'</div><label class="compact">Information available<select data-kind><option value="exact"'+selected(type,'exact')+'>Exact number of isolates</option><option value="range"'+selected(type,'range')+'>Range of counts</option><option value="percentage"'+selected(type,'percentage')+'>Rounded percentage</option></select></label><div class="fields">'+(type==='exact'?input('Exact number of isolates',r.count,'type="number" step="1" min="0" data-count="count"'):type==='range'?input('Lowest possible count',r.count_min,'type="number" step="1" min="0" data-count="count_min"')+input('Highest possible count',r.count_max,'type="number" step="1" min="0" data-count="count_max"'):input('Published percentage (0–100)',r.percentage,'type="text" inputmode="decimal" data-count="percentage"')+input('Decimal places in the publication',r.decimal_places,'type="number" step="1" min="0" data-count="decimal_places"')+'<label>Rounding rule<select data-count="rounding_rule"><option value="">Choose explicitly</option>'+['half_up','half_even','floor','ceiling'].map(x=>'<option value="'+x+'"'+selected(x,r.rounding_rule)+'>'+({half_up:'Round half up',half_even:'Round half to even',floor:'Round down',ceiling:'Round up'}[x])+'</option>').join('')+'</select></label>')+input('Source of this count',r.source,'data-count="source"')+'</div><p class="note" data-count-preview aria-live="polite">'+esc(M.countPreview(r,payload.config.panel))+'</p><details><summary>Convert a suppressed number of isolates</summary><p>This concerns how many isolates were reported, not a censored MIC concentration.</p><select data-count-relation><option value="&lt;">Less than</option><option value=">=">At least</option></select><input data-count-limit type="number" min="0" step="1" aria-label="Reported count limit"><button type="button" data-convert-count>Use count range</button></details></div>';
    }).join('');
    [...$('counts').children].forEach((el,i)=>{
      el.querySelector('[data-remove]').onclick=()=>{rows.splice(i,1);renderCounts();invalidate();};
      el.querySelector('[data-convert-count]').onclick=guarded(()=>{collect();M.setSuppressedCount(rows[i],el.querySelector('[data-count-relation]').value,el.querySelector('[data-count-limit]').value);renderCounts();invalidate();});
      el.querySelector('[data-scope]').onchange=guarded(e=>{
        collect();const row=rows[i];
        for(const key of ['threshold','relation','start_category','end_category','source_relation','source_threshold','source_information'])delete row[key];
        if(e.target.value==='interval'){row.start_category='';row.end_category='';row.source_scale='recorded';}else{row.threshold=null;row.relation='>';}
        renderCounts();invalidate();
      });
      el.querySelector('[data-kind]').onchange=guarded(e=>{
        // Preserve in-progress field edits before rebuilding this count's controls.
        for(const key of ['threshold','n','source','relation','source_scale','start_category','end_category']){const field=el.querySelector('[data-count="'+key+'"]');if(!field)continue;M.setCountField(rows[i],key,key==='threshold'?M.number(field.value):key==='n'?M.integer(field.value):field.value);}
        const row=rows[i];for(const key of ['count','count_min','count_max','percentage','decimal_places','rounding_rule'])delete row[key];
        if(e.target.value==='exact')row.count=null;else if(e.target.value==='range'){row.count_min=null;row.count_max=null;}else{row.percentage='';row.decimal_places=null;row.rounding_rule='';}
        renderCounts();invalidate();
      });
      el.querySelectorAll('[data-count]').forEach(field=>field.onchange=guarded(()=>{
        if(!field.isConnected)return;
        const key=field.dataset.count,kind=countType(rows[i]);
        if((key==='count'&&kind!=='exact')||(['count_min','count_max'].includes(key)&&kind!=='range')||(['percentage','decimal_places','rounding_rule'].includes(key)&&kind!=='percentage'))return;
        if(['threshold','relation'].includes(key)&&'start_category' in rows[i])return;
        const value=['source','relation','source_scale','rounding_rule','percentage','start_category','end_category'].includes(key)?field.value:key==='threshold'?M.number(field.value):M.integer(field.value);
        M.setCountField(rows[i],key,value,true);el.querySelector('[data-count-preview]').textContent=M.countPreview(rows[i],payload.config.panel);invalidate();
      }));
    });
  }
  function renderHistogram() {
    if(payload.mode!=='reporting-audit'){$('histogram').replaceChildren();return;}
    const labels=M.panelLabels(payload.config.panel||{});
    const counts=new Map(payload.histogram.map(row=>[row.category,row.count]));
    payload.histogram=labels.map(category=>({category,count:counts.has(category)?counts.get(category):null}));
    $('histogram').innerHTML=payload.histogram.map((r,i)=>'<div class="histogram-row"><label for="hist-'+i+'">'+esc(r.category)+'</label><input id="hist-'+i+'" type="number" min="0" step="1" value="'+esc(r.count)+'" aria-label="Count in '+esc(r.category)+'"></div>').join('');
    $('histogram').querySelectorAll('input').forEach((el,i)=>el.oninput=guarded(()=>{payload.histogram[i].count=M.integer(el.value);renderHistogramTotal();invalidate();}));
    renderHistogramTotal();
  }
  function renderHistogramTotal(){
    const rows=payload.histogram||[],filled=rows.filter(r=>r.count!=null&&String(r.count)!=='');
    const total=filled.reduce((sum,r)=>sum+BigInt(M.integer(r.count)),0n);
    $('histogram-total').textContent='Entered '+total+' of '+(payload.config.n??'?')+' isolates. '+filled.length+' of '+rows.length+' categories filled. '+(filled.length<rows.length?'Enter 0 for a category with no isolates.':String(total)===String(payload.config.n)?'The counts match the sample size.':'Check the counts or the sample size in step 1.');
  }
  function nextStep(){
    collect();const issues=M.stepIssues(payload,step);
    if(issues.length){notice(issues.map(x=>x.message).join(' '));const el=$(issues[0].id);if(el){for(let parent=el.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;const focus=el.matches('input,select,textarea,button')?el:el.querySelector('input,select,textarea,button');if(focus)focus.focus();}$('notice').scrollIntoView({block:'center'});return;}
    showStep(Math.min(4,step+1));
  }
  function renderTargets() {
    const rows=M.targets(payload);
    $('targets').innerHTML=rows.map((r,i)=>{
      const interval='start_category' in r||'end_category' in r;
      const kind=interval?'category_range':'threshold';
      const selector=payload.mode==='distribution'?'<label>Which MIC results does this question concern?<select data-question-kind><option value="threshold"'+selected(kind,'threshold')+'>Above one concentration</option><option value="category_range"'+selected(kind,'category_range')+'>One or more adjacent MIC categories</option></select></label>':'';
      const range=interval?'<label>First included category<select data-target="start_category">'+categoryOptions(r.start_category)+'</select></label><label>Last included category<select data-target="end_category">'+categoryOptions(r.end_category)+'</select></label>':input('Question concentration',r.threshold,'type="number" step="any" data-target="threshold"');
      const scale=payload.mode==='distribution'&&!interval?'<label>What does MIC mean in this question?<select data-target="target_scale"><option value="recorded"'+selected(r.target_scale||'recorded','recorded')+'>Recorded MIC categories</option><option value="interval"'+selected(r.target_scale,'interval')+'>MIC within the measurement intervals</option></select></label><p class="note">For example, a result recorded as &gt;32 does not tell us whether MIC exceeds 64. Choose measurement intervals to retain this uncertainty.</p>':'';
      const explanation=interval?'<p class="note">Both endpoint categories are included. Select the same category twice to ask about that category alone. A censored category remains whole; the result does not locate individual MICs within it.</p>':'<details class="block"><summary>Threshold meaning and source (optional)</summary><p>The selected MIC meaning applies to this numeric question. Choosing a kind does not assign clinical resistance.</p><div class="fields"><label>Threshold kind<select data-target="threshold_kind">'+[['custom','Custom concentration'],['ecoff','ECOFF'],['clinical','Clinical breakpoint']].map(([value,label])=>'<option value="'+value+'"'+selected(r.threshold_kind||'custom',value)+'>'+label+'</option>').join('')+'</select></label>'+input('Threshold source / standard',r.threshold_source,'data-target="threshold_source"')+input('Version / year',r.threshold_version,'data-target="threshold_version"')+input('Applicability: organism, host, site, method and rule',r.threshold_applicability,'data-target="threshold_applicability"')+'</div><p class="note">An ECOFF concerns wild-type distributions. Clinical interpretation needs an applicable breakpoint and its rule. Missing source details leave neutral MIC wording; descriptive analysis can continue.</p></details>';
      return '<div class="target-row"><div class="row-heading"><h3>Question '+(i+1)+'</h3>'+removeButton('question '+(i+1),i)+'</div>'+selector+'<div class="mini-grid">'+range+'<label>Optional criterion<select data-target="decision_operator"><option value="">No decision criterion</option>'+['<','<=','>','>='].map(x=>'<option value="'+esc(x)+'"'+selected(x,r.decision_operator)+'>'+esc(x)+'</option>').join('')+'</select></label>'+input('Criterion percentage (0–100)',M.fractionToPercent(r.decision_fraction),'type="text" inputmode="decimal" placeholder="e.g. 5 for 5%" data-target="decision_percentage"')+'</div>'+scale+explanation+'</div>';
    }).join('');
    [...$('targets').children].forEach((el,i)=>{
      el.querySelector('[data-remove]').onclick=()=>{rows.splice(i,1);renderTargets();invalidate();};
      const kind=el.querySelector('[data-question-kind]');
      if(kind)kind.onchange=guarded(()=>{collect();M.setTargetKind(rows[i],kind.value);renderTargets();invalidate();});
      el.querySelectorAll('[data-target]').forEach(field=>field.onchange=guarded(()=>{const key=field.dataset.target;M.setThresholdField(rows[i],key==='decision_percentage'?'decision_fraction':key,key==='threshold'?M.number(field.value):key==='decision_percentage'?M.percentToFraction(field.value):field.value,true);invalidate();}));
    });
  }
  function renderLayers() {
    $('population-options').hidden=!$('iid').checked;
    $('joint-options').hidden=payload.mode!=='distribution'||!['joint-exact','range-calibrated','range-hunter'].includes(fieldValue('population-method'));
    const c=payload.config,ready=c.reference_distribution&&c.wasserstein_calibration_manifest;
    $('calibration-status').textContent=ready?'Prepared calibration fields are present. Their reference, contract, target scope and sample binding will be checked; presence alone does not establish a guarantee.':'A compatible prepared reference and calibration manifest are required. Without them this layer is reported as unavailable.';
  }
  function renderReview() {
    if(isDocument()){
      $('review').innerHTML=payload.mode==='verify-report'?'<div><strong>Check scope</strong>Declared questions and disclosed counts. No original histogram required.</div>':'<div><strong>Input</strong>Text tables for '+esc(payload.mode)+'. Check input previews the structure before calculation.</div>';
      $('raw-preview').textContent=JSON.stringify(payload,null,2);$('advanced').value=JSON.stringify(payload,null,2);$('previous-note').hidden=true;return;
    }
    const c=payload.config,labels=M.panelLabels(c.panel||{}),q=c.summaries?.quantiles||[];
    const rows=[['Sample',c.cohort_id||'Not supplied'],['Number of isolates',c.n==null?'Not supplied':c.n+' isolates'],['MIC unit',c.unit||'Not supplied'],['Categories',labels.length?labels.join(' · '):'Not supplied'],['Primary summaries',q.length?q.map(x=>'MIC'+Number(x.probability)*100+': '+x.category+' ('+(x.rank!=null?'rank '+x.rank:x.convention||'rank not supplied')+')').join('; '):'No quantile summaries supplied'],['Available counts',payload.mode==='reporting-audit'?payload.histogram.length+' complete category rows':(c.additional_counts||[]).length+' additional rows'],['Sampling context',[c.sample_context?.host_species,c.sample_context?.specimen,'Repeated isolates: '+(c.sample_context?.repeat_sampling||'unknown'),c.sample_context?.grouping_notes].filter(Boolean).join(' · ')],['Intended population (user interpretation)',c.sample_context?.intended_population||'Not supplied'],['Population inference',c.iid?'Explicit iid assumption; independence and representativeness are not verified':'Not requested; sample description only'],['Calibration',c.wasserstein_calibration_manifest?'Imported contract; compatibility will be checked':'Unavailable without prepared calibration']];
    $('review').innerHTML=rows.map(([a,b])=>'<div><strong>'+esc(a)+'</strong>'+esc(b)+'</div>').join('');
    $('raw-preview').textContent=JSON.stringify(payload,null,2);$('advanced').value=JSON.stringify(payload,null,2);
    $('previous-note').hidden=!payload.previous;$('previous-note').textContent=payload.previous?'A previous configuration and result are attached. An update must retain the original sample and constraints.':'';
  }
  function tablePreview(name) {
    const target=$('preview-'+name),text=fieldValue('table-'+name);
    if(!text.trim()){target.textContent='No table supplied.';return;}
    try{
      const p=M.previewTable(text,fieldValue('delimiter-'+name));
      target.innerHTML='<p>'+p.rows+' data rows · '+p.columns.length+' columns'+(p.cohorts.length?' · '+p.cohorts.length+' samples':'')+'</p><div class="table-scroll" tabindex="0" role="region" aria-label="'+esc(name)+' table preview"><table><thead><tr>'+p.columns.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+p.sample.map(r=>'<tr>'+r.map(x=>'<td>'+esc(x)+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>'+(p.cohorts.length?'<p>Sample identifiers: '+p.cohorts.slice(0,20).map(esc).join(', ')+(p.cohorts.length>20?' …':'')+'</p>':'');
    }catch(e){target.textContent=e.message;}
  }
  function renderDocument() {
    const verify=payload.mode==='verify-report';$('tables-editor').hidden=verify;$('certificate-editor').hidden=!verify;
    $('mode-label').textContent=verify?'Received report · logical verification':'CSV and spreadsheet tables';
    if(verify){setValue('certificate-text',payload.certificate_json|| (payload.certificate?JSON.stringify(payload.certificate,null,2):''));certificatePreview();return;}
    setValue('table-mode',payload.mode);payload.tables||={};
    const labels={input:'Sample information or category counts',panels:'MIC categories and panels',targets:'Questions',additional_counts:'Additional counts'};
    const help={input:'Use the columns for the analysis selected above. One sample identifier must not describe different original samples.',panels:'Columns: panel_id, unit, category, lower, upper, lower_closed, upper_closed, panel_value. Include all categories; blank endpoints mean unbounded ends.',targets:'Columns: cohort_id, unit and threshold. In distribution mode, start_category and end_category may replace threshold; both endpoint categories are included. Optional target_scale: recorded (default) or interval, in distribution mode. Optional paired columns: decision_operator and decision_fraction. This existing CSV field uses fractions: 0.05 means 5%. It is preserved exactly on import.',additional_counts:'Columns: cohort_id, threshold, unit, n, source; plus count, or count_min and count_max, or percentage, decimal_places and rounding_rule. Optional relation: >, >=, < or <=. Optional source_scale: recorded or interval; a blank preserves saved interpretation. Percentage uses 0–100.'};
    $('tables').innerHTML=Object.entries(labels).map(([name,label])=>'<details class="table-entry"'+(['input','panels'].includes(name)?' open':'')+'><summary>'+label+(name==='additional_counts'?' · optional':'')+'</summary><div class="fields"><label class="file-button secondary">Choose '+label.toLowerCase()+' file<input data-table-file="'+name+'" type="file" accept=".csv,.tsv,.txt,text/csv,text/tab-separated-values,text/plain"></label><label>Separator for '+label.toLowerCase()+'<select id="delimiter-'+name+'"><option value="">Choose separator</option><option value="comma">Comma (CSV)</option><option value="semicolon">Semicolon</option><option value="tab">Tab (copied spreadsheet cells)</option></select></label></div><label for="table-'+name+'">Paste '+label.toLowerCase()+' including headers</label><textarea id="table-'+name+'" rows="5" spellcheck="false"></textarea><div id="preview-'+name+'" class="table-preview note" aria-live="polite"></div></details>').join('');
    for(const name of Object.keys(labels)){
      setValue('table-'+name,payload.tables[name]?.text);setValue('delimiter-'+name,payload.tables[name]?.delimiter);
      const hint=document.createElement('p');hint.className='note';hint.textContent=help[name];$('table-'+name).before(hint);
      $('table-'+name).oninput=()=>{tablePreview(name);invalidate();};$('delimiter-'+name).onchange=()=>{tablePreview(name);invalidate();};
      document.querySelector('[data-table-file="'+name+'"]').onchange=guarded(async e=>{const file=e.target.files[0];if(!file)return;if(!/\.(csv|tsv|txt)$/i.test(file.name))throw new Error('Choose a text CSV/TSV file, or paste spreadsheet cells. Workbook files are not supported.');setValue('table-'+name,await file.text());tablePreview(name);invalidate();});tablePreview(name);
    }
    $('table-reporting-plan').checked=payload.options.reporting_plan===true;tableModeHelp();
  }
  function tableModeHelp(){
    const mode=fieldValue('table-mode');$('table-reporting-label').hidden=mode!=='reporting-audit';
    $('table-schema').textContent=mode==='reporting-audit'?'Category-count input: cohort_id, panel_id, category, count, rank_convention. Include every category, including zeros. Questions are required.':mode==='batch'?'Summary input: cohort_id, panel_id, variant_id, n, mic50, mic90, rank_convention (plus explicit ranks if used). Questions are required.':'Distribution input: cohort_id, panel_id, variant_id, n; optional mic50, mic90 and rank_convention. Use variant_id=primary. Counts-only inputs may leave summaries blank. Questions are optional.';
  }
  function certificatePreview(){
    const text=fieldValue('certificate-text');if(!text.trim()){$('certificate-preview').textContent='No certificate supplied.';return;}
    try{const p=M.certificateInput(text);$('certificate-preview').textContent=p.certificate.certificates.length+' certificate(s): '+p.certificate.certificates.map(r=>r.cohort_id||'unnamed sample').join(', ')+'. The original JSON text is retained for exact verification.';}catch(e){$('certificate-preview').textContent=e.message;}
  }
  function showValidation(data) {
    const items=data.issues||[];
    $('validation').innerHTML=data.valid?'<p class="validation-success">The input is ready for calculation.</p>':'<div class="validation-errors"><strong>Please correct the following information.</strong><ul>'+items.map(x=>'<li><strong>'+esc(x.field||'Input')+':</strong> '+esc(x.message||x)+'</li>').join('')+'</ul></div>';
    if(data.warnings?.length){const ul=document.createElement('ul');ul.className='note';for(const warning of data.warnings){const li=document.createElement('li');li.textContent=warning.message||String(warning);ul.append(li);}$('validation').append(ul);}
    if(data.preview&&Object.keys(data.preview).length){const p=document.createElement('p');p.className='note';p.textContent='Checked table structure: '+Object.entries(data.preview).map(([name,v])=>name+': '+v.rows+' rows, '+v.columns.length+' columns').join('; ')+'. Numerical compatibility is checked during calculation.';$('validation').append(p);}
  }
  async function validate() {collect();renderReview();const data=await api('/api/validate',payload);showValidation(data);return data.valid;}
  async function run() {
    if(running)return;
    $('run').disabled=true;
    try {if(!await validate())return;const job=await api('/api/jobs',payload);jobId=job.job_id;running=true;$('job').hidden=false;$('job-files').replaceChildren();$('cancel').hidden=false;$('job-progress').hidden=false;$('job-title').textContent='Calculating';await poll();}
    finally {$('run').disabled=running;}
  }
  async function poll() {
    try {
      const job=await api('/api/jobs/'+encodeURIComponent(jobId));
      $('job-status').textContent=job.message||job.status;
      if(['running','queued','pending'].includes(job.status)){setTimeout(poll,800);return;}
      running=false;$('run').disabled=false;$('cancel').hidden=true;$('job-progress').hidden=true;
      $('job-title').textContent=job.status==='completed'?'Your report is ready':job.status==='cancelled'?'Calculation cancelled':job.status==='refused'?'Report ready · review refused results':'Calculation did not finish';
      $('job-directory').textContent=job.output_directory?'Saved on this computer: '+job.output_directory:'';
      const files=job.files||[];
      for(const f of files){const a=document.createElement('a');a.href=linkWithToken(f.url);a.textContent=f.name==='report.html'?'Save report':f.name;a.className=f.name==='report.html'?'primary':'secondary';a.download=f.name;if(f.name.endsWith('.html'))a.onclick=guarded(async event=>{event.preventDefault();await downloadReport(a.href,f.name);});$('job-files').append(a);}
      if(['completed','refused'].includes(job.status)&&files.length){const a=document.createElement('a');a.href=linkWithToken('/api/jobs/'+encodeURIComponent(jobId)+'/archive');a.textContent='Download all results';a.className='secondary';a.download='MIC-50-90-results.zip';$('job-files').append(a);}
      const report=files.find(file=>file.name==='report.html');
      if(report&&['completed','refused'].includes(job.status)){
        completedFiles=files;completedPayload=M.clone(payload);$('analysis-form').hidden=true;$('result-actions').hidden=false;
        $('add-result-count').hidden=payload.mode!=='distribution'||payload.input_format==='tables'||job.status!=='completed';
        const frame=$('report-frame');frame.hidden=false;frame.onload=()=>{
          const doc=frame.contentDocument;if(!doc)return;reportObserver?.disconnect();
          const resize=()=>{frame.style.height=Math.max(620,doc.body.scrollHeight+40)+'px';};
          window.MIC50Report.bind(doc,resize);reportObserver=new ResizeObserver(resize);reportObserver.observe(doc.body);
        };frame.src=linkWithToken(report.url);$('job-status').textContent=job.status==='completed'?'Read the answer below. The full report uses the same numbers.':job.message;
        $('job-title').focus();$('job').scrollIntoView({block:'start'});
      }
    } catch(e){running=false;$('run').disabled=false;$('job-progress').hidden=true;$('job-status').textContent='Connection lost. The calculation status could not be confirmed. '+e.message;}
  }
  $('edit-result').onclick=guarded(()=>{$('analysis-form').hidden=false;$('result-actions').hidden=true;$('report-frame').hidden=true;showStep(4);});
  $('print-result').onclick=guarded(()=>{const doc=$('report-frame').contentDocument;if(doc)window.MIC50Report.printReport(doc);});
  $('add-result-count').onclick=guarded(async()=>{
    const file=name=>{const found=completedFiles.find(item=>item.name===name);if(!found)throw new Error('This result does not contain the saved inputs required for a same-sample update.');return found;};
    const texts=await Promise.all(['configuration.json','results.json'].map(async name=>{const response=await fetch(linkWithToken(file(name).url));if(!response.ok)throw new Error('The saved analysis could not be read.');return response.text();}));
    const configuration=M.parseJSON(texts[0]),results=M.parseJSON(texts[1]);
    const restored=M.importText(texts[0]);restored.previous={configuration,results};restored.previous_configuration_text=texts[0];
    restored.options={...completedPayload.options,...restored.options};openPayload(restored);showStep(2);$('add-count').click();
    notice('The original input is restored. Append one truthful count from these same isolates. Earlier information and inference settings must stay fixed.');
    $('counts').lastElementChild?.scrollIntoView({block:'center'});
  });
  function downloadInput() {collect();const blob=new Blob([JSON.stringify(M.save(payload),null,2)+'\n'],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=(payload.config.cohort_id||'MIC-50-90').replace(/[^a-zA-Z0-9._-]/g,'_')+'-input.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  $('start-summary').setAttribute('aria-label','I have results from a publication');$('start-histogram').setAttribute('aria-label','I have laboratory category counts');$('open-input').setAttribute('aria-label','Open a saved analysis');
  $('start-summary').onclick=guarded(()=>{const fresh=M.blank();fresh.config.cohort_id='My sample';openPayload(fresh);});
  $('start-tables').onclick=guarded(()=>openPayload({...M.blank(),input_format:'tables',tables:{},options:{}}));
  $('start-verify').onclick=guarded(()=>openPayload({...M.blank(),mode:'verify-report'}));
  $('table-mode').onchange=()=>{collect();tableModeHelp();invalidate();};
  $('certificate-text').oninput=()=>{certificatePreview();invalidate();};
  $('certificate-file').onchange=guarded(async()=>{const file=$('certificate-file').files[0];if(file){setValue('certificate-text',await file.text());certificatePreview();invalidate();}});
  $('start-histogram').onclick=guarded(()=>{const fresh=M.blank();fresh.mode='reporting-audit';fresh.config.cohort_id='My sample';openPayload(fresh);});
  for(const [id,exampleId] of [['example-publication','published7133'],['example-laboratory','laboratory276']])$(id).onclick=guarded(()=>{const example=session?.examples.find(x=>x.id===exampleId);if(!example)throw new Error('Wait for the local session to be ready, then try the example.');openPayload(example.payload);notice('Filled-in example loaded. These are example values. Use New analysis to enter your own sample.');});
  $('open-input').onclick=()=>$('input-file').click();
  $('input-file').onchange=guarded(async()=>{if($('input-file').files[0])openPayload(M.importText(await $('input-file').files[0].text()));$('input-file').value='';});
  $('new-input').onclick=guarded(()=>{if(running)throw new Error('Finish or cancel the calculation before starting another analysis.');if(confirm('Start a new analysis? Save the editable input first if you need to keep it.')){$('welcome').hidden=false;$('workspace').hidden=true;}});
  $('save-input').onclick=guarded(downloadInput);
  $('load-example').onclick=guarded(()=>{const example=session?.examples.find(x=>x.id===fieldValue('example'));if(!example)throw new Error('Choose an example first.');openPayload(example.payload);});
  $('analysis-form').onsubmit=e=>e.preventDefault();
  $('analysis-form').addEventListener('input',()=>notice(''));
  $('analysis-form').addEventListener('change',()=>notice(''));
  $('analysis-form').addEventListener('change',()=>{$('validation').replaceChildren();if(!running&&!$('job').hidden)$('job-title').textContent='Previous report · the input has changed';});
  document.querySelectorAll('#steps button').forEach(button=>button.onclick=guarded(()=>showStep(Number(button.dataset.step))));
  $('back').onclick=guarded(()=>showStep(Math.max(0,step-1)));$('continue').onclick=guarded(nextStep);
  $('levels').oninput=()=>{levelsDirty=true;};$('left-censored').onchange=()=>{levelsDirty=true;};$('right-censored').onchange=()=>{levelsDirty=true;};
  $('apply-levels').onclick=guarded(applyLevels);
  $('panel-kind').onchange=()=>{renderPanel();invalidate();};
  $('add-category').onclick=guarded(()=>{if(!payload.config.panel.categories)payload.config.panel={categories:[]};payload.config.panel.categories.push({label:'',lower_bound:null,upper_bound:null,lower_closed:false,upper_closed:false,panel_value:null});renderPanel();invalidate();});
  $('add-count').onclick=guarded(()=>{collect();payload.config.additional_counts||=[];payload.config.additional_counts.push(M.newCount(payload.config.n,payload.config.unit));renderCounts();invalidate();});
  $('add-variant').onclick=()=>{payload.config.reporting_envelope||={};payload.config.reporting_envelope.variants||=[];const rows=payload.config.reporting_envelope.variants;rows.push({id:'alternative-'+(rows.length+1),summaries:M.clone(payload.config.summaries||{quantiles:[]})});renderVariants();invalidate();};
  $('add-target').onclick=guarded(()=>{collect();M.targets(payload,true).push({threshold:null,unit:payload.config.unit});renderTargets();invalidate();});
  $('iid').onchange=renderLayers;$('population-method').onchange=renderLayers;
  $('decision-plan').onchange=()=>{if($('decision-plan').checked)$('acquisition-plan').checked=false;};
  $('acquisition-plan').onchange=()=>{if($('acquisition-plan').checked)$('decision-plan').checked=false;};
  $('analysis-goal').onchange=guarded(()=>{collect();const questions=M.clone(M.targets(payload));const nextMode=fieldValue('analysis-goal');if(nextMode!=='distribution'&&questions.some(r=>'start_category' in r||'end_category' in r||r.target_scale==='interval')){$('analysis-goal').value=payload.mode;throw new Error('Questions about a group of MIC categories or measurement intervals use the distribution view. Keep this view or remove those questions before selecting threshold-only planning.');}payload.mode=nextMode;if(payload.mode==='distribution')payload.config.targets=questions;else payload.targets=questions;renderAll();showStep(3);invalidate();});
  $('apply-advanced').onclick=guarded(()=>{openPayload(M.importText(fieldValue('advanced')));showStep(4);notice('Advanced input applied. Review the fields and check the input before calculation.');});
  $('calibration-file').onchange=guarded(async()=>{
    if(!$('calibration-file').files[0])return;const text=await $('calibration-file').files[0].text();const raw=M.parseJSON(text);const c=raw.config||raw;
    const keys=['reference_distribution','wasserstein_calibration_manifest','calibration_context'];
    if(!keys.every(key=>key in c))throw new Error('Choose a prepared analysis configuration containing reference_distribution, wasserstein_calibration_manifest and calibration_context.');
    for(const key of keys)payload.config[key]=M.clone(c[key]);payload.calibration_input_text=text;renderLayers();invalidate();$('calibration-file').value='';
  });
  $('previous-files').onchange=guarded(async()=>{
    if(payload.mode!=='distribution')throw new Error('Saved population-bound updates are available for distribution analyses.');
    const texts=await Promise.all([...$('previous-files').files].map(file=>file.text())),raw=texts.map(text=>M.parseJSON(text.replace(/^\uFEFF/,'')));
    const configurationIndex=raw.findIndex(x=>x.inputs),configuration=raw[configurationIndex],results=raw.find(x=>x.cohorts);
    if(raw.length!==2||!configuration||!results)throw new Error('Choose the matching configuration.json and results.json together.');
    const restored=M.importText(texts[configurationIndex]);restored.previous={configuration,results};restored.previous_configuration_text=texts[configurationIndex];openPayload(restored);showStep(2);notice('Previous input restored. Retain its information and append new counts from the same original sample.');$('previous-files').value='';
  });
  $('clear-previous').onclick=()=>{payload.previous=null;renderReview();invalidate();};
  $('validate').onclick=guarded(validate);$('run').onclick=guarded(run);
  $('cancel').onclick=guarded(async()=>{if(jobId){await api('/api/jobs/'+encodeURIComponent(jobId)+'/cancel',{});$('job-status').textContent='Cancellation requested. Waiting for the final status.';}});
  $('quit').onclick=guarded(async()=>{if((running||!$('workspace').hidden)&&!confirm(running?'Stop the running calculation and quit?':'Quit the local application? Save the editable input first if you need to keep it.'))return;await api('/api/shutdown',{});running=false;document.querySelector('main').innerHTML='<section class="welcome"><h1>Application closed</h1><p>You can close this browser tab. Saved inputs and reports remain on your computer.</p></section>';$('quit').disabled=true;sessionStorage.removeItem('mic-50-90-token');});
  (async()=>{try{session=await api('/api/session');$('session-status').textContent='Local session ready';for(const e of session.examples||[])$('example').add(new Option(e.label,e.id));}catch(e){$('session-status').textContent='The local session is unavailable. Open the launch link supplied by MIC-50-90. '+e.message;}})();
})();

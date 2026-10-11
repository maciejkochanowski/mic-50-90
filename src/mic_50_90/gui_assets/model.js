/* Shared, side-effect-free input operations. Scientific validation stays in Python. */
(function (root) {
  'use strict';
  const clone = value => JSON.parse(JSON.stringify(value));
  const empty = value => value == null || String(value).trim() === '';
  function blank(newInput=true) {
    return {mode:'distribution', config:{cohort_id:'', n:null, unit:'', panel:{},
      summaries:{quantiles:[]}, additional_counts:[], sample_context:{repeat_sampling:'unknown'}, iid:false, confidence_level:.95},
      options:{population_method:'bonferroni', population_time_limit:30, population_tolerance_pp:.01,
        ...(newInput?{population_precision_pp:10}:{})},
      histogram:[], targets:[], previous:null};
  }
  function importInput(raw) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) throw new Error('Choose a JSON input object or saved form.');
    if (raw.format === 'mic-50-90-guided-input') return importInput(raw.payload);
    if (raw.input_format === 'tables' || raw.mode === 'verify-report') return {...blank(false), ...clone(raw)};
    if (raw.config && raw.mode) return {...blank(false), ...clone(raw)};
    if (raw.inputs) {
      if (!Array.isArray(raw.inputs) || raw.inputs.length !== 1) throw new Error('The guided form opens one cohort at a time. Use the batch commands for multiple cohorts.');
      const result = importInput(raw.inputs[0]);
      for (const key of ['population_method','population_time_limit','population_tolerance_pp','precision_pp','population_precision_pp','population_count_plan','population_minimum_bins','population_planning_time_limit']) {
        if (key in raw) result.options[key] = clone(raw[key]);
      }
      return result;
    }
    if (!('n' in raw) || !('panel' in raw)) throw new Error('This file is not an input configuration. Open configuration.json or a saved form; results.json alone is not an editable input.');
    return {...blank(false), config:clone(raw)};
  }
  function save(payload) {
    return {format:'mic-50-90-guided-input', version:'1.0.0', payload:clone(payload)};
  }
  function setSampleContext(config, fields) {
    const old=config.sample_context||{},context={...old};
    for(const key of ['host_species','specimen','grouping_notes','intended_population']){
      if(!(key in fields))continue;
      const value=String(fields[key]??'').trim();
      if(value)context[key]=value;else delete context[key];
    }
    const repeat=fields.repeat_sampling||'unknown';
    // An untouched old input must stay valid for same-sample saved updates.
    if(repeat!=='unknown'||'repeat_sampling' in old)context.repeat_sampling=repeat;
    if(Object.keys(context).length||'sample_context' in config)config.sample_context=context;
  }
  function setThresholdField(row,key,value,edited=false) {
    if(!edited){
      if(empty(value)&&empty(row[key]))return;
      if(!(key in row)&&((key==='threshold_kind'&&value==='custom')||(key==='target_scale'&&value==='recorded')))return;
    }
    if(value==null||value==='')delete row[key];else row[key]=value;
  }
  function importText(text) {
    const ordinary=JSON.parse(text.replace(/^\uFEFF/,''));
    if(ordinary.version==='1.0.0'&&Array.isArray(ordinary.certificates))return certificateInput(text);
    const payload=importInput(parseJSON(text.replace(/^\uFEFF/,'')));
    if(!payload.calibration_input_text&&['reference_distribution','wasserstein_calibration_manifest','calibration_context'].every(key=>key in payload.config))payload.calibration_input_text=text;
    return payload;
  }
  function targets(payload,create=false) {
    const owner=payload.mode==='distribution'?payload.config:payload;
    if(create)return owner.targets ||= [];
    return owner.targets || [];
  }
  function setTargetKind(row,kind) {
    if(!['threshold','category_range'].includes(kind))throw new Error('Choose a concentration or a group of whole MIC categories.');
    for(const key of ['threshold','start_category','end_category','threshold_kind','threshold_source','threshold_version','threshold_applicability'])delete row[key];
    if(kind==='category_range'){row.start_category='';row.end_category='';}
    else row.threshold=null;
  }
  function scaleDecimal(text,places) {
    const match=String(text).trim().match(/^([+-]?)(\d*)(?:\.(\d*))?(?:e([+-]?\d+))?$/i);
    if(!match||(!match[2]&&!match[3]))throw new Error('Enter a decimal percentage from 0 to 100.');
    const exponent=Number(match[4]||0)-(match[3]||'').length+places;
    if(!Number.isSafeInteger(exponent)||Math.abs(exponent)>10000)throw new Error('Decimal exponent is outside the supported range.');
    let digits=(match[2]+(match[3]||'')).replace(/^0+/,'')||'0';
    if(digits==='0')return '0';
    const point=digits.length+exponent;
    let value=point<=0?'0.'+'0'.repeat(-point)+digits:point>=digits.length?digits+'0'.repeat(point-digits.length):digits.slice(0,point)+'.'+digits.slice(point);
    if(value.includes('.'))value=value.replace(/0+$/,'').replace(/\.$/,'');
    return (match[1]==='-'?'-':'')+value;
  }
  function scaleRatio(text,multiply) {
    const match=String(text).trim().match(/^([+-]?\d+)\s*\/\s*(\d+)$/);
    if(!match)return null;
    let a=BigInt(match[1]),b=BigInt(match[2]);if(!b)throw new Error('The denominator cannot be zero.');
    if(multiply)a*=100n;else b*=100n;
    let x=a<0n?-a:a,y=b;while(y){const r=x%y;x=y;y=r;}a/=x;b/=x;
    return b===1n?String(a):String(a)+'/'+String(b);
  }
  function fractionToPercent(text) {
    if(text==null||String(text).trim()==='')return '';
    return scaleRatio(text,true)??scaleDecimal(text,2);
  }
  function percentToFraction(text) {
    if(text==null||String(text).trim()==='')return null;
    const scaled=scaleRatio(text,false)??scaleDecimal(text,-2);
    const [a,b='1']=scaled.split('/');
    if(scaled.includes('/')){if(BigInt(a)<0n||BigInt(a)>BigInt(b))throw new Error('Enter a percentage from 0 to 100.');}
    else if(scaled.startsWith('-')||Number(scaled)>1)throw new Error('Enter a percentage from 0 to 100.');
    // Compare decimal digits too: Number alone rounds values infinitesimally above 100%.
    else if(/^1\./.test(scaled)&&/[1-9]/.test(scaled.split('.')[1]))throw new Error('Enter a percentage from 0 to 100.');
    return scaled;
  }
  function certificateInput(text) {
    const raw=JSON.parse(text.replace(/^\uFEFF/,''));
    if(raw?.version!=='1.0.0'||!Array.isArray(raw.certificates)||!raw.certificates.length)throw new Error('Choose a nonempty MIC-50-90 1.0.0 reporting_certificates.json document.');
    return {...blank(),mode:'verify-report',certificate:raw,certificate_json:text};
  }
  function newCount(n,unit) {
    return {threshold:null,relation:'>',source_scale:'recorded',count:null,n,unit,source:''};
  }
  function setCountField(row,key,value,edited=false) {
    if(!edited){
      if(empty(value)&&empty(row[key]))return;
      if(key==='relation'&&value==='>'&&!(key in row))return;
    }
    row[key]=value;
  }
  function countType(row) {
    if(!empty(row.percentage))return 'percentage';
    if(!empty(row.count_min)||!empty(row.count_max))return 'range';
    if(!empty(row.count))return 'exact';
    return 'percentage' in row?'percentage':'count_min' in row||'count_max' in row?'range':'exact';
  }
  function countPreview(row,panel={}) {
    if(row.source_scale==='interval')return 'This count concerns MIC within the measurement intervals. Check input verifies that the stated boundary separates whole intervals; a crossing interval is identified explicitly.';
    if(row.source_scale==='recorded'&&!('start_category' in row)){
      const relation=row.relation||'>';
      const labels=panelLabels(panel);
      const values=Array.isArray(panel.categories)?panel.categories.map(c=>Number(c.panel_value??c.upper_bound??(2*Number(c.lower_bound)))):
        [...(panel.levels||[]).map(Number),...(panel.right_censored!==false&&panel.levels?.length?[2*Number(panel.levels.at(-1))]:[])];
      const select={'>':x=>x>Number(row.threshold),'>=':x=>x>=Number(row.threshold),'<':x=>x<Number(row.threshold),'<=':x=>x<=Number(row.threshold)}[relation];
      if(row.threshold==null||!labels.length||!select||values.some(x=>!Number.isFinite(x)||x<=0))return 'This count concerns recorded MIC categories. Enter the panel and concentration to preview the included categories.';
      const included=labels.filter((_,i)=>select(values[i]));
      const count=!empty(row.count)?row.count:!empty(row.count_min)?row.count_min+' to '+row.count_max:!empty(row.percentage)?row.percentage+'% (rounding checked on validation)':'the supplied count';
      return 'Recorded MIC '+relation+' '+row.threshold+' → categories '+(included.length?included.join(', '):'none')+' → '+count+' of '+(row.n??'?')+' isolates. No category is split.';
    }
    if(row.source_information?.original_text)return row.source_information.original_text+' → '+row.count_min+' to '+row.count_max+' of '+row.n+' isolates. This is a count range, not an MIC measurement interval.';
    if('start_category' in row)return 'Count all isolates in '+(row.start_category||'the first category')+' through '+(row.end_category||'the last category')+', including both endpoints. Categories are not split.';
    const relation=row.relation||'>';
    if(relation==='>='||relation==='<')return 'The original '+relation+' relation is retained. Check input verifies an exact category boundary; an ambiguous category is refused. No same-threshold substitution is made.';
    if(relation==='<='&&row.count!=null&&row.n!=null){try{return exactCount(row.n,row.count,'<=')+' recorded MICs strictly above '+row.threshold+' (complement of '+row.count+'/'+row.n+' at or below).';}catch(e){return e.message;}}
    if(relation==='<=')return 'The calculation finds compatible integer counts, then complements them using this original denominator.';
    return 'This information already describes recorded MIC strictly above the concentration.';
  }
  function setSuppressedCount(row,relation,text) {
    if(!['<','>='].includes(relation)||!/^\d+$/.test(String(text).trim())||!/^\d+$/.test(String(row.n)))throw new Error('Enter an integer count and the original sample size. Blank is not zero.');
    const limit=BigInt(String(text).trim()),n=BigInt(row.n);
    const low=relation==='<'?0n:limit,high=relation==='<'?(limit-1n<n?limit-1n:n):n;
    if(n<1n||low>high||high<0n)throw new Error('No counts with this denominator satisfy the supplied statement.');
    for(const key of ['count','percentage','decimal_places','rounding_rule'])delete row[key];
    row.count_min=integer(String(low));row.count_max=integer(String(high));
    row.source_information={original_text:relation+String(limit)+' isolates',count_relation:relation,reported_count:String(limit)};
  }
  function previewTable(text,delimiter) {
    const separator={comma:',',semicolon:';',tab:'\t'}[delimiter];
    if(!separator)throw new Error('Choose a delimiter explicitly.');
    const rows=[];let row=[],cell='',quoted=false,closed=false;
    text=String(text).replace(/^\uFEFF/,'');
    for(let i=0;i<text.length;i++){
      const ch=text[i];
      if(quoted){if(ch==='"'){if(text[i+1]==='"'){cell+='"';i++;}else{quoted=false;closed=true;}}else cell+=ch;continue;}
      if(ch==='"'&&!cell&&!closed){quoted=true;continue;}
      if(ch===separator){row.push(cell);cell='';closed=false;continue;}
      if(ch==='\n'||ch==='\r'){if(ch==='\r'&&text[i+1]==='\n')i++;row.push(cell);if(row.some(v=>v!==''))rows.push(row);row=[];cell='';closed=false;continue;}
      if(closed)throw new Error('Unexpected text after a quoted field at row '+(rows.length+1)+'.');
      cell+=ch;
    }
    if(quoted)throw new Error('Unclosed quoted field.');
    row.push(cell);if(row.some(v=>v!==''))rows.push(row);
    const columns=rows.shift()||[];
    if(columns.length<2)throw new Error('Check the selected delimiter and header columns.');
    if(new Set(columns).size!==columns.length)throw new Error('Duplicate header columns.');
    rows.forEach((r,i)=>{if(r.length!==columns.length)throw new Error('Table row '+(i+2)+' has '+r.length+' fields; the header has '+columns.length+'.');});
    const ci=columns.indexOf('cohort_id');
    return {columns,rows:rows.length,cohorts:ci<0?[]:[...new Set(rows.map(r=>r[ci]))],sample:rows.slice(0,5)};
  }
  function setQuantile(config, probability, value) {
    config.summaries ||= {};
    const entries = config.summaries.quantiles || [];
    const old = entries.find(q => sameDecimal(q.probability,probability)) || {};
    const replacement = {...old, probability:old.probability??probability, ...value};
    delete replacement.rank;
    delete replacement.convention;
    if (value && 'rank' in value) replacement.rank = value.rank;
    if (value && 'convention' in value) replacement.convention = value.convention;
    config.summaries.quantiles = [...entries.filter(q => !sameDecimal(q.probability,probability)), ...(value ? [replacement] : [])]
      .sort((a,b) => a.probability - b.probability);
  }
  function exactCount(n, count, relation) {
    if (typeof n==='string'||typeof count==='string') {
      const denominator=BigInt(integer(n)),observed=BigInt(integer(count));
      if(denominator<1n||observed>denominator)throw new Error('Enter an integer count between zero and the sample size.');
      if(relation==='>')return observed.toString();
      if(relation==='<=')return (denominator-observed).toString();
      throw new Error('This input accepts counts strictly above or at/below the stated concentration.');
    }
    if (!Number.isSafeInteger(n) || n < 1 || !Number.isSafeInteger(count) || count < 0 || count > n)
      throw new Error('Enter an integer count between zero and the sample size.');
    if (relation === '>') return count;
    if (relation === '<=') return n-count;
    throw new Error('This input accepts counts strictly above or at/below the stated concentration.');
  }
  function panelLabels(panel) {
    if (Array.isArray(panel.categories)) return panel.categories.map(c=>c.label);
    if (!Array.isArray(panel.levels) || !panel.levels.length) return [];
    const labels=panel.levels.map(formatMic);
    if (panel.left_censored !== false) labels[0]='<='+labels[0];
    if (panel.right_censored !== false) labels.push('>'+formatMic(panel.levels.at(-1)));
    return labels;
  }
  function number(text) {
    if (text == null || String(text).trim() === '') return null;
    const value=Number(text);
    if (!Number.isFinite(value)) throw new Error('Enter a finite number.');
    if (!sameDecimal(String(text),String(value))) throw new Error('This concentration or numerical option exceeds the supported decimal precision. Supply a value representable without changing its decimal meaning.');
    return value;
  }
  function formatMic(value) {
    const [mantissa,exponentText]=Number(value).toExponential(11).split('e'),exponent=Number(exponentText);
    const trim=text=>text.includes('.')?text.replace(/0+$/,'').replace(/\.$/,''):text;
    if(exponent < -4 || exponent >= 12)return trim(mantissa)+'e'+(exponent<0?'-':'+')+String(Math.abs(exponent)).padStart(2,'0');
    return trim(Number(mantissa+'e'+exponent).toFixed(Math.max(0,11-exponent)));
  }
  function integer(text) {
    if(text==null||String(text).trim()==='')return null;
    const value=String(text).trim();
    if(!/^\d+$/.test(value))throw new Error('Enter an integer using whole-number digits. Fractional counts and ranks are not allowed.');
    if(BigInt(value)>9007199254740991n)throw new Error('The integer exceeds the supported browser input range.');
    return value;
  }
  function sameDecimal(a,b) {
    function parts(text) {
      const match=String(text).trim().match(/^([+-]?)(\d*)(?:\.(\d*))?(?:e([+-]?\d+))?$/i);
      if(!match||(!match[2]&&!match[3]))return null;
      let digits=(match[2]+(match[3]||'')).replace(/^0+/,'')||'0';
      let exponent=Number(match[4]||0)-(match[3]||'').length;
      if(digits==='0')return ['','0',0];
      while(digits.endsWith('0')){digits=digits.slice(0,-1);exponent++;}
      return [match[1]==='-'?'-':'',digits,exponent];
    }
    return JSON.stringify(parts(a))===JSON.stringify(parts(b));
  }
  function parseJSON(text) {
    // Tokenise numbers before JSON.parse; a reviver alone sees already-rounded values.
    let marker='__mic_gui_numeric_token__';while(text.includes(marker))marker+='_';
    const tokens=[],pattern=/"(?:[^"\\]|\\.)*"|-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?/g;
    const encoded=text.replace(pattern,token=>token[0]==='"'?token:JSON.stringify(marker+tokens.push(token)));
    function exactLocation(path) {
      let parts=path.slice();if(parts[0]==='payload')parts.shift();
      if(parts[0]==='previous')return false;
      if(parts[0]==='inputs'&&typeof parts[1]==='number')parts=parts.slice(2);
      if(parts[0]==='config')parts.shift();
      if(parts.length===1&&parts[0]==='n')return true;
      if(parts[0]==='additional_counts'&&parts.length===3)return ['n','count','count_min','count_max','decimal_places','percentage'].includes(parts[2]);
      if(parts[0]==='histogram'&&parts.length===3)return parts[2]==='count';
      if(parts[0]==='targets'&&parts.length===3)return parts[2]==='decision_fraction';
      if(parts[0]==='reporting_envelope'&&parts[1]==='variants')parts=parts.slice(3);
      return parts[0]==='summaries'&&parts[1]==='quantiles'&&parts.length===4&&parts[3]==='rank';
    }
    function convert(value,path=[]) {
      if(Array.isArray(value))return value.map((item,i)=>convert(item,[...path,i]));
      if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([key,item])=>[key,convert(item,[...path,key])]));
      if(typeof value!=='string'||!value.startsWith(marker))return value;
      const token=tokens[Number(value.slice(marker.length))-1];
      return exactLocation(path)?token:number(token);
    }
    return convert(JSON.parse(encoded));
  }
  // Early entry guidance only; Python still validates the full scientific contract.
  function stepIssues(payload,step) {
    const c=payload.config||{},issues=[],add=(id,message)=>issues.push({id,message});
    const present=value=>value!==null&&value!==undefined&&String(value).trim()!=='';
    if(step===0){
      if(!present(c.n)||Number(c.n)<1)add('n','Enter the number of isolates for this same organism and antimicrobial. Copy n from the table, or the total from your laboratory record.');
      if(!c.unit)add('unit','Choose the MIC unit printed beside the concentrations: mg/L or µg/mL.');
    }
    if(step===1&&!panelLabels(c.panel||{}).length)add('levels','Enter the full tested concentration list from the Methods, supplement or laboratory test panel. MIC50 and MIC90 alone do not supply this list.');
    if(step===2){
      if(payload.mode==='reporting-audit'){
        const rows=payload.histogram||[];
        if(!rows.length||rows.some(r=>!present(r.count)))add('histogram','Enter a count for every MIC category, including zeros. An empty cell does not mean zero.');
        else {
          const sum=rows.reduce((total,r)=>total+BigInt(integer(r.count)),0n);
          if(present(c.n)&&sum!==BigInt(integer(c.n)))add('histogram','These counts total '+sum+' isolates, but the sample size is '+c.n+'. Check for a missing or duplicated category.');
        }
        if(!payload.rank_convention)add('histogram-rank','Choose how the software should calculate MIC50/MIC90 for this reporting comparison. The explanation is beside the selection.');
      }else{
        const summaries=c.summaries||{},quantiles=summaries.quantiles||[];
        for(const q of quantiles){
          if(q.category&&!q.convention&&!present(q.rank))add('quantiles','MIC'+Number(q.probability)*100+': select how this summary was calculated. If the source does not say, read the help before choosing an analysis assumption; do not guess.');
        }
        if(!quantiles.length&&!(c.additional_counts||[]).length&&!summaries.minimum&&!summaries.maximum&&!(c.reporting_envelope?.variants?.length))add('quantiles','Enter at least one result from your source: MIC50/MIC90, a reported MIC range, or an additional count.');
      }
    }
    if(step===3&&payload.mode!=='distribution'&&!(payload.targets||[]).length)add('add-target','Add a concentration of interest. For example, ask how many isolates have MIC above 4 mg/L. The comparison needs a question to preserve.');
    return issues;
  }
  const api={blank,clone,importInput,importText,save,setSampleContext,setThresholdField,setTargetKind,setQuantile,exactCount,panelLabels,number,integer,parseJSON,sameDecimal,targets,percentToFraction,fractionToPercent,certificateInput,newCount,setCountField,countType,countPreview,setSuppressedCount,previewTable,stepIssues};
  if (typeof module !== 'undefined' && module.exports) module.exports=api;
  else root.MicFormModel=api;
})(globalThis);

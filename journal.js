'use strict';
(() => {
    let file, book, training, report;
    const names = {ab:'A–B', bc:'B–C', ac:'A–C'};
    const escape = text => String(text).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
    const label = (title, field) => '<label>'+title+field+'</label>';
    const select = (id, options) => '<select id="'+id+'">'+options+'</select>';
    const column = id => $(id).value === '' ? null : Number($(id).value);
    const zones = () => column('point_b') === null ? ['ac'] : ['ab','bc'];
    const options = (empty, selected) => '<option value="">'+empty+'</option>'+book.headers.map((h,i)=>
        '<option value="'+i+'"'+(i===selected?' selected':'')+'>'+escape(h)+' · '+(i+1)+'</option>').join('');
    const source = () => (training?'Учебные данные':'Загруженные данные')+' · '+file.name+(book.sheet?' / '+book.sheet:'');
    const find = re => book.headers.findIndex(h=>re.test(h));
    const drawTable = (head, rows) => '<table><thead><tr>'+head.map(h=>'<th>'+escape(h)+'</th>').join('')+
        '</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(v=>'<td>'+escape(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
    const numeric = v => String(v).replace('.',',');
    const signed = v => v===''?'—':(Number(v)>0?'+':'')+numeric(v);
    function clearReport() {
        report=null;
        $('journalResult').hidden=true;
    }
    function addWithdrawal(zone, i=-1) {
        const div=document.createElement('div');
        div.className='row';
        div.innerHTML=label('Столбец отбора','<select class="take">'+options('Выберите столбец',i)+'</select>')+
            '<button type="button">Убрать</button>';
        div.querySelector('button').onclick=()=>{div.remove();clearReport()};
        $('takes_'+zone).append(div);
    }
    function buildZones() {
        $('sectors').replaceChildren();
        for (const zone of zones()) {
            const field=document.createElement('fieldset');
            field.className='zone-settings';
            const matchZone = i => {
                const h=book.headers[i].toLowerCase().replace(/[\s–—-]/g,'');
                return zone==='ac'||h.includes(zone)||h.includes(zone==='ab'?'ав':'вс');
            };
            const limitId=book.headers.findIndex((h,i)=>/допуск/i.test(h)&&matchZone(i)&&
                (zone!=='ac'||/канал|a\W*c/i.test(h)));
            field.innerHTML='<legend>'+names[zone]+(zone==='ac'?' · весь канал':'')+'</legend>'+
                '<div id="takes_'+zone+'"></div><div class="row"><button id="add_'+zone+'">Добавить отбор</button>'+
                '<label><span><input type="checkbox" id="none_'+zone+'"> Отборов не было</span></label></div>'+
                '<div class="row">'+label('Допуск за одну смену',select('limit_'+zone,options('Ввести вручную / неизвестен',limitId)))+
                label('Одинаковый для каждой смены','<input id="fixed_'+zone+'" placeholder="Не указан" inputmode="decimal">')+'</div>';
            $('sectors').append(field);
            book.headers.forEach((h,i)=>{if(/отбор/i.test(h)&&matchZone(i))addWithdrawal(zone,i)});
            $('fixed_'+zone).disabled=limitId>=0;
            $('limit_'+zone).onchange=()=>$('fixed_'+zone).disabled=column('limit_'+zone)!==null;
            $('none_'+zone).onchange=()=>{
                const none=$('none_'+zone).checked;
                $('takes_'+zone).hidden=none;
                $('add_'+zone).disabled=none;
            };
            $('add_'+zone).onclick=()=>{addWithdrawal(zone);clearReport()};
        }
    }
    function configure() {
        clearReport();
        $('importPanel').hidden=false;
        $('sourceFile').textContent=source();
        $('sheetLabel').hidden=!book.sheets.length;
        $('worksheet').innerHTML=book.sheets.map(s=>'<option>'+escape(s)+'</option>').join('');
        $('worksheet').value=book.sheet;
        $('preview').innerHTML=drawTable(['Строка',...book.headers],book.rows.slice(0,5).map(([n,c])=>[n,...c]));
        const fields=[['period','Период',/смена|период|дата/i],['a','Вход A',/^(вход|подача|a\b)/i],
            ['b','Промежуточный B',/^(замер b|промежуточ|b\b)/i],['c','Выход C',/^(выход|c\b)/i]];
        $('points').innerHTML=fields.map(([k,title,re])=>label(title,select('point_'+k,options(
            k==='b'?'Без B · весь канал':'Выберите столбец',find(re))))).join('');
        $('point_b').onchange=buildZones;
        buildZones();
        $('points').insertAdjacentHTML('beforeend',label('Единицы в файле',select('unitColumn',options('Общие для журнала',find(/единиц|ед\.?\s*изм/i)))));
        typeHint();
    }
    function typeHint() {
        const kind=$('journalKind').value;
        $('typeHint').textContent=kind==='rate'?'Переведите расход в объём: умножьте расход в м³/с на длительность каждого интервала в секундах и сложите объёмы за смену.':
            'Для каждого канала вычтите начальное показание счётчика из конечного за одну смену. Проверьте сбросы счётчика.';
        $('typeHint').hidden=kind==='volume';
        $('check').disabled=kind!=='volume';
    }
    async function readSheet(sheet='') {
        clearReport();
        $('importPanel').hidden=true;
        const url=await new Promise((resolve,reject)=>{
            const reader=new FileReader();
            reader.onload=()=>resolve(reader.result);
            reader.onerror=()=>reject(Error('Ошибка чтения файла.'));
            reader.readAsDataURL(file);
        });
        book=await api('journal-load',{name:file.name,content:url.split(',')[1],sheet});
        configure();
    }
    async function open(f,isTraining) {
        training=isTraining;
        file=f;
        $('journalUnit').value='m3';
        $('journalKind').value='volume';
        await readSheet();
        if(training)await calculate();
        $(training?'journalResult':'importPanel').scrollIntoView({block:'start'});
    }
    async function calculate() {
        clearReport();
        const points=Object.fromEntries(['period','a','b','c'].map(k=>[k,column('point_'+k)]));
        const takes={},limits={};
        for(const z of zones()) {
            const none=$('none_'+z).checked;
            const selected=[...$('takes_'+z).querySelectorAll('select')].map(s=>s.value);
            if(!none&&selected.includes(''))throw Error(names[z]+': выберите столбец отбора.');
            takes[z]={none,columns:none?[]:selected.map(Number)};
            limits[z]={column:column('limit_'+z),value:$('fixed_'+z).value.trim()};
        }
        report=await api('journal-check',{headers:book.headers,rows:book.rows,mapping:{
            points,takes,limits,unitColumn:column('unitColumn'),kind:$('journalKind').value,unit:$('journalUnit').value}});
        $('resultSource').textContent=source();
        $('journalResult').hidden=false;
        const counts=[['Смен проверено',report.checked],['С превышением допуска',report.over],['Требуют уточнения',report.unclear]];
        $('indicators').innerHTML=counts.map(([k,v])=>'<div class="metric">'+k+'<b>'+v+'</b></div>').join('');
        $('report').innerHTML='<table><thead><tr><th>Строка</th><th>Смена</th><th>Участок</th><th>Остаток, м³</th><th>Допуск, м³</th><th>Вывод</th></tr></thead><tbody>'+
            report.results.map((r,i)=>'<tr data-index="'+i+'"><td><button class="link-button" aria-expanded="false">'+r.line+'</button></td><td>'+escape(r.period||'Не указана')+
            '</td><td>'+r.zone+'</td><td>'+signed(r.residual)+'</td><td>'+numeric(r.limit||'—')+'</td><td><span class="flag '+
            (r.status==='Превышен допуск'?'warn':r.status==='В пределах допуска'?'':'review')+'">'+r.status+'</span></td></tr>').join('')+'</tbody></table>';
    }
    $('report').onclick=e=>{
        const tr=e.target.closest('tr[data-index]');
        if(!tr)return;
        const prev=$('report').querySelector('.trace-row');
        const close=prev&&prev.previousElementSibling===tr;
        if(prev){prev.previousElementSibling.querySelector('button').setAttribute('aria-expanded','false');prev.remove()}
        if(close)return;
        const r=report.results[tr.dataset.index];
        tr.querySelector('button').setAttribute('aria-expanded','true');
        const detail=document.createElement('tr');
        detail.className='trace-row';
        detail.innerHTML='<td colspan="6"><div class="trace"><b>'+escape(source())+' · строка '+r.line+'</b><p>'+
            r.audit.map(escape).join(' · ')+'</p><code>'+escape(r.formula)+'</code><p>'+escape(r.why)+'</p></div></td>';
        tr.after(detail);
    };
    $('export').onclick=()=>{
        const rows=[['Источник','Строка','Смена','Участок','Остаток, м³','Допуск, м³','Статус','Исходные записи','Расчёт, м³','Объяснение'],
            ...report.results.map(r=>[source(),r.line,r.period,r.zone,numeric(r.residual),numeric(r.limit),r.status,r.audit.join(' | '),r.formula,r.why])];
        const quote=v=>{
            let text=String(v);
            if(/^\s*[=+@-]/.test(text)&&!/^[-+]?\d+([,.]\d+)?$/.test(text))text="'"+text;
            return '"'+text.replaceAll('"','""')+'"';
        };
        const csv=rows.map(row=>row.map(quote).join(';')).join('\r\n');
        const url=URL.createObjectURL(new Blob(['\ufeff',csv],{type:'text/csv;charset=utf-8'}));
        const a=document.createElement('a');a.href=url;a.download='Сверка водоучёта.csv';a.click();
        setTimeout(()=>URL.revokeObjectURL(url),1000);
    };
    $('upload').onclick=()=>$('journalFile').click();
    $('journalFile').onchange=()=>{const f=$('journalFile').files[0];$('journalFile').value='';if(f)guard(()=>open(f,false))};
    $('demo').onclick=()=>guard(async()=>{
        const res=await fetch('/journal.xlsx');
        if(!res.ok)throw Error('Учебный журнал недоступен.');
        await open(new File([await res.blob()],'journal.xlsx'),true);
    });
    $('worksheet').onchange=()=>guard(()=>readSheet($('worksheet').value));
    $('importPanel').oninput=clearReport;
    $('importPanel').addEventListener('change',clearReport);
    $('journalKind').onchange=typeHint;
    $('check').onclick=()=>guard(async()=>{await calculate();$('journalResult').scrollIntoView()});
    $('tabs').addEventListener('click',()=>{
        $('selector').hidden=!state.series||!['experiment','results'].includes(document.querySelector('#tabs .active').dataset.tab);
        $('error').hidden=true;
    });
})();


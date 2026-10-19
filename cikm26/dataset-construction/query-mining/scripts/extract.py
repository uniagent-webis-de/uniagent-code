import gzip,json,glob,re,os,collections
REQ=['case_id','event_id','timestamp','event_type','model','status']
QT={'bm25':'query','retrieve_corpus':'query','retrieve_hessian_law_de':'query','retrieve_university_kassel_public_de':'query','retrieve_university_kassel_public_en':'query','search_rules':'query','corpus_search':'queries','mounted_corpus.lexical_search':'terms'}
val=[];raw=[]
for p in sorted(glob.glob('/d/submissions/raw-outputs/*/*/output/run-trace.jsonl.log.gz')):
    rel=os.path.relpath(p,'/d/submissions/raw-outputs')
    ds=rel.split('/')[0]; app=ds.replace('task-2-','').replace('-20260928-test','')
    ev=[];reason=''
    try:
        for l in gzip.open(p,'rt'):
            e=json.loads(l)
            if not isinstance(e,dict): reason='non-object line';break
            m=[k for k in REQ if k not in e]
            if m: reason='missing '+','.join(m);break
            ev.append(e)
        else:
            if not ev: reason='empty'
            else:
                last={}
                for e in ev: last[e['case_id']]=e['event_type']
                if any(v!='decision' for v in last.values()): reason='trace does not end with decision'
    except Exception as x: reason=f'unreadable: {x}'
    val.append((rel,'false' if reason else 'true',reason))
    if reason: continue
    for e in ev:
        if e['event_type']!='tool_call' or e.get('tool') not in QT: continue
        i=e.get('input')
        if not isinstance(i,dict): continue
        v=i.get(QT[e['tool']])
        if isinstance(v,list): v=[' '.join(map(str,v))] if e['tool']=='mounted_corpus.lexical_search' else v
        else: v=[v]
        for q in v:
            if isinstance(q,str): raw.append(dict(query=q,application_type=app,case_id=e['case_id'],submission=os.path.dirname(os.path.dirname(rel)) if False else rel.rsplit('/output/',1)[0],tool=e['tool'],event_id=e['event_id']))
with open('/d/work/trace-validation.tsv','w') as f:
    f.write('path\tvalid\treason\n')
    for r in val: f.write('\t'.join(r)+'\n')
with open('/d/work/raw-queries.jsonl','w') as f:
    for r in raw: f.write(json.dumps(r,ensure_ascii=False)+'\n')
print(len(val),sum(v[1]=='true' for v in val),len(raw))
print(collections.Counter(v[2] for v in val))

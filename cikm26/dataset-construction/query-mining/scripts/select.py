import json,re
BAD=re.compile(r'Supernote|Bechtel|Warmer|Beschaßung|Lenovo|WPS|Bogen|Dagstuhl|IT Business|Kehl|Stuttgart|Fliegner',re.I)
cs=[json.loads(l) for l in open('/d/work/clusters.jsonl')]
out=[]
for c in cs:
    if c['num_submissions']<2: continue
    reps=[m for m in [c['representative']]+c['members'] if not BAD.search(m) and 2<=len(m.split())<=14]
    if not reps: continue
    out.append(dict(cluster_id=c['cluster_id'],query=reps[0],language=c['language'],application_types=c['application_types'],
      num_queries=c['num_queries'],num_submissions=c['num_submissions'],variants=[m for m in c['members'] if m!=reps[0]][:5]))
out=out[:100]
with open('/d/query-candidates.jsonl','w') as f:
    for o in out: f.write(json.dumps(o,ensure_ascii=False)+'\n')
print(len(out))

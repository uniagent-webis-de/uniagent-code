import json,re,collections
import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.cluster import AgglomerativeClustering
rows=[json.loads(l) for l in open('/d/work/normalized-queries.jsonl')]
rows=[r for r in rows if len(r['query'].split())>=2 and not re.search(r'\bemail\b|^(Is|Check|Please|Bitte)\b|Antrag .* approved|\bE\d{2}\b|kunsthochschule|^(Ob|Prüfen|Überprüfen|Bestätigen)\b',r['query'])]
GER=re.compile(r'ung\b|keit\b|[äöüß]|\b(und|der|die|das|für|bei|von|ob|mit|ohne|gibt|welche|dienst\w*|antrag\w*|beschaff\w*|erstattung|auslagen\w*)\b',re.I)
EN=set('the of for and to in without policy required requirements rules what which are is travel business expense reimbursement private payment documentation application'.split())
def lang(q):
    w=re.findall(r'\w+',q.lower());return 'de' if GER.search(q) else 'en'
X=TfidfVectorizer(analyzer='char_wb',ngram_range=(3,5),sublinear_tf=True).fit_transform([r['query'].lower() for r in rows]).toarray()
lab=AgglomerativeClustering(n_clusters=None,distance_threshold=0.65,metric='cosine',linkage='average').fit_predict(X)
cl=collections.defaultdict(list)
for r,l in zip(rows,lab): r['language']=lang(r['query']);cl[int(l)].append(r)
out=[]
for cid,m in cl.items():
    def score(r):
        n=len(r['query'].split());return (3<=n<=10,len(r['submissions']),r['count'])
    rep=max(m,key=score)
    out.append(dict(cluster_id=cid,representative=rep['query'],language=rep['language'],members=[r['query'] for r in m],size=len(m),
      application_types=sorted({a for r in m for a in r['application_types']}),num_queries=sum(r['count'] for r in m),
      num_submissions=len({s for r in m for s in r['submissions']})))
out.sort(key=lambda c:(-c['num_submissions'],-c['size']))
with open('/d/work/clusters.jsonl','w') as f:
    for c in out: f.write(json.dumps(c,ensure_ascii=False)+'\n')
print(len(rows),len(out))

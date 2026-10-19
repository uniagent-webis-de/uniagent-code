import json,re,collections
def norm(q): return re.sub(r'\s+',' ',q.strip().strip('"\'“”„').strip()).strip()
FILE=re.compile(r'\.(pdf|png|jpe?g|docx?|txt)\b|^[a-z]+-\d+$|\b(antrag|rechnung|beleg|angebot)-\d+',re.I)
CASE=re.compile(r'Universität Kehl|Technik-Universität Warmer|Seite \d+ von|Kunsthochschule|Stempel|Formular löschen|Subject:|ID: [A-Z-]+|\b[A-ZÄÖÜ]{3,} (GmbH|KG|UG)\b|\d{2}\.\d{2}\.\d{4}|\b\d{5} [A-ZÄÖÜ]')
PII=re.compile(r'\bDE\d{2}[ \d]{15,}|[\w.]+@[\w.]+\.\w+|\bIBAN\b',re.I)
agg={};seen=set();dropped=collections.Counter()
for l in open('/d/work/raw-queries.jsonl'):
    r=json.loads(l);q=norm(r['query'])
    if len(q)<3 or len(q)>200: dropped['length']+=1;continue
    if FILE.search(q): dropped['file/id']+=1;continue
    if CASE.search(q) or sum(c.isdigit() for c in q)/len(q)>0.15 or len(q)>120: dropped['case-text']+=1;continue
    if PII.search(q): dropped['pii']+=1;continue
    key=(r['submission'],r['case_id'],q.lower())
    if key in seen: dropped['dup-in-case']+=1;continue
    seen.add(key)
    a=agg.setdefault(q.lower(),dict(query=q,count=0,subs=set(),apps=set(),tools=set()))
    a['count']+=1;a['subs'].add(r['submission']);a['apps'].add(r['application_type']);a['tools'].add(r['tool'])
print(dropped,len(agg))
with open('/d/work/normalized-queries.jsonl','w') as f:
    for a in sorted(agg.values(),key=lambda a:-len(a['subs'])):
        f.write(json.dumps(dict(query=a['query'],count=a['count'],submissions=sorted(a['subs']),application_types=sorted(a['apps']),tools=sorted(a['tools'])),ensure_ascii=False)+'\n')

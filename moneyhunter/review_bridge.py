"""Bounded public approved-facts bridge. No credentials, pending data or durable trust cache."""
import hashlib
import json
import os
from urllib.parse import urlsplit, urlunsplit
from urllib.request import Request, urlopen
from . import evidence

LAST_RECORDS=[]
LAST_REVISIONS={}
LAST_STATUS={'status':'not_loaded','records':0,'sold_observations':0,'cash_quotes':0}

def revision(record):
    return hashlib.sha256(json.dumps(record,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()

def validate_payload(doc):
    import datetime as dt
    if not isinstance(doc,dict) or doc.get('schema_version')!=1 or doc.get('kind')!='human_reviewed_public_facts':raise ValueError('invalid reviewed bridge schema')
    when=dt.datetime.fromisoformat(doc['generated_at'].replace('Z','+00:00'))
    if when.tzinfo is None or not 0<=(dt.datetime.now(dt.timezone.utc)-when).total_seconds()<300:raise ValueError('stale/future reviewed snapshot')
    rows=doc.get('records');revisions=doc.get('record_revisions',{})
    if not isinstance(rows,list) or len(rows)>400:raise ValueError('invalid/bounded review records')
    validated=[evidence.validate(r) for r in rows]
    if any(not r['id'].startswith('community_') or revisions.get(r['id'])!=revision(r) for r in validated):raise ValueError('review revision mismatch')
    if len({r['id'] for r in validated})!=len(validated):raise ValueError('duplicate reviewed id')
    urls=[o['url'] for r in validated for o in r['observations']]
    if len(urls)!=len(set(urls)):raise ValueError('duplicate reviewed sale')
    return validated,revisions

def load(native=()):
    global LAST_RECORDS,LAST_REVISIONS,LAST_STATUS
    LAST_RECORDS=[];LAST_REVISIONS={};LAST_STATUS={'status':'not_configured','records':0,'sold_observations':0,'cash_quotes':0,'outcomes':'private; never exported'}
    endpoint=os.getenv('MONEYHUNTER_CAPTURE_URL')
    if not endpoint:return []
    u=urlsplit(endpoint)
    if u.scheme!='https' or u.username or u.password or u.query or u.fragment or u.path!='/api/research-capture':
        LAST_STATUS['status']='invalid_existing_capture_endpoint';return []
    url=urlunsplit((u.scheme,u.netloc,'/api/reviewed-evidence','',''))
    try:
        with urlopen(Request(url,headers={'User-Agent':'MoneyHunter-reviewed-facts/1'}),timeout=12) as response:
            body=response.read(2_000_001)
            if len(body)>2_000_000:raise ValueError('review payload too large')
            # Redirects cannot introduce an unexpected trust host.
            if urlsplit(response.url).netloc!=u.netloc:raise ValueError('unexpected review redirect')
        records,revisions=validate_payload(json.loads(body))
        old_urls={u for c in native for u in getattr(c,'source_urls',[])}
        if any(o['url'] in old_urls for r in records for o in r['observations']):raise ValueError('sold source already in native reviewed store')
        comps=evidence.load(records=records)
        for comp in comps:
            comp.evidence_record_id=comp.source.removeprefix('reviewed evidence ')
            comp.evidence_revision=revisions[comp.evidence_record_id]
        LAST_RECORDS=records;LAST_REVISIONS=revisions
        LAST_STATUS.update(status='ready',worker_status=json.loads(body).get('status','unknown'),records=len(records),sold_observations=sum(len(r['observations']) for r in records),cash_quotes=sum(bool(r.get('floor')) for r in records))
        return comps
    except Exception as exc:
        LAST_STATUS.update(status='unavailable_fail_closed',reason=type(exc).__name__)
        return []

def catalog():
    return [{**x,'evidence_record_id':x['id'],'evidence_revision':LAST_REVISIONS[x['id']]} for x in evidence.public_catalog(records=LAST_RECORDS)]

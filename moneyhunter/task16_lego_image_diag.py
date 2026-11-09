"""Task 16 Part A — LEGO image-gate diagnostic (MH_TASK16_TRACE=1)."""
from __future__ import annotations
import json, os
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit
from . import publication, images, market, pricing_labels
import re

def _set_number(row):
    ident=market.identity(row)
    if not ident: return None
    ids=re.findall(r'(?<!\d)\d{5,6}(?!\d)', ident.match)
    return ids[0] if len(ids)==1 else None

def _source_label(url, basis=''):
    host=urlsplit(url or '').hostname or ''
    if 'hotukdeals' in host or 'pepper' in host: return 'own-source/HUKD'
    if 'ebayimg' in host: return 'eBay catalogue/ask reference'
    if basis.startswith('Reference'): return 'exact-set reference'
    if basis.startswith('Own'): return 'own-source/HUKD'
    return host or 'missing_url'

def diagnose(raws, state, path=None):
    path=path or os.environ.get('MH_TASK16_TRACE_PATH','task16_partA_lego_image_diagnostic.json')
    now=datetime.now(timezone.utc)
    cache=state.get('product_images_v1') or {}
    paused=state.get('product_image_paused_hosts') or {}
    rows=[]
    for r in raws:
        if r.get('category')!='lego' or not publication.allowed(r):
            continue
        proof=publication.proof(r)
        thumb=r.get('thumb') or ''
        candidates=list(dict.fromkeys(([thumb] if thumb else [])+(r.get('image_candidates') or [])))
        attempts=[]
        for u in candidates[:6]:
            safe=images.safe(u)
            rec=cache.get(safe or u) or {}
            live_ok=None; live_reason=None
            if safe:
                live_ok, live_reason=images.probe(safe)
            elif u:
                live_ok, live_reason=False, 'source_not_allowed_or_unsafe'
            else:
                live_ok, live_reason=False, 'missing_url'
            # Map to Part A vocabulary
            result='success' if live_ok else {
                'http_404':'404','http_403':'source_not_allowed','http_401':'source_not_allowed',
                'non_image_or_status':'mime_or_signature_reject','unavailable':'timeout_or_unavailable',
                'unsafe_url':'source_not_allowed','source_not_allowed_or_unsafe':'source_not_allowed',
                'missing_url':'missing_url',
            }.get(live_reason or '', live_reason or 'unknown')
            if live_reason=='non_image_or_status':
                # distinguish mime vs signature if possible — probe already combined; keep precise reason
                result='mime_or_signature_reject'
            attempts.append({
                'image_url': safe or u,
                'safe': bool(safe),
                'image_check_result': result,
                'image_check_reason': live_reason,
                'cache_ok': rec.get('ok'),
                'cache_status': rec.get('status'),
                'cache_expires': rec.get('expires'),
                'cache_checked_at': rec.get('checked_at'),
                'image_check_source': _source_label(safe or u, r.get('image_basis') or ''),
            })
        primary=attempts[0] if attempts else {
            'image_url': None, 'image_check_result':'missing_url', 'image_check_reason':'missing_url',
            'image_check_source':'missing_url',
        }
        rows.append({
            'set_number': _set_number(r),
            'title': r.get('title'),
            'offer_url': r.get('url'),
            'selling_price': proof.get('listing'),
            'publication_allowed': True,
            'publishable': images.publishable(r, now),
            'image_status': r.get('image_status'),
            'image_verified_url': r.get('image_verified_url'),
            'image_verified_until': r.get('image_verified_until'),
            'image_basis': r.get('image_basis'),
            'image_url': primary.get('image_url'),
            'image_check_result': primary.get('image_check_result'),
            'image_check_reason': primary.get('image_check_reason'),
            'image_check_attempted_at': now.isoformat(),
            'image_check_source': primary.get('image_check_source'),
            'attempts': attempts,
            'paused_hosts': dict(paused),
        })
    # Same-stage analysis
    stages=[r['image_check_result'] for r in rows]
    from collections import Counter
    payload={
        'generated_at': now.isoformat(),
        'count': len(rows),
        'all_fail_same_stage': len(set(stages))==1 if stages else None,
        'result_counts': dict(Counter(stages)),
        'status_counts': dict(Counter(r.get('image_status') for r in rows)),
        'publishable_count': sum(1 for r in rows if r['publishable']),
        'cache_entries': len(cache),
        'paused_hosts': dict(paused),
        'MAX_FETCHES': images.MAX_FETCHES,
        'TTL_SECONDS': images.TTL_SECONDS,
        'note': 'Live probe during diagnostic. After Task 16 fix, prepare() re-runs post-ask_estimate preferring publication.allowed LEGO.',
        'items': rows,
        'pricing_labels': pricing_labels.summarize(raws),
    }
    Path(path).write_text(json.dumps(payload, indent=2, default=str)+'\n')
    try:
        Path('/workspace/task16_partA_lego_image_diagnostic.json').write_text(Path(path).read_text())
    except OSError:
        pass
    return payload

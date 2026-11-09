"""Honest pricing labels for scan/diagnostic reports (Task 16 Part D).

exact_priced: publication.allowed — has a source-supported selling/listing price
research_model_only: has ask_estimate but is not publication.allowed (no sellable price)
unpriced: no ask_estimate

approximate_priced is retired — it previously counted research models without a
supported selling price as "priced", which was misleading (Task 15: 22 approx
with selling_price null).
"""
from __future__ import annotations
from collections import Counter

def selling_price_of(row):
    """Supported selling/listing price when publication.allowed, else None."""
    try:
        from . import publication
        if publication.allowed(row):
            listing = publication.proof(row).get('listing')
            if isinstance(listing, (int, float)):
                return float(listing)
    except Exception:
        pass
    return None

def classify(row):
    """Return exact_priced | research_model_only | unpriced."""
    if selling_price_of(row) is not None:
        return 'exact_priced'
    if row.get('ask_estimate'):
        return 'research_model_only'
    return 'unpriced'

def summarize(rows):
    counts = Counter(classify(r) for r in rows)
    return {
        'exact_priced': counts.get('exact_priced', 0),
        'research_model_only': counts.get('research_model_only', 0),
        'unpriced': counts.get('unpriced', 0),
        'approximate_priced': None,
        'label_note': (
            'approximate_priced renamed to research_model_only (Task 16 Part D); '
            'exact_priced requires publication.allowed supported selling/listing price'
        ),
    }

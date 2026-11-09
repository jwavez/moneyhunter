"""Honest pricing labels for scan/diagnostic reports (Task 16 Part D).

exact_priced: has a real selling_price (supported listing / suggested_listing)
research_model_only: has ask_estimate data but no selling_price
unpriced: no estimate data

approximate_priced is retired — it previously counted research models with
selling_price null as "priced", which was misleading.
"""
from __future__ import annotations
from collections import Counter

def selling_price_of(row):
    """Numeric selling price when the row has a concrete listing figure."""
    m = row.get('ask_estimate') or {}
    # Explicit selling_price wins when present and numeric
    sp = m.get('selling_price')
    if isinstance(sp, (int, float)):
        return float(sp)
    # Publication-supported listing / suggested_listing is the real sell figure
    for key in ('suggested_listing',):
        v = m.get(key)
        if isinstance(v, (int, float)):
            return float(v)
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
            'exact_priced requires a real selling/listing price'
        ),
    }

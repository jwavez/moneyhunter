"""One public estimate policy; no account balances or automatic tier promotion."""
import math
import os
from . import config as C

def current():
    try: index = int(os.getenv('MH_TIER', '0'))
    except (ValueError, TypeError): index = 0
    if not 0 <= index < len(C.COMMUNITY_CAPS) or os.getenv('MH_TIER_WARNING'): index = 0
    tier = C.tier_for(C.COMMUNITY_RULE_BANKROLLS[index])
    return {'community_index':index, 'cap':C.COMMUNITY_CAPS[index], 'strong_net':tier.min_net,
            'strong_roi':tier.min_roi/100, 'review_net':10., 'review_roi':.2, 'review_stress_drop':.1, 'review_stress_net':5., 'review_stress_roi':.1,
            'watch_ceiling':C.COMMUNITY_CAPS[index]*2.5}

def ceiling(proceeds, minimum, roi, cap):
    return max(0, math.floor(min(proceeds-minimum, proceeds/(1+roi), cap)*100)/100)

"""Separate explicitly priced secondary tool offers; never treat them as postage."""
import re
MODELS=r'(?:DUB\d+[A-Z]*|BL\d+[A-Z]*|DCF\d+[A-Z0-9]*(?:-[A-Z]+)?|DT\d+(?:-[A-Z]+)?)'
def primary(raw):
    x=dict(raw);title=x.get('title','')
    parts=re.split(r'\s+(?://|/)\s+(?=(?:Makita|DeWalt)\b)',title,maxsplit=1,flags=re.I)
    if len(parts)==2 and re.search(MODELS,parts[0],re.I) and re.search(MODELS,parts[1],re.I):
        secondary=re.findall(r'£\s*(\d+(?:\.\d{1,2})?)',parts[1])
        if x.get('price_basis')=='rss_merchant_price' and len(secondary)==1 and float(secondary[0])!=x.get('price') and re.search(r'bare|body only|tool only',parts[0],re.I):
            x.update(source_title=title,title=parts[0].strip(),secondary_offer_note=parts[1],primary_offer_status='primary RSS merchant price; separate optional offer not included')
        else:x['offer_ambiguity']='Multiple separately named tool/accessory prices; primary acquisition not verified'
    return x

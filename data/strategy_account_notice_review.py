"""Bounded RSS content matching; metadata dates/URLs are not issuer mentions."""
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime


def normalized(text):
    return ' '.join(re.sub(r'<[^>]*>', ' ', html.unescape(text)).split())


def review_notices(raw, *, ticker, issuer_names):
    audit=[];blocking=[]
    for ordinal,item in enumerate(ET.fromstring(raw).iter()):
        if item.tag.rsplit('}',1)[-1]!='item':continue
        fields={}
        for node in item:
            field=node.tag.rsplit('}',1)[-1]
            if field in {'title','description','content','summary','encoded'}:
                fields.setdefault(field,[]).append(normalized(' '.join(node.itertext())))
        titles=fields.get('title',[])
        # Exact official listing headline grammar only. Other titles fail closed.
        headline=re.fullmatch(r'ETP\d{4}-\d+ - Nasdaq to Begin Listing .+ ETF on '
            r'((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), '
            r'[A-Z][a-z]+ \d{1,2}, \d{4})',titles[0]) if len(titles)==1 else None
        listing=False
        if headline:
            try:
                date=datetime.strptime(headline[1],'%A, %B %d, %Y')
                listing=date.strftime('%A')==headline[1].split(',')[0]
            except ValueError:pass
        for field,values in fields.items():
            for text in values:
                for term,kind in [(ticker,'ticker')]+[(n,'issuer_name') for n in issuer_names]:
                    match=re.search(r'(?<![A-Za-z0-9])'+re.escape(normalized(term))+r'(?![A-Za-z0-9])',text,re.I)
                    if not match:continue
                    exempt=listing and field=='title' and kind=='ticker'
                    row=dict(item_ordinal=ordinal,field=field,term=term,term_type=kind,
                        title=titles[0] if titles else '',excerpt=text[max(0,match.start()-80):match.end()+160],
                        disposition='ETF_LISTING_TITLE_UNDERLYING_MENTION' if exempt else 'REQUIRES_REVIEW')
                    audit.append(row)
                    if not exempt:blocking.append(row)
    return dict(blocking=blocking,matches=audit)

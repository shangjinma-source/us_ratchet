"""Parse one immutable RSS body once; preserve original per-issuer audit rows."""
from datetime import datetime
import re
import xml.etree.ElementTree as ET

from data.strategy_account_notice_review import normalized


class CompiledNoticeReview:
    def __init__(self, raw):
        items = []
        for ordinal, item in enumerate(ET.fromstring(raw).iter()):
            if item.tag.rsplit('}', 1)[-1] != 'item':
                continue
            fields = {}
            for node in item:
                field = node.tag.rsplit('}', 1)[-1]
                if field in {'title', 'description', 'content', 'summary', 'encoded'}:
                    fields.setdefault(field, []).append(normalized(' '.join(node.itertext())))
            titles = fields.get('title', [])
            headline = re.fullmatch(
                r'ETP\d{4}-\d+ - Nasdaq to Begin Listing .+ ETF on '
                r'((?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday), '
                r'[A-Z][a-z]+ \d{1,2}, \d{4})', titles[0]) if len(titles) == 1 else None
            listing = False
            if headline:
                try:
                    date = datetime.strptime(headline[1], '%A, %B %d, %Y')
                    listing = date.strftime('%A') == headline[1].split(',')[0]
                except ValueError:
                    pass
            items.append((ordinal, titles[0] if titles else '', listing,
                          tuple((field, tuple(values)) for field, values in fields.items())))
        self._items = tuple(items)

    def review(self, *, ticker, issuer_names):
        terms = [(ticker, 'ticker')] + [(name, 'issuer_name') for name in issuer_names]
        patterns = [(term, kind, re.compile(
            r'(?<![A-Za-z0-9])' + re.escape(normalized(term)) + r'(?![A-Za-z0-9])', re.I))
            for term, kind in terms]
        audit, blocking = [], []
        for ordinal, title, listing, fields in self._items:
            for field, values in fields:
                for text in values:
                    for term, kind, pattern in patterns:
                        match = pattern.search(text)
                        if not match:
                            continue
                        exempt = listing and field == 'title' and kind == 'ticker'
                        row = dict(item_ordinal=ordinal, field=field, term=term, term_type=kind,
                                   title=title, excerpt=text[max(0, match.start()-80):match.end()+160],
                                   disposition='ETF_LISTING_TITLE_UNDERLYING_MENTION'
                                   if exempt else 'REQUIRES_REVIEW')
                        audit.append(row)
                        if not exempt:
                            blocking.append(row)
        return dict(blocking=blocking, matches=audit)

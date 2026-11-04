"""Calendar-only selection; source transport and ordinary news ordering unchanged."""
import re
from docs.candidates.news_issuer_source_calendar_hook import capture as capture_issuer, candidate_headlines, text
CHANGE=re.compile(r'cancel|postpon|reschedul|date change|new date|revises date|changes date',re.I)
def calendar_headlines(document):
    def selected(row):
        title=text(row['headline']).lower()
        financial=any(term in title for term in ('financial results','earnings','financial conference call'))
        scheduling=any(term in title for term in ('to report','will report','conference call','webcast','schedule','date')) or bool(CHANGE.search(title))
        return financial and scheduling
    return candidate_headlines(document,predicate=selected)

def capture(cache, *, session=None, now=None):
    result=capture_issuer(cache,session=session,now=now,headline_selector=calendar_headlines)
    # Do not silently retain an older date when the reader cannot admit a change.
    if any(CHANGE.search(event['title']) for event in result['events']):
        result['errors'].append(dict(source='Moderna calendar',message='SCHEDULE_CHANGE_REQUIRES_REVIEW'))
    return result

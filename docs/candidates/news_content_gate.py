"""Candidate content admission; no network/model and no production imports."""
import re
from html import unescape

def normalized(value):
    return re.sub(r'\s+',' ',unescape(re.sub(r'<[^>]+>',' ',value or ''))).strip().casefold()

def analysis_skip_reason(event):
    if event.get('content_kind')=='SEC_METADATA_ONLY' or event.get('source','').startswith('SEC '):
        return 'SKIPPED_METADATA_ONLY'
    body=normalized(event.get('source_text'));title=normalized(event.get('title'))
    if len(body)<80 or body==title:
        return 'SKIPPED_INSUFFICIENT_TEXT'
    if event.get('noise_hint')=='LOW_INFORMATION_EMPLOYER_AWARD':
        return 'SKIPPED_LOW_INFORMATION'
    return None

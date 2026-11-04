"""One source-background development probe; never writes a live account."""
import json
import sys
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from data import news_investment_model_v1 as model
from data.news_background_context_v1 import BACKGROUND_INSTRUCTION, attach_background
from data.news_model_coordinator_v1 import ModelCoordinator


def save(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')


def main():
    original = ROOT / 'tmp/news_five_case_execution_20261029/PDD_20230320'
    folder = ROOT / 'tmp/news_pdd_expectations_20261104'
    old = (original / 'A_prompt.txt').read_bytes()
    body_raw = (folder / 'pdd_section.txt').read_bytes()
    body = (folder / 'pdd_section.txt').read_text(encoding='utf-8').encode('utf-8')
    assert sha256(old).hexdigest() == 'ecf9b3849890785b423a4fc0ca511dba40a075febaf753b011fc7deb989f8e53'
    assert sha256(body).hexdigest() == '78cceac4d1dea44a9c6845ba9b154dd13fe33ed9f73ec13e80a715aa48ecd3d5'
    prefix, input_text = old.decode().split('\nPUBLIC_INPUT\n', 1)
    payload = json.loads(input_text)
    receipt = json.loads((folder / 'receipt.json').read_bytes())
    background = dict(id='PDD_20230317_EXPECTATIONS', role='BACKGROUND',
        eligible_as_new_trigger=False, may_refresh_event_window=False,
        content_kind='FULL_TEXT', text=body.decode(), text_sha256=sha256(body).hexdigest(),
        title='PDD section of earnings preview', url=receipt['url'],
        published_at='2023-03-17T10:08:00-04:00', publication_date='2023-03-17',
        publication_time_quality='PUBLISHER_DISPLAY_MODERN_RETRIEVAL',
        observed_at=receipt['received_at'], security_ids=['research:security:pdd'],
        reference_period='Q4 2022 forecast and explicitly labeled subsequent annual forecasts',
        limitations=['Modern retrieval; original historical version unverified.',
                    'Publisher-reported expectations, not original consensus vendor snapshot.',
                    'FX assumptions, analyst sample, and EPS versus ADS basis not fully harmonized.',
                    'Not issuer guidance; do not calculate a certified exact earnings surprise.',
                    'Hypothetical historical availability only; not measured historical discovery.'])
    enriched = attach_background(payload, [background])
    assert enriched['positions'] == payload['positions']
    for before, after in zip(payload['sources'], enriched['sources']):
        assert dict(before, role='TRIGGER') == after
    prompt = prefix + BACKGROUND_INSTRUCTION + '\nPUBLIC_INPUT\n' + json.dumps(enriched, ensure_ascii=False, sort_keys=True)
    output = folder / 'A_background_run1'
    output.mkdir(exist_ok=False)  # A terminal failure is retained; no automatic retry.
    (output / 'prompt.txt').write_text(prompt, encoding='utf-8')
    save(output / 'input.json', enriched)
    contract = dict(model='gpt-6.1-sol', effort='medium', max_calls=1, retries=0,
                    timeout_seconds=120, original_prompt_sha256=sha256(old).hexdigest(),
                    prompt_sha256=sha256(prompt.encode()).hexdigest(),
                    background_sha256=sha256(body).hexdigest(), production_authorized=False,
                    background_file_sha256=sha256(body_raw).hexdigest(),
                    background_normalization='UTF-8 text; CRLF normalized to LF as recorded by capture',
                    simulation_as_of='2023-03-20T10:32:00+00:00',
                    source_pins={name: sha256((ROOT/name).read_bytes()).hexdigest() for name in
                        ['data/news_investment_model_v1.py', 'data/news_desk.py',
                         'data/news_background_context_v1.py', 'data/news_model_coordinator_v1.py']})
    save(output / 'contract.json', contract)
    result = dict(status='PREPARED', attempts=0, started_at=datetime.now(timezone.utc).isoformat())
    save(output / 'receipt.json', result)
    try:
        with ModelCoordinator(ROOT / 'data/cache/news').reserve('event'):
            result.update(status='STARTED', attempts=1)
            save(output / 'receipt.json', result)
            answer, usage = model._invoke(prompt, output, 120)
            save(output / 'raw_answer.json', answer)
            validated = model._validate(deepcopy(answer), enriched)
            save(output / 'result.json', validated)
            result.update(status='PENDING_SEMANTIC_REVIEW', usage=usage)
    except Exception as error:
        result.update(status='FAILED', error=str(error))
    finally:
        result['finished_at'] = datetime.now(timezone.utc).isoformat()
        save(output / 'receipt.json', result)
    print(json.dumps(result))


if __name__ == '__main__':
    main()

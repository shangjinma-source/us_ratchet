"""Launch exactly one frozen batch; the supervisor owns the shared deadline."""
import argparse
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backtest.fixed_research_batch import run_batch


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--registration', required=True)
    parser.add_argument('--sha256', required=True)
    args = parser.parse_args()
    raw = Path(args.registration).read_bytes()
    if sha256(raw).hexdigest() != args.sha256:
        raise ValueError('REGISTRATION_CHANGED')
    registration = json.loads(raw)
    result = run_batch(registration=registration, output_directory=registration['output_directory'])
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()

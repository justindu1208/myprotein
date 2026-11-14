"""Offline harness: python -m protolab.binder_cli input.json > report.json.

Input is trusted adapter output, NOT a public endpoint accepting LLM evidence.
"""
import argparse
import json
from pathlib import Path
from .harness import BinderHarness, Evidence, Policy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    try:
        data = json.loads(args.input.read_text())
        harness = BinderHarness(Policy(**data['policy']))
        report = harness.run(data['request'], data.get('candidates', []),
                             [Evidence(**e) for e in data.get('evidence', [])],
                             data.get('retries'), data.get('errors'))
    except (ValueError, TypeError, KeyError, OSError) as exc:
        parser.exit(2, f'Invalid harness input: {exc}\n')
    print(json.dumps(report, indent=2, allow_nan=False))


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""Offline package and anonymized measurement-ledger validation."""
import argparse
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from urllib.parse import unquote, urlparse

import yaml

ROOT = Path(__file__).resolve().parents[1]


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_package():
    skills = [p for p in (ROOT / 'skills').iterdir() if (p / 'SKILL.md').is_file()]
    require(len(skills) == 1, 'Expected one standalone skill')
    skill = skills[0]
    text = (skill / 'SKILL.md').read_text()
    match = re.match(r'\A---\n(.*?)\n---\n', text, re.S)
    require(match, 'Missing YAML frontmatter')
    front = yaml.safe_load(match.group(1))
    require(isinstance(front, dict), 'Frontmatter must be a mapping')
    require(front.get('name') == skill.name, 'Skill name must match folder')
    require(bool(re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', front['name'])), 'Invalid skill name')
    require(len(front['name']) <= 64, 'Skill name too long')
    require(isinstance(front.get('description'), str) and front['description'].strip(), 'Missing description')
    ui = yaml.safe_load((skill / 'agents/openai.yaml').read_text())
    require(isinstance(ui, dict) and isinstance(ui.get('interface'), dict), 'Missing UI interface')
    for key in ('display_name', 'short_description', 'default_prompt'):
        require(isinstance(ui['interface'].get(key), str) and ui['interface'][key].strip(), f'Missing UI {key}')
    docs = [ROOT / 'README.md', *list((ROOT / 'docs').rglob('*.md')), *list(skill.rglob('*.md'))]
    for path in docs:
        for target in re.findall(r'\]\(([^)]+)\)', path.read_text()):
            parsed = urlparse(target.strip('<>'))
            if parsed.scheme or not parsed.path:
                continue
            dest = (path.parent / unquote(parsed.path)).resolve()
            require(dest.is_relative_to(ROOT), f'External local reference in {path.relative_to(ROOT)}')
            require(dest.exists(), f'Broken link: {path.relative_to(ROOT)} -> {target}')
    require((ROOT / 'LICENSE').is_file(), 'Missing LICENSE')
    print('Package metadata and local links: PASS')


def validate_evidence(path):
    data = json.loads(path.read_text())
    require(data['metric'] == 'CoreCCU' and data['compute_type'] == 'NRDB Queries', 'Mixed or unknown units')
    rows = data['rows']
    require(len({r['case'] for r in rows}) == len(rows), 'Duplicate case IDs')
    require(set(r['phase'] for r in rows) == {'before', 'after'}, 'Invalid comparison phases')
    for phase in ('before', 'after'):
        items = [r for r in rows if r['phase'] == phase]
        for row in items:
            require(row['successful_executions'] == row['usage_records'] == 1, 'Attribution requires one execution and usage record')
            require(type(row['inspected_events']) is int and row['inspected_events'] >= 0, 'Invalid inspected count')
            value = Decimal(row['recorded_core_ccu'])
            require(value.is_finite() and value >= 0, 'Invalid CCU')
        totals = data['totals'][phase]
        require(sum(r['successful_executions'] for r in items) == totals['executions'], f'{phase} executions mismatch')
        require(sum(r['inspected_events'] for r in items) == totals['inspected_events'], f'{phase} inspected count mismatch')
        require(sum(Decimal(r['recorded_core_ccu']) for r in items) == Decimal(totals['recorded_core_ccu']), f'{phase} CCU mismatch')
    require(data['validation_query_count'] >= sum(r['successful_executions'] for r in rows), 'Validation count omits compared queries')
    print('Measurement ledger units, attribution counts and sums: PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path)
    default_evidence = ROOT / 'docs/evidence/site-performance.json'
    args = parser.parse_args()
    try:
        validate_package()
        if args.evidence is not None:
            validate_evidence(args.evidence)
        elif default_evidence.exists():
            validate_evidence(default_evidence)
    except (ValueError, KeyError, TypeError, OSError, yaml.YAMLError) as exc:
        print(f'FAIL: {exc}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

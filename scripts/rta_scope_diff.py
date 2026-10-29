#!/usr/bin/env python3
"""Compare explicit ZIP/EPUB members and gate changes with a declarative allowlist.

No extraction, no write, no network. Byte-level / ZIP-header scopes are distinct.
"""
from __future__ import annotations

import argparse
from fnmatch import fnmatchcase
import hashlib
import json
from pathlib import Path
import sys
import zipfile


def member_digest(z: zipfile.ZipFile, name: str) -> str:
    h = hashlib.sha256()
    with z.open(name) as f:
        for block in iter(lambda: f.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def scope_diff(before: Path, after: Path, policy: Path) -> dict:
    rules = json.loads(policy.read_text('utf-8'))
    required = ('changed', 'added', 'removed')
    if not isinstance(rules, dict) or any(not isinstance(rules.get(k), list) or
         any(not isinstance(v, str) or not v for v in rules[k]) for k in required):
        raise ValueError('policy must have changed, added, removed lists of glob patterns')
    with zipfile.ZipFile(before) as left, zipfile.ZipFile(after) as right:
        if left.testzip() or right.testzip():
            raise ValueError('ZIP integrity check failed')
        lnames, rnames = left.namelist(), right.namelist()
        if len(lnames) != len(set(lnames)) or len(rnames) != len(set(rnames)):
            raise ValueError('duplicate member names; refusing ambiguous ZIP')
        ls, rs = set(lnames), set(rnames)
        added = sorted(rs - ls)
        removed = sorted(ls - rs)
        changed = sorted(name for name in (ls & rs)
                         if member_digest(left, name) != member_digest(right, name))
        # Header and ordering modifications may matter for reproducibility even when bytes agree.
        meta = sorted(n for n in ls & rs
                      if (left.getinfo(n).date_time, left.getinfo(n).compress_type,
                          left.getinfo(n).external_attr, left.getinfo(n).flag_bits)
                      != (right.getinfo(n).date_time, right.getinfo(n).compress_type,
                          right.getinfo(n).external_attr, right.getinfo(n).flag_bits))
        order_same = lnames == rnames
    def denied(items: list[str], patterns: list[str]):
        return [n for n in items if not any(fnmatchcase(n, pattern) for pattern in patterns)]
    unexpected = {k: denied(v, rules[k]) for k,v in
                  [('changed',changed),('added',added),('removed',removed)]}
    # Strict default: metadata and order differences are reported, not treated as scope failure,
    # because ZIP headers may vary with local compressor; the caller may opt in.
    strict_meta = rules.get('strict_metadata', False)
    strict_order = rules.get('strict_order', False)
    if not isinstance(strict_meta, bool) or not isinstance(strict_order, bool):
        raise ValueError('strict_metadata and strict_order must be booleans')
    pass_scope = (not any(unexpected.values())
                  and (not strict_meta or not meta)
                  and (not strict_order or order_same))
    return {'status': 'SCOPE_PASS' if pass_scope else 'SCOPE_FAIL',
            'changed': changed, 'added': added, 'removed': removed,
            'unexpected': unexpected, 'header_metadata_changed': meta,
            'member_order_equal': order_same,
            'strict_metadata': strict_meta, 'strict_order': strict_order,
            'warning': 'Byte/member scope is NOT semantic, video, accessibility or rights acceptance.'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--before', type=Path, required=True)
    p.add_argument('--after', type=Path, required=True)
    p.add_argument('--policy', type=Path, required=True)
    args = p.parse_args()
    try:
        r = scope_diff(args.before, args.after, args.policy)
    except (OSError, ValueError, json.JSONDecodeError, zipfile.BadZipFile) as exc:
        print(f'RTA_SCOPE_ERROR: {type(exc).__name__}: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(r, ensure_ascii=False, indent=2))
    return 0 if r['status'] == 'SCOPE_PASS' else 3

if __name__ == '__main__':
    raise SystemExit(main())

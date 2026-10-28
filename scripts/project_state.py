#!/usr/bin/env python3
'''Inspect an optional knowledge-project manifest without running its tasks.
- 🎯Expose current artifacts and reusable review bindings without a required framework.
- 🤖Agent-authored; hash binding is not a semantic acceptance decision.
'''
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sys


SCHEMA_VERSION: str = 'knowledge-project/1'
'''📌Version of the optional project adapter; source kinds remain open strings.'''
DIGEST_PATTERN: re.Pattern[str] = re.compile(r'[0-9a-fA-F]{64}')
'''📌A digest denotes SHA-256, never an mtime/size fingerprint.'''
ACCEPTED_STATUSES: frozenset[str] = frozenset({'passed', 'passed_with_uncertainties'})
'''📌Stored reviewer outcomes eligible for binding checks, not generated verdicts.'''


@dataclass(frozen=True)
class Asset:
    '''A registered source or derived artifact.
    - 📌Paths are references; inspection never relocates or modifies them.
    '''
    identifier: str
    kind: str
    path: Path | None
    dependencies: tuple[str, ...]
    checks: tuple[dict[str, object], ...]


def digest_file(path: Path) -> str:
    '''Hash an explicitly selected local file using bounded reads.'''
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def __local_path(value: object, base: Path) -> Path | None:
    '''Resolve a local reference while leaving an absent capture explicit.'''
    if value is None:
        return None
    if not isinstance(value, str) or not value:
        raise ValueError('path must be a nonempty local path or absent')
    if '://' in value:
        raise ValueError('path must be local; store an original URL in a separate url field')
    path = Path(value)
    return (base / path).resolve() if not path.is_absolute() else path.resolve()


def load_project(path: Path) -> tuple[dict[str, Asset], dict[str, str]]:
    '''Validate reference identities while permitting new kinds and extra metadata.'''
    data = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(data, dict) or data.get('schema_version') != SCHEMA_VERSION:
        raise ValueError(f'expected schema_version {SCHEMA_VERSION!r}')
    assets: dict[str, Asset] = {}
    for collection in ('sources', 'artifacts'):
        records = data.get(collection, [])
        if not isinstance(records, list):
            raise ValueError(f'{collection} must be a list')
        for row in records:
            if not isinstance(row, dict):
                raise ValueError(f'{collection} contains a non-object')
            identifier, kind = row.get('id'), row.get('kind')
            if not isinstance(identifier, str) or not identifier or identifier in assets:
                raise ValueError(f'missing or duplicate asset id: {identifier!r}')
            if not isinstance(kind, str) or not kind:
                raise ValueError(f'{identifier}: kind must be a nonempty string')
            dependencies = row.get('depends_on', [])
            checks = row.get('checks', [])
            if not isinstance(dependencies, list) or any(
                not isinstance(item, str) for item in dependencies
            ):
                raise ValueError(f'{identifier}: depends_on must be a list of IDs')
            if not isinstance(checks, list) or any(not isinstance(item, dict) for item in checks):
                raise ValueError(f'{identifier}: checks must be a list of objects')
            assets[identifier] = Asset(
                identifier=identifier, kind=kind,
                path=__local_path(row.get('path'), path.parent),
                dependencies=tuple(dependencies), checks=tuple(checks),
            )
    for asset in assets.values():
        missing = set(asset.dependencies) - assets.keys()
        if missing:
            raise ValueError(f'{asset.identifier}: unknown dependencies {sorted(missing)}')
    for asset in assets.values():
        dependency_closure(asset.identifier, assets)  # Reject cyclic provenance, not iterative tasks.
    current = data.get('current', {})
    if not isinstance(current, dict) or any(
        not isinstance(name, str) or not isinstance(identifier, str) or identifier not in assets
        for name, identifier in current.items()
    ):
        raise ValueError('current must map names to registered asset IDs')
    return assets, current


def dependency_closure(identifier: str, assets: dict[str, Asset]) -> set[str]:
    '''Return a source/artifact lineage and reject a cyclic lineage.'''
    found: set[str] = set()
    visiting: set[str] = set()

    def visit(item: str) -> None:
        if item in visiting:
            raise ValueError(f'cyclic artifact dependency at {item}')
        if item in found:
            return
        visiting.add(item)
        for dependency in assets[item].dependencies:
            visit(dependency)
        visiting.remove(item)
        found.add(item)

    visit(identifier)
    return found


def __review_binding(
    check: dict[str, object], *, identifier: str, assets: dict[str, Asset],
    base: Path, verify: bool, digests: dict[Path, str],
) -> dict[str, object]:
    '''Test recorded evidence identity without inventing a reviewer conclusion.'''
    result: dict[str, object] = {
        'kind': check.get('kind'), 'declared_status': check.get('status'),
        'scope': check.get('scope'),
        'binding': 'not_rechecked', 'reusable': False,
    }
    if check.get('status') not in ACCEPTED_STATUSES:
        result['binding'] = 'not_accepted'
        return result
    evidence, report = check.get('inputs'), check.get('report')
    if not isinstance(evidence, dict) or not isinstance(report, dict):
        result['binding'] = 'unbound'
        return result
    required = dependency_closure(identifier, assets)
    if not required.issubset(evidence) or any(key not in assets for key in evidence):
        result['binding'] = 'incomplete_dependencies'
        return result
    expected = list(evidence.values()) + [report.get('sha256')]
    if any(not isinstance(value, str) or not DIGEST_PATTERN.fullmatch(value) for value in expected):
        result['binding'] = 'invalid_digest'
        return result
    report_path = __local_path(report.get('path'), base)
    paths = {key: assets[key].path for key in evidence}
    if report_path is None or not report_path.is_file() or any(
        value is None or not value.is_file() for value in paths.values()
    ):
        result['binding'] = 'missing_file'
        return result
    if not verify:
        return result

    def matches(file_path: Path, expected_digest: str) -> bool:
        if file_path not in digests:
            digests[file_path] = digest_file(file_path)
        return digests[file_path] == expected_digest.lower()

    for key, file_path in paths.items():
        assert file_path is not None
        if not matches(file_path, evidence[key]):
            result.update(binding='stale', changed_asset=key)
            return result
    if not matches(report_path, report['sha256']):
        result.update(binding='stale_report')
        return result
    # 🤖Identity can match while the legacy report's acceptance scope remains unknown.
    scoped = all(isinstance(check.get(key), str) and check[key].strip() for key in ('kind', 'scope'))
    result.update(binding='matched', reusable=scoped)
    if not scoped:
        result['reuse_limitation'] = 'Review kind/scope is missing; inspect the existing report before reuse.'
    return result


def inspect_project(
    path: Path, *, selected: list[str] | None = None, verify: bool = False,
) -> dict[str, object]:
    '''Inspect a selected lineage; missing optional manifests do not block publication.'''
    if not path.exists():
        return {'status': 'NOT_PRESENT', 'hint': 'Use the existing source and manuscript paths directly.'}
    assets, current = load_project(path)
    if verify and not selected:
        raise ValueError('--verify requires --artifact to avoid hashing a whole media library')
    identifiers = selected if selected else list(assets)
    unknown = set(identifiers) - assets.keys()
    if unknown:
        raise ValueError(f'unknown selected artifacts: {sorted(unknown)}')
    digests: dict[Path, str] = {}
    rows = []
    for identifier in identifiers:
        asset = assets[identifier]
        rows.append({
            'id': identifier, 'kind': asset.kind,
            'path': asset.path.as_posix() if asset.path else None,
            'available': asset.path.is_file() if asset.path else False,
            'depends_on': list(asset.dependencies),
            'checks': [__review_binding(
                check, identifier=identifier, assets=assets, base=path.parent,
                verify=verify, digests=digests,
            ) for check in asset.checks],
        })
    return {
        'status': 'INSPECTED', 'scope': 'Reference and hash binding only; not content acceptance.',
        'current': current, 'assets': rows,
    }


def main() -> int:
    '''Expose a read-only CLI with explicit verification scope.'''
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('manifest', type=Path)
    parser.add_argument('--artifact', action='append', dest='selected')
    parser.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    try:
        result = inspect_project(args.manifest.resolve(), selected=args.selected, verify=args.verify)
    except (OSError, ValueError, TypeError) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

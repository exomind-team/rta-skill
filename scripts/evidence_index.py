#!/usr/bin/env python3
'''Build or query an optional local index of source-linked text and image records.
- 🎯Reuse existing ASR/OCR/caption manifests without rerunning their producers.
- 📌This is literal keyword retrieval, not semantic matching or content approval.
- 🤖Agent-authored; no model, network, telemetry, or background process is started.
'''
from __future__ import annotations

import argparse
from bisect import bisect_left
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import tempfile
import unicodedata


INDEX_VERSION: int = 1
'''📌Version of this derived SQLite cache, independent from manuscript schemas.'''
DEFAULT_LIMIT: int = 5
'''📜Keep search output bounded for the calling Agent.'''
MAX_LIMIT: int = 50
'''📌A wider inspection must be split into deliberate queries.'''
HELD_STATES: frozenset[str] = frozenset({
    'excluded', 'hold', 'private_hold', 'retracted', 'superseded',
})
'''📌Held records remain indexed for explicit review but are hidden from ordinary queries.'''
DIGEST_PATTERN: re.Pattern[str] = re.compile(r'[0-9a-fA-F]{64}')
'''📌An optional asset digest must be a SHA-256 value.'''


def __normalize(text: str) -> str:
    '''Normalize only search keys, leaving source text and metadata untouched.'''
    return unicodedata.normalize('NFKC', text).casefold()


def __record(raw: object, *, base: Path, line: int) -> dict[str, object]:
    '''Check stable identity and a locator without fixing source kinds to a closed list.'''
    if not isinstance(raw, dict):
        raise ValueError(f'line {line}: expected an object')
    record = dict(raw)
    for key in ('id', 'source_id', 'kind'):
        if not isinstance(record.get(key), str) or not record[key]:
            raise ValueError(f'line {line}: missing nonempty {key}')
    locator = record.get('locator')
    if not isinstance(locator, dict) or not locator:
        raise ValueError(f'line {line}: locator must identify the source unit or source scope')
    for key in ('text', 'caption'):
        if key in record and not isinstance(record[key], str):
            raise ValueError(f'line {line}: {key} must be a string')
    status = record.setdefault('status', 'candidate')
    if not isinstance(status, str) or not status:
        raise ValueError(f'line {line}: status must be a nonempty string')
    if 'path' in record:
        value = record['path']
        if not isinstance(value, str) or not value or '://' in value:
            raise ValueError(f'line {line}: path must be local; keep URLs in a separate field')
        path = Path(value)
        record['path'] = (base / path).resolve().as_posix()
    digest = record.get('sha256')
    if digest is not None and (
        not isinstance(digest, str) or not DIGEST_PATTERN.fullmatch(digest)
    ):
        raise ValueError(f'line {line}: invalid asset SHA-256')
    return record


def build_index(records_path: Path, output: Path) -> dict[str, object]:
    '''Validate a staged cache and publish it without replacing an existing path.
    - 📌The input is explicit normalized JSONL; this never crawls a directory.
    - 🚩Publication uses a same-directory hard link for atomic no-replace semantics.
    '''
    if output.exists() or output.is_symlink():
        raise FileExistsError(f'index exists; choose a new cache path: {output.as_posix()}')
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f'.{output.name}.', dir=output.parent)
    os.close(descriptor)
    stage = Path(temporary)
    count = 0
    source_digest = hashlib.sha256()
    try:
        with closing(sqlite3.connect(stage)) as connection, connection:
            connection.execute(f'PRAGMA user_version = {INDEX_VERSION}')
            connection.execute(
                'CREATE TABLE evidence ('
                'id TEXT PRIMARY KEY, source_id TEXT NOT NULL, kind TEXT NOT NULL, '
                'status TEXT NOT NULL, search_text TEXT NOT NULL, payload TEXT NOT NULL)'
            )
            with records_path.open('rb') as stream:
                for line_number, raw_line in enumerate(stream, start=1):
                    source_digest.update(raw_line)
                    encoding = 'utf-8-sig' if line_number == 1 else 'utf-8'
                    line = raw_line.decode(encoding)
                    if not line.strip():
                        continue
                    record = __record(
                        json.loads(line), base=records_path.parent, line=line_number,
                    )
                    search_text = __normalize(
                        f'{record.get("text", "")} {record.get("caption", "")}'
                    )
                    try:
                        connection.execute(
                            'INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?)',
                            (record['id'], record['source_id'], record['kind'], record['status'],
                             search_text, json.dumps(record, ensure_ascii=False)),
                        )
                    except sqlite3.IntegrityError as exc:
                        raise ValueError(f'line {line_number}: duplicate id {record["id"]!r}') from exc
                    count += 1
            connection.execute('CREATE INDEX source_kind ON evidence (source_id, kind)')
        os.link(stage, output)  # Fails rather than overwriting a concurrent writer's output.
        return {
            'status': 'INDEXED', 'records': count, 'index': output.as_posix(),
            'records_sha256': source_digest.hexdigest(),
            'scope': 'Derived retrieval cache only; source assertions and review status are supplied metadata.',
        }
    finally:
        # Only this invocation's unique temporary file is owned here.
        stage.unlink(missing_ok=True)


def __asset_integrity(record: dict[str, object], *, verify: bool) -> str:
    '''Describe asset availability separately from supplied editorial acceptance.'''
    value = record.get('path')
    if not isinstance(value, str):
        return 'no_local_asset_reference'
    path = Path(value)
    if not path.is_file():
        return 'missing'
    if not verify:
        return 'available_not_rechecked'
    expected = record.get('sha256')
    if not isinstance(expected, str):
        return 'no_expected_digest'
    with path.open('rb') as stream:
        actual = hashlib.file_digest(stream, 'sha256').hexdigest()
    return 'matched' if actual == expected.lower() else 'stale'


def search_index(
    index: Path, *, query: str, source_id: str | None = None, kind: str | None = None,
    limit: int = DEFAULT_LIMIT, include_held: bool = False, verify: bool = False,
) -> dict[str, object]:
    '''Return bounded literal matches; a miss is not evidence that the source lacks content.'''
    if not 1 <= limit <= MAX_LIMIT:
        raise ValueError(f'limit must be between 1 and {MAX_LIMIT}')
    terms = list(dict.fromkeys(__normalize(query).split()))
    if not terms:
        raise ValueError('query must contain at least one literal term')
    if not index.exists():
        return {
            'status': 'NOT_PRESENT', 'matches': [],
            'hint': 'Use the actual sources directly; this optional cache is absent.',
        }
    # 📌Read-only mode avoids creating a database or journal while querying.
    with closing(sqlite3.connect(f'{index.resolve().as_uri()}?mode=ro', uri=True)) as connection:
        if connection.execute('PRAGMA user_version').fetchone()[0] != INDEX_VERSION:
            raise ValueError('unsupported evidence-index version; rebuild or use sources directly')
        clauses: list[str] = []
        values: list[str] = []
        for column, value in (('source_id', source_id), ('kind', kind)):
            if value is not None:
                clauses.append(f'{column} = ?')
                values.append(value)
        sql = 'SELECT id, status, search_text, payload FROM evidence'
        if clauses:
            sql += ' WHERE ' + ' AND '.join(clauses)
        best_keys: list[tuple[int, str]] = []
        best_records: list[dict[str, object]] = []
        total_matches = 0
        for identifier, status, text, payload in connection.execute(sql, values):
            if not include_held and status in HELD_STATES:
                continue
            if all(term in text for term in terms):
                record = json.loads(payload)
                occurrences = sum(text.count(term) for term in terms)
                total_matches += 1
                rank = (-occurrences, identifier)
                position = bisect_left(best_keys, rank)
                if position < limit:
                    best_keys.insert(position, rank)
                    best_records.insert(position, record)
                    if len(best_keys) > limit:
                        best_keys.pop()
                        best_records.pop()
    matches = []
    for (negative_occurrences, _), record in zip(best_keys, best_records):
        matches.append({
            **record, 'asset_integrity': __asset_integrity(record, verify=verify),
            'literal_match': {'terms': terms, 'occurrences': -negative_occurrences},
        })
    return {
        'status': 'SEARCHED', 'matches': matches, 'total_matches': total_matches,
        'scope': 'Literal retrieval candidates, not semantic confidence, source completeness, or figure approval.',
    }


def main() -> int:
    '''Run an explicitly requested build or a read-only query.'''
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build')
    build.add_argument('--records', type=Path, required=True)
    build.add_argument('--output', type=Path, required=True)
    search = commands.add_parser('search')
    search.add_argument('--index', type=Path, required=True)
    search.add_argument('--query', required=True)
    search.add_argument('--source', dest='source_id')
    search.add_argument('--kind')
    search.add_argument('--limit', type=int, default=DEFAULT_LIMIT)
    search.add_argument('--include-held', action='store_true')
    search.add_argument('--verify', action='store_true')
    args = parser.parse_args()
    try:
        if args.command == 'build':
            result = build_index(args.records.resolve(), args.output.resolve())
        else:
            result = search_index(
                args.index.resolve(), query=args.query, source_id=args.source_id,
                kind=args.kind, limit=args.limit, include_held=args.include_held, verify=args.verify,
            )
    except (OSError, ValueError, sqlite3.Error) as exc:
        print(f'{type(exc).__name__}: {exc}', file=sys.stderr)
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())

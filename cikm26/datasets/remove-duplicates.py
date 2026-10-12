#!/usr/bin/env python3
"""Remove near-duplicate documents from a documents.jsonl.gz.

Documents connected by a path of pairs with similarity >= threshold (default:
s3 >= 0.9) in near-duplicates.jsonl form one cluster. The document with the
smallest doc_id (sorted alphanumerically) is the representative of its
cluster. If documents.jsonl.gz contains non-representative cluster members, it
is copied to documents.jsonl.gz-backup and rewritten with only the
representatives (plus all documents that are in no cluster).

Example:
    python3 remove-duplicates.py \
        --documents in-progress/retrieval-hessian-law-de/documents.jsonl.gz \
        --near-duplicates ../near-duplicate-detection/output/hessian-law-de/near-duplicates.jsonl
"""
import argparse
import gzip
import json
import os
import shutil
import sys


def find(parent, x):
    root = x
    while parent[root] != root:
        root = parent[root]
    while parent[x] != root:
        parent[x], x = root, parent[x]
    return root


def build_clusters(near_duplicates_file, similarity, threshold):
    """Returns a dict mapping each clustered doc id to its cluster representative."""
    parent = {}
    with open(near_duplicates_file, 'rt', encoding='utf-8') as f:
        for line in f:
            if not line.strip():
                continue
            for pair in json.loads(line)['similarities']:
                score = pair['similarities'].get(similarity)
                if score is None:
                    raise ValueError(f'Pair without "{similarity}" similarity: {pair}')
                if score < threshold:
                    continue
                a, b = pair['firstId'], pair['secondId']
                parent.setdefault(a, a)
                parent.setdefault(b, b)
                ra, rb = find(parent, a), find(parent, b)
                if ra != rb:
                    # Attach the larger root to the smaller one, so that the root is always the minimum id.
                    if ra < rb:
                        parent[rb] = ra
                    else:
                        parent[ra] = rb
    return {doc_id: find(parent, doc_id) for doc_id in parent}


def read_doc_ids(documents_file):
    ids = set()
    with gzip.open(documents_file, 'rt', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                ids.add(json.loads(line)['doc_id'])
    return ids


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--documents', required=True, help='Path to documents.jsonl.gz (modified in place).')
    parser.add_argument('--near-duplicates', required=True, help='Path to near-duplicates.jsonl.')
    parser.add_argument('--similarity', default='s3', help='Similarity to use (default: s3).')
    parser.add_argument('--threshold', type=float, default=0.9, help='Minimum similarity for equivalence (default: 0.9).')
    args = parser.parse_args()

    representative = build_clusters(args.near_duplicates, args.similarity, args.threshold)
    representatives = set(representative.values())
    print(f'{len(representative)} documents in {len(representatives)} clusters '
          f'({args.similarity} >= {args.threshold}).')

    doc_ids = read_doc_ids(args.documents)
    missing = sorted(r for r in representatives if r not in doc_ids)
    if missing:
        sys.exit(f'ERROR: {len(missing)} representative documents are not in {args.documents}, '
                 f'e.g., {missing[:5]}. Nothing was changed.')

    to_remove = {d for d in doc_ids if d in representative and representative[d] != d}
    if not to_remove:
        print('No non-representative near-duplicates in the documents, nothing to do.')
        return

    backup = args.documents + '-backup'
    if os.path.exists(backup):
        sys.exit(f'ERROR: {backup} already exists, refusing to overwrite it. Nothing was changed.')
    shutil.copy2(args.documents, backup)

    tmp = args.documents + '.tmp'
    kept = 0
    with gzip.open(args.documents, 'rt', encoding='utf-8') as src, gzip.open(tmp, 'wt', encoding='utf-8') as dst:
        for line in src:
            if not line.strip():
                continue
            if json.loads(line)['doc_id'] in to_remove:
                continue
            dst.write(line if line.endswith('\n') else line + '\n')
            kept += 1
    os.replace(tmp, args.documents)
    print(f'Removed {len(to_remove)} documents, kept {kept}. Backup: {backup}')


if __name__ == '__main__':
    main()

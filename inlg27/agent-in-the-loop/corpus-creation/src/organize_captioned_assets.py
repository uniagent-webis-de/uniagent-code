"""Keep only flattened caption images in final; archive extraction artifacts losslessly."""

import csv
import json
import logging
import os
from pathlib import Path
import re
import shutil
import sys

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.corpus_paths import PROJECT_ROOT, FINAL_DIR, document_pdf_path
from src.extract_captioned_assets import checksum, copy_addition, commit_indexes, read_jsonl, write_json, write_jsonl

METADATA = ('figures_tables_assets.jsonl', 'figures_tables_extraction.json',
            'figures_tables_unmatched_captions.jsonl')


def archive_dir(paper, *, project_root=PROJECT_ROOT):
    """Mirror a final document's task/paper hierarchy under intermediate."""
    return project_root / 'data/intermediate/figures-tables' / paper.relative_to(project_root / 'data/final')


def organize_document(paper, archive, *, project_root):
    """Archive old trees, promote only complete caption images, and retain a retry journal.

    Paths in intermediate asset metadata are relative to the corpus-builder root.
    The previous tree is byte-preserved, including its original metadata.
    """
    journal = archive / 'layout.json'
    previous = archive / 'previous'
    staged = archive / 'staged'
    relative = lambda path: path.relative_to(project_root).as_posix()
    if journal.exists():
        plan = json.loads(journal.read_text())
    else:
        rows = read_jsonl(paper / METADATA[0])
        old = {p.relative_to(paper).as_posix(): checksum(p)
               for folder in ('figures', 'tables') for p in (paper / folder).rglob('*') if p.is_file()}
        old.update({name: checksum(paper / name) for name in METADATA})
        images = {}
        for row in rows:
            source = Path(row['caption_image'])
            if source.is_absolute() or '..' in source.parts or source.suffix.lower() != '.png':
                raise ValueError(f'invalid caption image: {source}')
            target = Path('figures' if row['kind'] == 'figure' else 'tables') / source.name
            if target.as_posix() in images:
                raise ValueError(f'duplicate caption filename: {target}')
            images[target.as_posix()] = source.as_posix()
        plan = dict(old=old, images=images, complete=False)
        write_json(journal, plan)
    moved = {relative(paper / name): relative(previous / name) for name in plan['old']}
    fields = dict(figures_tables_assets_path=relative(archive / METADATA[0]),
                  n_figures=sum(name.startswith('figures/') for name in plan['images']),
                  n_tables=sum(name.startswith('tables/') for name in plan['images']))
    fields['n_table_images'] = fields['n_tables']
    if plan['complete']:
        verify_document(paper, archive, plan, project_root=project_root)
        return fields, moved

    # Keep metadata accessible even if a process stops between directory promotions.
    for name in METADATA:
        if (paper / name).exists():
            copy_addition(paper / name, previous / name)
    rows = read_jsonl(previous / METADATA[0])
    for folder in ('figures', 'tables'):
        (staged / folder).mkdir(parents=True, exist_ok=True)
    for target, source in plan['images'].items():
        saved = previous / source
        copy_addition(saved if saved.exists() else paper / source, staged / target)
    for row in rows:
        source = row['caption_image']
        target = next(name for name, old in plan['images'].items() if old == source)
        row['caption_image'] = relative(paper / target)
        row['original_image'] = relative(previous / row['original_image'])
        for fragment in row.get('fragments', []):
            fragment['image'] = (relative(paper / target) if fragment['image'] == source else
                                 relative(previous / fragment['image']))
    write_jsonl(archive / METADATA[0], rows)
    for name in METADATA[1:]:
        copy_addition(previous / name, archive / name)
    try:
        for folder in ('figures', 'tables'):
            destination, saved = paper / folder, previous / folder
            if not saved.exists():
                if destination.exists():
                    destination.rename(saved)
                else:
                    saved.mkdir(parents=True)
            if not destination.exists():
                (staged / folder).rename(destination)
        verify_document(paper, archive, plan, project_root=project_root)
    except BaseException:
        for folder in ('figures', 'tables'):
            if (previous / folder).exists():
                if (paper / folder).exists():
                    shutil.rmtree(paper / folder)
                (previous / folder).rename(paper / folder)
        raise
    for name in METADATA:
        (paper / name).unlink(missing_ok=True)
    plan['complete'] = True
    write_json(journal, plan)
    if staged.exists():
        shutil.rmtree(staged)
    return fields, moved


def verify_document(paper, archive, plan, *, project_root):
    """Prove old bytes survive and final contains exactly one PNG per asset."""
    for name, digest in plan['old'].items():
        if checksum(archive / 'previous' / name) != digest:
            raise RuntimeError(f'archived file changed: {name}')
    actual = {p.relative_to(paper).as_posix() for folder in ('figures', 'tables')
              for p in (paper / folder).rglob('*')}
    if actual != set(plan['images']):
        raise RuntimeError(f'final image layout differs: {paper}')
    for target, source in plan['images'].items():
        if checksum(paper / target) != plan['old'][source]:
            raise RuntimeError(f'caption image changed: {paper / target}')
    for row in read_jsonl(archive / METADATA[0]):
        for name in [row['caption_image'], row['original_image']] + [f['image'] for f in row.get('fragments', [])]:
            if not (project_root / name).is_file():
                raise FileNotFoundError(name)


def repair_markdown_links(paper, archive, moved, *, project_root):
    """Retarget local image links while preserving the original parsed text in intermediate."""
    count = 0
    for markdown in paper.glob('*.txt.md'):
        saved = archive / 'previous' / markdown.name
        original = markdown.read_text()

        def replace(match):
            nonlocal count
            target = match.group('target')
            if '://' in target or target.startswith('data:'):
                return match.group(0)
            source = (paper / target).resolve()
            if not source.is_relative_to(project_root):
                return match.group(0)
            destination = moved.get(source.relative_to(project_root).as_posix())
            if destination is None:
                return match.group(0)
            count += 1
            return match.group('prefix') + os.path.relpath(project_root / destination, paper)

        text = original
        for pattern in (r'(?P<prefix>!?\[[^\]]*\]\(\s*<?)(?P<target>[^\s)>]+)',
                        r'''(?P<prefix><img\b[^>]*?\bsrc=["'])(?P<target>[^"']+)'''):
            text = re.sub(pattern, replace, text)
        if text != original:
            if not saved.exists():
                copy_addition(markdown, saved)
            temporary = markdown.with_name(markdown.name + '.caption-tmp')
            temporary.write_text(text, encoding='utf-8')
            temporary.replace(markdown)
    return count


def organize_corpus():
    """Migrate the current indexed corpus and transactionally repair its metadata links."""
    from src.build_corpus import validate, validate_output_files, validate_final_task_directories
    logger = logging.getLogger(__name__)
    root = PROJECT_ROOT / 'data/intermediate/figures-tables'
    root.mkdir(parents=True, exist_ok=True)
    tasks = read_jsonl(FINAL_DIR / 'shared_tasks.jsonl')
    # Snapshot indexes before changing any document, including on a retried run.
    backup = root / 'index-before-layout'
    backup.mkdir(exist_ok=True)
    for name in ['manifest.jsonl', 'shared_tasks.jsonl', 'shared_tasks.csv', 'shared_tasks_summary.csv'] + [
            f"{task['task_id']}/metadata.json" for task in tasks]:
        target = backup / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            shutil.copy2(FINAL_DIR / name, target)
    fields_by_key, moved = {}, {}
    repaired_links = 0
    for index, task in enumerate(tasks):
        for role, doc in [('overview', task['overview'])] + [('participant', p) for p in task['participants']]:
            paper = document_pdf_path(task['task_id'], role, doc['pdf_url']).parent
            fields, paths = organize_document(paper, archive_dir(paper, project_root=PROJECT_ROOT), project_root=PROJECT_ROOT)
            fields_by_key[(task['task_id'], doc['pdf_url'])] = fields
            moved.update(paths)
            repaired_links += repair_markdown_links(paper, archive_dir(paper, project_root=PROJECT_ROOT),
                                                     paths, project_root=PROJECT_ROOT)
        if index % 25 == 0:
            logger.info('Organized %d/%d tasks', index + 1, len(tasks))

    def update(value):
        if isinstance(value, dict):
            return {key: update(item) for key, item in value.items()}
        if isinstance(value, list):
            return [update(item) for item in value]
        return moved.get(value, value) if isinstance(value, str) else value

    updates = {}
    for task in tasks:
        for doc in [task['overview'], *task['participants']]:
            doc.update(fields_by_key[(task['task_id'], doc['pdf_url'])])
        # Only file references change outside the asset counts and metadata location.
        revised = update(task)
        task.clear()
        task.update(revised)
        path = FINAL_DIR / task['task_id'] / 'metadata.json'
        metadata = update(json.loads(path.read_text()))
        for doc in [metadata['overview'], *metadata['participants']]:
            doc.update(fields_by_key[(task['task_id'], doc['pdf_url'])])
        if metadata['overview'] != task['overview'] or metadata['participants'] != task['participants']:
            raise RuntimeError(f"task/main metadata disagree: {task['task_id']}")
        updates[path] = (json.dumps(metadata, ensure_ascii=False, indent=2) + '\n').encode()
    manifest = update(read_jsonl(FINAL_DIR / 'manifest.jsonl'))
    for record in manifest:
        record.update(fields_by_key.get((record['task_id'], record['pdf_url']), {}))
    for name, rows in [('shared_tasks.jsonl', tasks), ('manifest.jsonl', manifest)]:
        updates[FINAL_DIR / name] = ''.join(json.dumps(row, ensure_ascii=False) + '\n' for row in rows).encode()
    if not (validate(tasks, logger) and validate_output_files(tasks, logger) and validate_final_task_directories(tasks, logger)):
        raise RuntimeError('builder validation failed')
    ids = {task['task_id'] for task in tasks}
    for name in ['shared_tasks.csv', 'shared_tasks_summary.csv']:
        with (FINAL_DIR / name).open() as stream:
            if {row['task_id'] for row in csv.DictReader(stream)} != ids:
                raise RuntimeError(f'CSV task IDs disagree: {name}')
    commit_indexes(updates, root / 'index-commit-backup')
    for report in FINAL_DIR.glob('figures_tables_extraction_report.*'):
        copy_addition(report, root / report.name)
        report.unlink()
    summary = dict(tasks=len(tasks), documents=len(fields_by_key),
                   figures=sum(f['n_figures'] for f in fields_by_key.values()),
                   tables=sum(f['n_tables'] for f in fields_by_key.values()),
                   archived_files=len(moved), repaired_markdown_image_links=repaired_links,
                   status='passed', metadata_paths_relative_to='corpus-creation')
    write_json(root / 'layout-report.json', summary)
    logger.info('Layout migration passed: %s', summary)
    return summary


def main():
    (PROJECT_ROOT / 'logs').mkdir(exist_ok=True)
    logging.basicConfig(filename=PROJECT_ROOT / 'logs/organize_captioned_assets.log', filemode='w',
                        level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    try:
        organize_corpus()
    except BaseException:
        logging.exception('Layout migration failed; originals retained in intermediate/figures-tables')
        raise


if __name__ == '__main__':
    main()

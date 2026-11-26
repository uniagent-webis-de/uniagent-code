import json
from pathlib import Path

import pytest
from PIL import Image


def fixture_document(root):
    paper = root / 'data/final/task/papers/paper'
    folder = paper / 'tables/with_captions'
    (folder / 'originals').mkdir(parents=True)
    for name, color in [('tables/old.png', 'red'),
                        ('tables/with_captions/caption.png', 'blue'),
                        ('tables/with_captions/part.png', 'green'),
                        ('tables/with_captions/originals/original.png', 'yellow')]:
        Image.new('RGB', (8, 8), color).save(paper / name)
    (paper / 'figures').mkdir()
    (paper / 'tables/table.md').write_text('old table')
    row = dict(kind='table', caption='Table 1: test', page=1, pages=[1, 2],
               source_pdf='data/final/task/papers/paper/paper.pdf',
               caption_image='tables/with_captions/caption.png',
               original_image='tables/with_captions/originals/original.png',
               fragments=[dict(image='tables/with_captions/part.png', page=2)])
    for name, value in [('figures_tables_assets.jsonl', row),
                        ('figures_tables_extraction.json', dict(status='ok', review_required=True)),
                        ('figures_tables_unmatched_captions.jsonl', dict(caption='unmatched'))]:
        (paper / name).write_text(json.dumps(value) + '\n')
    return paper


def test_flatten_preserves_every_old_file_and_resolves_metadata_paths(tmp_path):
    from src.organize_captioned_assets import organize_document
    paper = fixture_document(tmp_path)
    originals = {p.relative_to(paper): p.read_bytes() for p in paper.rglob('*') if p.is_file()}
    archive = tmp_path / 'data/intermediate/figures-tables/task/papers/paper'
    fields, moved = organize_document(paper, archive, project_root=tmp_path)
    assert list((paper / 'figures').iterdir()) == []
    assert [p.name for p in (paper / 'tables').iterdir()] == ['caption.png']
    assert not list(paper.glob('figures_tables*'))
    for relative, content in originals.items():
        assert (archive / 'previous' / relative).read_bytes() == content
    row = json.loads((archive / 'figures_tables_assets.jsonl').read_text())
    assert row['caption'] == 'Table 1: test'
    assert row['pages'] == [1, 2]
    assert row['caption_image'] == 'data/final/task/papers/paper/tables/caption.png'
    for path in [row['caption_image'], row['original_image'], row['fragments'][0]['image']]:
        assert (tmp_path / path).is_file()
    assert fields['n_tables'] == fields['n_table_images'] == 1
    assert fields['figures_tables_assets_path'].startswith('data/intermediate/')
    assert (tmp_path / moved['data/final/task/papers/paper/tables/old.png']).is_file()
    assert organize_document(paper, archive, project_root=tmp_path) == (fields, moved)


def test_failure_restores_original_directories_and_can_retry(tmp_path, monkeypatch):
    from src.organize_captioned_assets import organize_document
    paper = fixture_document(tmp_path)
    archive = tmp_path / 'data/intermediate/figures-tables/task/papers/paper'
    rename = Path.rename
    def fail(path, target):
        if path == archive / 'staged/tables':
            raise OSError('injected promotion failure')
        return rename(path, target)
    with monkeypatch.context() as patch:
        patch.setattr(Path, 'rename', fail)
        with pytest.raises(OSError, match='injected promotion failure'):
            organize_document(paper, archive, project_root=tmp_path)
    assert (paper / 'tables/old.png').exists()
    assert (paper / 'tables/with_captions/caption.png').exists()
    assert (paper / 'figures_tables_assets.jsonl').exists()
    organize_document(paper, archive, project_root=tmp_path)
    assert (paper / 'tables/caption.png').exists()


def test_corpus_updates_indexes_and_can_repeat_without_changing_content(tmp_path, monkeypatch):
    from src import organize_captioned_assets as organizer, corpus_paths, build_corpus
    paper = fixture_document(tmp_path)
    final = tmp_path / 'data/final'
    overview = final / 'task/overview'
    import shutil
    shutil.copytree(paper, overview)
    for directory, name in [(paper, 'paper'), (overview, 'overview')]:
        (directory / f'{name}.pdf').write_bytes(b'PDF unchanged')
        (directory / f'{name}.txt.md').write_text('Text unchanged')
    docs = [dict(pdf_url='https://example.org/overview.pdf', title='Overview'),
            dict(pdf_url='https://example.org/paper.pdf', title='Paper')]
    task = dict(task_id='task', overview=docs[0], participants=docs[1:], counts=dict(coverage_ratio=None))
    (final / 'task/metadata.json').write_text(json.dumps(task))
    (final / 'shared_tasks.jsonl').write_text(json.dumps(task) + '\n')
    (final / 'manifest.jsonl').write_text(''.join(json.dumps(dict(task_id='task', **doc,
        pdffigures2_files=['data/final/task/papers/paper/tables/old.png'])) + '\n' for doc in docs))
    for filename in ['shared_tasks.csv', 'shared_tasks_summary.csv']:
        (final / filename).write_text('task_id\ntask\n')
    monkeypatch.setattr(organizer, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(organizer, 'FINAL_DIR', final)
    monkeypatch.setattr(corpus_paths, 'FINAL_DIR', final)
    monkeypatch.setattr(build_corpus, 'FINAL_DIR', final)
    first = organizer.organize_corpus()
    assert first['documents'] == 2
    assert first['tables'] == 2
    revised = json.loads((final / 'shared_tasks.jsonl').read_text())
    assert revised['participants'][0]['n_tables'] == 1
    assert revised == json.loads((final / 'task/metadata.json').read_text())
    for doc in revised['participants'] + [revised['overview']]:
        assert (tmp_path / doc['figures_tables_assets_path']).exists()
    manifest = [json.loads(line) for line in (final / 'manifest.jsonl').read_text().splitlines()]
    assert all((tmp_path / row['pdffigures2_files'][0]).exists() for row in manifest)
    assert organizer.organize_corpus() == first
    assert (paper / 'paper.pdf').read_bytes() == b'PDF unchanged'


def test_old_extractor_reuses_organized_caption_images(tmp_path, monkeypatch):
    from src import extract_figs_tbls as extractor
    paper = tmp_path / 'data/final/task/overview'
    paper.mkdir(parents=True)
    (paper / 'overview.pdf').write_bytes(b'pdf')
    metadata = tmp_path / 'data/intermediate/figures-tables/task/overview/figures_tables_assets.jsonl'
    metadata.parent.mkdir(parents=True)
    metadata.write_text('')
    previous = dict(figures_tables_assets_path=str(metadata.relative_to(tmp_path)),
                    figures_tables_status='ok', n_captioned_figures=0, n_captioned_tables=0)
    monkeypatch.setattr(extractor, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(extractor, 'document_pdf_path', lambda *args: paper / 'overview.pdf')
    monkeypatch.setattr(extractor, 'document_figures_dir', lambda *args: paper / 'figures')
    monkeypatch.setattr(extractor, 'document_tables_dir', lambda *args: paper / 'tables')
    def forbidden(*args, **kwargs):
        pytest.fail('old extractor must not replace captioned assets')
    monkeypatch.setattr(extractor, 'apply_reviewed_assets', forbidden)
    import logging
    result = extractor.process_document('task', 'overview', 'url', previous,
        pdffigures2_dir=tmp_path, jar=None, dpi=150, image_format='png', logger=logging.getLogger('test'))
    assert result['n_figures'] == result['n_tables'] == 0


def test_text_refresh_preserves_final_caption_counts():
    from src.parse_fulltext import preserve_extractor_fields
    previous = dict(figures_tables_assets_path='data/intermediate/figures-tables/task/overview/figures_tables_assets.jsonl',
                    n_figures=3, n_tables=2, n_table_images=2)
    result = preserve_extractor_fields(dict(n_figures=0, n_tables=0, n_table_images=0), previous)
    assert result['n_figures'] == 3
    assert result['n_tables'] == result['n_table_images'] == 2


def test_reparsed_text_assets_stay_out_of_final_image_folders(tmp_path, monkeypatch):
    import logging
    from src import parse_fulltext as parser, corpus_corrections
    paper = tmp_path / 'data/final/task/overview'
    paper.mkdir(parents=True)
    pdf = paper / 'overview.pdf'
    pdf.write_bytes(b'pdf')
    archive = tmp_path / 'data/intermediate/figures-tables/task/overview'
    archive.mkdir(parents=True)
    (archive / 'layout.json').write_text('{}')
    (tmp_path / 'fulltext_corrections.json').write_text('{}')
    monkeypatch.setattr(parser, 'PROJECT_ROOT', tmp_path)
    monkeypatch.setattr(corpus_corrections, 'CURATION_DIR', tmp_path)
    monkeypatch.setattr(parser, 'document_pdf_path', lambda *args: pdf)
    monkeypatch.setattr(parser, 'document_markdown_path', lambda *args: paper / 'overview.txt.md')
    monkeypatch.setattr(parser, 'document_figures_dir', lambda *args: paper / 'figures')
    monkeypatch.setattr(parser, 'document_tables_dir', lambda *args: paper / 'tables')
    monkeypatch.setattr(parser, 'probe_pdf', lambda *args: (1, False))
    def parse(pdf_path, out_path, ocr_url, language, logger, figures_dir):
        assert figures_dir == archive / 'text-assets/figures'
        out_path.write_text('text ' * 1000)
        return True
    def tables(text, tables_dir, pdf_path, logger):
        assert tables_dir == archive / 'text-assets/tables'
        return 0, 0
    monkeypatch.setattr(parser, 'parse_document', parse)
    monkeypatch.setattr(parser, 'write_tables', tables)
    parser.process_document('task', 'overview', 'url', tmp_path, None, 'eng', logging.getLogger('test'))
    assert not list((paper / 'figures').iterdir())
    assert not list((paper / 'tables').iterdir())


def test_markdown_links_follow_archived_images_and_original_text_is_preserved(tmp_path):
    from src.organize_captioned_assets import organize_document, repair_markdown_links
    paper = fixture_document(tmp_path)
    markdown = paper / 'paper.txt.md'
    original = '# Source text\n![Old table](tables/old.png)\n![Missing already](figures/missing.png)\n'
    markdown.write_text(original)
    archive = tmp_path / 'data/intermediate/figures-tables/task/papers/paper'
    _, moved = organize_document(paper, archive, project_root=tmp_path)
    assert repair_markdown_links(paper, archive, moved, project_root=tmp_path) == 1
    assert (archive / 'previous/paper.txt.md').read_text() == original
    text = markdown.read_text()
    assert 'figures/missing.png' in text
    target = text.split('![Old table](')[1].split(')')[0]
    assert (paper / target).resolve() == archive / 'previous/tables/old.png'
    assert repair_markdown_links(paper, archive, moved, project_root=tmp_path) == 0
    assert markdown.read_text() == text


def test_link_repair_never_reverts_later_text_corrections(tmp_path):
    from src.organize_captioned_assets import organize_document, repair_markdown_links
    paper = fixture_document(tmp_path)
    markdown = paper / 'paper.txt.md'
    markdown.write_text('original ![table](tables/old.png)')
    archive = tmp_path / 'data/intermediate/figures-tables/task/papers/paper'
    _, moved = organize_document(paper, archive, project_root=tmp_path)
    repair_markdown_links(paper, archive, moved, project_root=tmp_path)
    markdown.write_text('UPDATED OCR CONTENT')
    repair_markdown_links(paper, archive, moved, project_root=tmp_path)
    assert markdown.read_text() == 'UPDATED OCR CONTENT'
    assert (archive / 'previous/paper.txt.md').read_text().startswith('original ')

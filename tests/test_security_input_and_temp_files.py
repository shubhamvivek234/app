"""Security controls use synthetic XML and owned temporary directories only."""
import os
from pathlib import Path

import pytest

from utils.clip_selector import parse_youtube_timed_text
from utils.rss_parser import parse_feed_xml


@pytest.mark.parametrize('declaration', [
    '<!DOCTYPE rss [<!ENTITY value "expanded-secret">]>',
    '<!DOCTYPE rss SYSTEM "file:///unreachable-synthetic-file">',
])
def test_feed_rejects_dtd_and_entities(declaration):
    with pytest.raises(ValueError):
        parse_feed_xml(declaration + '<rss><channel><title>Safe</title></channel></rss>')


def test_transcript_security_rejection_never_enters_regex_fallback():
    xml = '<!DOCTYPE transcript [<!ENTITY value "expanded-secret">]><transcript><text start="0" dur="1">ordinary</text><text start="1" dur="1">&value;</text></transcript>'
    assert parse_youtube_timed_text(xml) == []


def test_transcript_malformed_ordinary_xml_keeps_existing_fallback():
    assert parse_youtube_timed_text('<transcript><text start="0" dur="1">ordinary</text>')[0]['text'] == 'ordinary'


def test_quarantine_is_private_shared_and_exclusive(tmp_path):
    from utils.private_temp import create_quarantine_file
    base = tmp_path / 'shared-quarantine'
    file, path = create_quarantine_file(str(base), 'actor', 'owned.bin')
    with file:
        file.write(b'retry-evidence')
    assert Path(path).read_bytes() == b'retry-evidence'
    assert os.stat(base).st_mode & 0o777 == 0o700
    assert os.stat(base / 'actor').st_mode & 0o777 == 0o700
    assert os.stat(path).st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        create_quarantine_file(str(base), 'actor', 'owned.bin')
    assert Path(path).read_bytes() == b'retry-evidence'


@pytest.mark.parametrize('part', ['root', 'actor', 'file'])
def test_quarantine_rejects_symlinks_without_touching_target(tmp_path, part):
    from utils.private_temp import create_quarantine_file
    base = tmp_path / 'quarantine'
    target = tmp_path / 'untouched'
    if part == 'root':
        target.mkdir(); base.symlink_to(target, target_is_directory=True)
    elif part == 'actor':
        base.mkdir(); target.mkdir(); (base / 'actor').symlink_to(target, target_is_directory=True)
    else:
        (base / 'actor').mkdir(parents=True); target.write_bytes(b'original'); (base / 'actor' / 'owned.bin').symlink_to(target)
    with pytest.raises(OSError):
        create_quarantine_file(str(base), 'actor', 'owned.bin')
    assert target.read_bytes() == b'original' if part == 'file' else list(target.iterdir()) == []


def test_scratch_paths_are_distinct_private_files_without_user_path_components(tmp_path, monkeypatch):
    from utils import private_temp
    monkeypatch.setattr(private_temp.tempfile, 'tempdir', str(tmp_path))
    private_temp._scratch_root.cache_clear()
    first = Path(private_temp.private_scratch_path('.webp'))
    second = Path(private_temp.private_scratch_path('.webp'))
    assert first != second and first.parent == second.parent
    assert os.stat(first.parent).st_mode & 0o777 == 0o700
    assert os.stat(first).st_mode & 0o777 == 0o600
    first.unlink(); second.unlink(); first.parent.rmdir(); private_temp._scratch_root.cache_clear()

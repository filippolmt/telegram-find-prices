import logging
from pathlib import Path

from config import tighten_permissions


def _mode(p):
    return p.stat().st_mode & 0o777


def test_world_writable_dir_and_files_become_owner_only(tmp_path):
    (tmp_path / "db.sqlite3").touch(mode=0o777)
    (tmp_path / "bot_session.session").touch(mode=0o777)
    tmp_path.chmod(0o777)
    for p in tmp_path.iterdir():
        p.chmod(0o777)

    tighten_permissions(tmp_path)

    assert _mode(tmp_path) == 0o700
    assert all(_mode(p) == 0o600 for p in tmp_path.iterdir())


def test_chmod_permission_error_is_skipped_and_others_tightened(tmp_path, monkeypatch, caplog):
    locked, other = tmp_path / "locked", tmp_path / "other"
    for p in (locked, other):
        p.touch()
        p.chmod(0o777)
    real_chmod = Path.chmod

    def chmod(self, mode):
        if self == locked:
            raise PermissionError
        real_chmod(self, mode)

    monkeypatch.setattr(Path, "chmod", chmod)

    with caplog.at_level(logging.WARNING):
        tighten_permissions(tmp_path)

    assert "Cannot chmod" in caplog.text and str(locked) in caplog.text
    assert _mode(other) == 0o600


def test_already_owner_only_logs_nothing(tmp_path, caplog):
    tmp_path.chmod(0o700)
    (tmp_path / "db.sqlite3").touch(mode=0o600)

    with caplog.at_level(logging.WARNING):
        tighten_permissions(tmp_path)

    assert caplog.text == ""

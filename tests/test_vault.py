import json

import pytest

from snapshot_vault import load_verified, restore, snapshot


@pytest.fixture
def setup(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "a.txt").write_text("hello")
    (source / "nested").mkdir()
    (source / "nested/b.txt").write_text("hello")
    return source, tmp_path / "vault", tmp_path / "restored"


def test_roundtrip_dedup(setup):
    source, vault, dest = setup
    identifier = snapshot(source, vault)
    assert len(list((vault / "objects").iterdir())) == 1
    assert restore(vault, identifier, dest) == 2
    assert (dest / "nested/b.txt").read_text() == "hello"
    assert len(load_verified(vault, identifier)) == 2


def test_changed_file(setup):
    source, vault, dest = setup
    first = snapshot(source, vault)
    (source / "a.txt").write_text("changed")
    snapshot(source, vault)
    restore(vault, first, dest)
    assert (dest / "a.txt").read_text() == "hello"
    assert len(list((vault / "objects").iterdir())) == 2


def test_corruption(setup):
    source, vault, dest = setup
    identifier = snapshot(source, vault)
    next((vault / "objects").iterdir()).write_bytes(b"broken")
    with pytest.raises(ValueError):
        restore(vault, identifier, dest)
    assert not dest.exists()


def test_traversal(setup):
    source, vault, dest = setup
    identifier = snapshot(source, vault)
    file = vault / "snapshots" / f"{identifier}.json"
    data = json.loads(file.read_text())
    data["files"][0]["path"] = "../escaped"
    file.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        restore(vault, identifier, dest)


def test_refuses_overwrite(setup):
    source, vault, dest = setup
    identifier = snapshot(source, vault)
    dest.mkdir()
    with pytest.raises(ValueError):
        restore(vault, identifier, dest)


def test_refuses_nested_vault(setup):
    source, _, _ = setup
    with pytest.raises(ValueError):
        snapshot(source, source / "vault")


def test_symlink(setup):
    source, vault, _ = setup
    (source / "link").symlink_to(source / "a.txt")
    with pytest.raises(ValueError):
        snapshot(source, vault)

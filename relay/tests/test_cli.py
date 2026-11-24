import json

import pytest

from relay.service import cli
from relay.service.store import Store


def test_show_and_approve_a_hash_then_refuse_unknown(tmp_path, capsys):
    db = tmp_path / "t.sqlite3"
    clave = Store(db).request_approval("practica", "http://127.0.0.1/f", {"nombre": "Ana"})
    assert cli.main(["--bd", str(db), "show", clave]) == 0
    assert json.loads(capsys.readouterr().out)["contenido"] == {"nombre": "Ana"}
    assert cli.main(["--bd", str(db), "approve", clave]) == 0
    with pytest.raises(SystemExit):
        cli.main(["--bd", str(db), "approve", clave])  # already approved: not waiting anymore
    with pytest.raises(SystemExit):
        cli.main(["--bd", str(db), "approve", "0" * 64])


def test_token_is_created_private_and_reused(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "TOKEN_FILE", tmp_path / "relay" / "token")
    cli.main(["token"])
    first = capsys.readouterr().out.strip()
    cli.main(["token"])
    assert capsys.readouterr().out.strip() == first and len(first) >= 16
    assert (tmp_path / "relay" / "token").stat().st_mode & 0o077 == 0

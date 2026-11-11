"""CLI verify exit codes (0 clean / 1 findings / 2 input error)."""

import json

from subgrant import cli

from .helpers import base_chain


def _write(tmp_path, name, doc):
    p = tmp_path / name
    p.write_text(json.dumps(doc), encoding="utf-8")
    return str(p)


def test_verify_clean_exit_0(tmp_path, capsys):
    path = _write(tmp_path, "clean.json", base_chain())
    assert cli.main(["verify", path]) == 0
    assert "OK" in capsys.readouterr().out


def test_verify_findings_exit_1(tmp_path, capsys):
    d = base_chain()
    d["edges"][1]["authority"]["tools"] = ["tool.read", "tool.write"]
    path = _write(tmp_path, "amp.json", d)
    assert cli.main(["verify", path]) == 1
    assert "D1" in capsys.readouterr().out


def test_verify_input_error_exit_2(tmp_path, capsys):
    d = base_chain()
    d["edges"][1]["parent_edge"] = "e999"  # dangling
    path = _write(tmp_path, "bad.json", d)
    assert cli.main(["verify", path]) == 2
    assert "schema error" in capsys.readouterr().err


def test_verify_bad_json_exit_2(tmp_path, capsys):
    p = tmp_path / "x.json"
    p.write_text("{not json", encoding="utf-8")
    assert cli.main(["verify", str(p)]) == 2


def test_verify_json_flag(tmp_path, capsys):
    d = base_chain()
    d["edges"][1]["authority"]["tools"] = ["tool.read", "tool.write"]
    path = _write(tmp_path, "amp.json", d)
    cli.main(["verify", path, "--json"])
    out = json.loads(capsys.readouterr().out)
    assert out == [{"class": "D1", "edge": "e2"}]


def test_report_exit_0_and_json(tmp_path, capsys):
    path = _write(tmp_path, "clean.json", base_chain())
    assert cli.main(["report", path]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["schema"] == "subgrant-evidence/1"
    assert out["entries"][0]["type"] == "header"

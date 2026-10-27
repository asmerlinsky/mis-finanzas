import random
from pathlib import Path

import pytest

from mis_finanzas.tools.redact import main
from mis_finanzas.tools.redact_csv import redact_csv_file
from mis_finanzas.tools.redaction import LeakError

NAME = "Juana Pérez"
CSV = (
    "FECHA;DESCRIPCION;MONTO;SALDO\n"
    "2026-10-27T12:30:00.000-03:00;Transferencia de Pérez, Juana CVU 0000003100012345678901;"
    "-1.234,56;10.000,00\n"
    "28-10-2026;Pago QR Kiosco;-500,00;9.500,00\n"
)


def test_csv_keeps_delimiter_dates_and_shapes(tmp_path: Path) -> None:
    source = tmp_path / "mp.csv"
    source.write_text(CSV, encoding="utf-8")
    target = tmp_path / "out.csv"
    redact_csv_file(source, target, [NAME], random.Random(1))
    lines = target.read_text(encoding="utf-8").splitlines()
    assert lines[0] == "FECHA;DESCRIPCION;MONTO;SALDO"
    first = lines[1].split(";")
    assert first[0] == "2026-10-27T12:30:00.000-03:00"
    assert first[1].startswith("Transferencia de XXXX, XXXX CVU ")
    assert "0000003100012345678901" not in lines[1]
    assert len(first[2]) == len("-1.234,56") and first[2][-3] == ","
    assert lines[2].startswith("28-10-2026;Pago QR Kiosco;")


def test_csv_run_together_name_blocks_output(tmp_path: Path) -> None:
    source = tmp_path / "mp.csv"
    source.write_text("A;B\nx;SraJuanaPerez\n", encoding="utf-8")
    with pytest.raises(LeakError):
        redact_csv_file(source, tmp_path / "out.csv", [NAME], random.Random(2))
    assert not (tmp_path / "out.csv").exists()


def test_cli_csv(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "mp.csv").write_text(CSV, encoding="cp1252")
    assert main(["mp.csv", "--name", NAME]) == 0
    assert (tmp_path / "samples" / "mp.redacted.csv").read_text(encoding="cp1252").count(";") == 9

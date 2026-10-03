from refurbpass.collectors.system import SystemInfo
from refurbpass.report.pdf import ReportGenerator, build_qr
from refurbpass.scoring import calculate_score


def _health():
    return calculate_score(0.62, 0.95, None, details={"battery": "31000 mWh sur 50000 mWh"},
                           disk_issues=["Disque test : 12 secteurs réalloués, à surveiller"])


def test_pdf_is_written(tmp_path):
    out = tmp_path / "sous-dossier" / "rapport.pdf"
    ReportGenerator("Atelier Test").generate(SystemInfo(model="Test"), _health(), str(out))
    assert out.read_bytes().startswith(b"%PDF")


def test_special_characters_do_not_break_pdf(tmp_path):
    out = tmp_path / "rapport.pdf"
    system = SystemInfo(model="<b>Modèle & Cie</b>")
    ReportGenerator("Atelier <i>A&B</i>").generate(system, _health(), str(out))
    assert out.stat().st_size > 1000


def test_pdf_without_any_score(tmp_path):
    out = tmp_path / "rapport.pdf"
    ReportGenerator("Atelier").generate(SystemInfo(), calculate_score(None, None, None), str(out))
    assert out.read_bytes().startswith(b"%PDF")


def test_qr_drawing_size():
    drawing = build_qr("RefurbPass-ID:test", size=70)
    assert drawing.width == 70 and drawing.height == 70

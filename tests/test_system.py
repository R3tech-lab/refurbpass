from refurbpass.collectors.system import build_model_name, format_ram


def test_lenovo_uses_commercial_name():
    assert build_model_name("LENOVO", "20L5000XFR", "ThinkPad T480") == "LENOVO ThinkPad T480"


def test_model_already_contains_manufacturer():
    assert build_model_name("Dell Inc.", "Dell Inc. Latitude 5490", None) == "Dell Inc. Latitude 5490"


def test_placeholders_become_unknown():
    assert build_model_name("To be filled by O.E.M.", "Default string", None) == "Inconnu"


def test_format_ram():
    assert format_ram(int(15.85 * 1024 ** 3)) == "16 Go"

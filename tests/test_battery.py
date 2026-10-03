from refurbpass.collectors.battery import compute_health, parse_powercfg_xml, read_linux_battery


def test_compute_health():
    assert compute_health(50000, 31000) == 0.62
    assert compute_health(50000, 52000) == 1.0  # plafonné
    assert compute_health(0, 31000) is None
    assert compute_health(50000, None) is None


def test_parse_powercfg_xml():
    xml = b"""<?xml version="1.0" encoding="UTF-8"?>
    <BatteryReport xmlns="http://schemas.microsoft.com/battery/2012">
      <Batteries><Battery>
        <DesignCapacity>48000</DesignCapacity>
        <FullChargeCapacity>36000</FullChargeCapacity>
        <CycleCount>212</CycleCount>
      </Battery></Batteries>
    </BatteryReport>"""
    assert parse_powercfg_xml(xml) == (48000, 36000, 212)
    assert parse_powercfg_xml(b"pas du xml") is None


def test_read_linux_battery(tmp_path):
    bat = tmp_path / "BAT0"
    bat.mkdir()
    (bat / "energy_full_design").write_text("50000000")
    (bat / "energy_full").write_text("40000000")
    (bat / "cycle_count").write_text("150")
    assert read_linux_battery(tmp_path) == (50000, 40000, 150, "mWh")


def test_read_linux_battery_absent(tmp_path):
    assert read_linux_battery(tmp_path) is None


def test_zero_cycles_means_unknown():
    xml = b"""<BatteryReport><Batteries><Battery>
        <DesignCapacity>93480</DesignCapacity><FullChargeCapacity>62096</FullChargeCapacity>
        <CycleCount>0</CycleCount></Battery></Batteries></BatteryReport>"""
    assert parse_powercfg_xml(xml) == (93480, 62096, None)

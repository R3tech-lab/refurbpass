import json

from refurbpass.collectors import disk
from refurbpass.collectors.disk import evaluate_disk, parse_scan

HEALTHY_NVME = {
    "model_name": "Samsung SSD 970 EVO",
    "device": {"name": "/dev/nvme0", "type": "nvme"},
    "smart_status": {"passed": True},
    "power_on_time": {"hours": 4210},
    "nvme_smart_health_information_log": {
        "percentage_used": 3, "critical_warning": 0, "media_errors": 0, "power_on_hours": 4210,
    },
}

WORN_SATA_SSD = {
    "model_name": "Kingston SA400",
    "device": {"name": "/dev/sda", "type": "sat"},
    "rotation_rate": 0,
    "smart_status": {"passed": True},
    "power_on_time": {"hours": 18000},
    "ata_smart_attributes": {"table": [
        {"id": 5, "name": "Reallocated_Sector_Ct", "value": 100, "raw": {"value": 12}},
        {"id": 231, "name": "SSD_Life_Left", "value": 15, "raw": {"value": 15}},
    ]},
}

FAILING_HDD = {
    "model_name": "WDC WD10",
    "device": {"name": "/dev/sdb", "type": "sat"},
    "rotation_rate": 5400,
    "smart_status": {"passed": False},
    "power_on_time": {"hours": 52000},
    "ata_smart_attributes": {"table": [
        {"id": 5, "name": "Reallocated_Sector_Ct", "value": 50, "raw": {"value": 400}},
        {"id": 197, "name": "Current_Pending_Sector", "value": 90, "raw": {"value": 8}},
    ]},
}


def test_healthy_nvme():
    report = evaluate_disk(HEALTHY_NVME, "/dev/nvme0")
    assert report.kind == "SSD NVMe"
    assert report.power_on_hours == 4210
    assert report.wear_used_pct == 3
    assert report.health == 0.97
    assert report.issues == []


def test_worn_sata_ssd():
    report = evaluate_disk(WORN_SATA_SSD, "/dev/sda")
    assert report.kind == "SSD"
    assert report.wear_used_pct == 85
    assert report.reallocated_sectors == 12
    assert report.health <= 0.15
    assert any("remplacement conseillé" in i for i in report.issues)


def test_failing_hdd():
    report = evaluate_disk(FAILING_HDD, "/dev/sdb")
    assert report.kind == "HDD"
    assert report.smart_passed is False
    assert report.pending_sectors == 8
    assert report.health == 0.0
    assert len(report.issues) >= 3


def test_parse_scan():
    out = "/dev/sda -d ata # /dev/sda, ATA device\n/dev/nvme0 -d nvme # /dev/nvme0, NVMe device\n"
    assert parse_scan(out) == [("/dev/sda", ["-d", "ata"]), ("/dev/nvme0", ["-d", "nvme"])]


class _Proc:
    def __init__(self, stdout, returncode=0):
        self.stdout, self.returncode = stdout, returncode


def test_collect_without_smartctl(monkeypatch):
    monkeypatch.setattr(disk.shutil, "which", lambda _: None)
    info = disk.collect_disk_info()
    assert info.status == "Unavailable"
    assert "non installé" in info.details


def test_collect_takes_worst_disk(monkeypatch):
    monkeypatch.setattr(disk.shutil, "which", lambda _: "smartctl")
    payloads = {"/dev/nvme0": HEALTHY_NVME, "/dev/sda": WORN_SATA_SSD}

    def fake_run(cmd, timeout=30):
        if "--scan" in cmd:
            return _Proc("/dev/nvme0 -d nvme\n/dev/sda -d sat\n")
        return _Proc(json.dumps(payloads[cmd[3]]))

    monkeypatch.setattr(disk, "_run", fake_run)
    info = disk.collect_disk_info()
    assert info.status == "OK"
    assert len(info.disks) == 2
    assert info.health == min(d.health for d in info.disks)


def test_permission_denied_is_unavailable_not_warning(monkeypatch):
    monkeypatch.setattr(disk.shutil, "which", lambda _: "smartctl")

    def fake_run(cmd, timeout=30):
        if "--scan" in cmd:
            return _Proc("/dev/sda -d ata\n")
        return _Proc(json.dumps({"smartctl": {"exit_status": 2}}), returncode=2)

    monkeypatch.setattr(disk, "_run", fake_run)
    info = disk.collect_disk_info()
    assert info.status == "Unavailable"
    assert info.health is None
    assert "administrateur" in info.details

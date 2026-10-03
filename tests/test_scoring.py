from refurbpass.scoring import calculate_score


def test_perfect_health():
    result = calculate_score(1.0, 1.0, 1.0)
    assert result.overall_score == 100
    assert all(c.status == "OK" for c in result.component_scores)
    assert result.summary_weak_points == []


def test_partial_health():
    # (62 * 0.3) + (95 * 0.4) + (100 * 0.3) = 86.6 -> 86
    result = calculate_score(0.62, 0.95, 1.0)
    assert result.overall_score == 86
    assert result.component_scores[0].status == "Warning"
    assert any("Batterie à 62%" in wp for wp in result.summary_weak_points)


def test_critical_health():
    # (40 * 0.3) + (50 * 0.4) + (80 * 0.3) = 56
    result = calculate_score(0.40, 0.50, 0.80)
    assert result.overall_score == 56
    assert result.component_scores[0].status == "Critical"
    assert result.component_scores[1].status == "Critical"
    assert len(result.summary_weak_points) >= 2


def test_only_system_available():
    result = calculate_score(None, None, 1.0)
    assert result.overall_score == 100
    assert result.component_scores[0].status == "Unavailable"
    assert result.component_scores[1].status == "Unavailable"
    assert result.component_scores[2].status == "OK"


def test_system_not_measured_does_not_inflate_score():
    # Sans test système, le score ne repose que sur batterie (30) et disque (40).
    # (50 * 30 + 50 * 40) / 70 = 50, et non plus 65 comme avec un système « offert » à 100.
    result = calculate_score(0.5, 0.5, None)
    assert result.overall_score == 50
    assert result.component_scores[2].status == "Unavailable"


def test_desktop_without_battery_is_not_applicable():
    result = calculate_score(None, 0.95, None, not_applicable=["battery"])
    battery = result.component_scores[0]
    assert battery.status == "NotApplicable"
    assert result.overall_score == 95


def test_nothing_measured_gives_no_score():
    # Rien mesuré : pas de score (et surtout pas 0/100, qui dirait « PC en très mauvais état »)
    result = calculate_score(None, None, None)
    assert result.overall_score is None


def test_disk_issues_replace_generic_phrase():
    issues = ["Samsung SSD : 12 secteurs réalloués, à surveiller"]
    result = calculate_score(None, 0.6, None, disk_issues=issues)
    assert result.summary_weak_points == issues


def test_custom_details_are_used():
    result = calculate_score(0.9, None, None, details={"disk": "smartmontools non installé"})
    assert result.component_scores[1].details == "smartmontools non installé"

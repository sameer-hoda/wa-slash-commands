from mac.validation.gemini import classify_validation


def test_missing_key():
    assert classify_validation(False, False, False, "") == "missing"


def test_quota_error_maps_to_quota():
    assert classify_validation(True, True, False, "429 quota exceeded") == "quota"


def test_region_error_maps_to_region():
    assert classify_validation(True, True, False, "403 region not supported") == "region-blocked"


def test_invalid_key():
    assert classify_validation(True, False, False, "400 API key not valid") == "invalid"


def test_offline():
    assert classify_validation(True, True, False, "connection reset offline") == "offline"


def test_valid():
    assert classify_validation(True, True, True, "") == "valid"

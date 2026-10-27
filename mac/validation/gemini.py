"""Real Gemini key validation classifier for onboarding."""


def classify_validation(list_models_ok: bool, model_present: bool,
                        probe_ok: bool, probe_error: str) -> str:
    if not list_models_ok and not model_present and not probe_ok \
            and not (probe_error or "").strip():
        return "missing"
    err = (probe_error or "").lower()
    if probe_ok and list_models_ok and model_present:
        return "valid"
    if "429" in err or "quota" in err:
        return "quota"
    if "403" in err or "region" in err or "not supported" in err:
        return "region-blocked"
    if "offline" in err or "connection" in err or "timeout" in err \
            or "unreachable" in err:
        return "offline"
    return "invalid"

from server.locale.log_messages import normalize_locale, t


def test_normalize_locale_defaults() -> None:
    assert normalize_locale(None) == "es"
    assert normalize_locale("") == "es"
    assert normalize_locale("fr") == "es"


def test_normalize_locale_bcp47() -> None:
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("es-ES") == "es"


def test_t_spanish_known_key() -> None:
    s = t("update.git_pull", "es")
    assert "git pull" in s.lower()


def test_t_english_known_key() -> None:
    s = t("update.git_pull", "en")
    assert "git pull" in s.lower()


def test_t_fallback_unknown_locale() -> None:
    s = t("update.git_pull", "xx")
    assert "git pull" in s.lower()


def test_t_fallback_unknown_key() -> None:
    s = t("nonexistent.key", "en")
    assert s == "nonexistent.key"


def test_t_interpolation() -> None:
    assert "foo" in t("summary.project", "en", name="foo", status="OK")

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


def test_both_locales_define_the_same_keys() -> None:
    """A UI string added to one language only is the easiest i18n regression to ship."""
    from server.locale.log_messages import _MESSAGES

    assert set(_MESSAGES["es"]) == set(_MESSAGES["en"])


def test_every_key_used_in_the_code_exists() -> None:
    import pathlib
    import re

    from server.locale.log_messages import _MESSAGES

    used: set[str] = set()
    for path in pathlib.Path("server").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        used |= set(re.findall(r"""\bt\(\s*['"]([a-z_]+\.[a-z_]+)['"]""", source))

    assert used, "the scan found no t() calls at all, the pattern must have drifted"
    assert used <= set(_MESSAGES["es"]), f"missing keys: {sorted(used - set(_MESSAGES['es']))}"

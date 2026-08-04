from server.locale.log_messages import _MESSAGES, normalize_locale, t


def test_normalize_locale_defaults() -> None:
    assert normalize_locale(None) == "es"
    assert normalize_locale("") == "es"
    assert normalize_locale("fr") == "es"


def test_normalize_locale_bcp47() -> None:
    assert normalize_locale("en-US") == "en"
    assert normalize_locale("es-ES") == "es"


def test_each_locale_returns_its_own_string() -> None:
    """Asserting a shared literal like "git pull" proved nothing: it is in both tables,
    so the old tests passed even with the locale argument ignored or the tables swapped."""
    spanish = t("update.compose_pull", "es")
    english = t("update.compose_pull", "en")

    assert spanish != english
    assert spanish == _MESSAGES["es"]["update.compose_pull"]
    assert english == _MESSAGES["en"]["update.compose_pull"]


def test_t_fallback_unknown_locale_is_spanish() -> None:
    assert t("update.compose_pull", "xx") == t("update.compose_pull", "es")
    assert t("update.compose_pull", None) == t("update.compose_pull", "es")


def test_t_fallback_unknown_key() -> None:
    s = t("nonexistent.key", "en")
    assert s == "nonexistent.key"


def test_t_interpolation() -> None:
    assert "foo" in t("summary.project", "en", name="foo", status="OK")


def test_both_locales_define_the_same_keys() -> None:
    """A UI string added to one language only is the easiest i18n regression to ship."""
    assert set(_MESSAGES["es"]) == set(_MESSAGES["en"])


def test_no_translation_is_left_identical_by_accident() -> None:
    """Catches a key copied into the other table without being translated.

    The allowlist is for strings that genuinely are the same in both languages.
    """
    same_on_purpose = {
        "log.prefix_ok",
        "log.prefix_err",
        "log.prefix_warn",
        "log.prefix_info",
        "log.status_ok",
        "log.status_error",
        "error.error_prefix",
        # A technical label and a pure interpolation: nothing to translate in either.
        "docker.stderr_label",
        "summary.project",
    }
    identical = {
        key
        for key, value in _MESSAGES["es"].items()
        if _MESSAGES["en"].get(key) == value
    }

    assert identical <= same_on_purpose, f"sin traducir: {sorted(identical - same_on_purpose)}"


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

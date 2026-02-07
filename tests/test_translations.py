"""
Tests for translations module.
"""

from translations import t, resolve_lang, MESSAGES, SUPPORTED_LANGUAGES, DEFAULT_LANGUAGE


class TestResolveLang:
    def test_none(self):
        assert resolve_lang(None) == "en"

    def test_empty_string(self):
        assert resolve_lang("") == "en"

    def test_english(self):
        assert resolve_lang("en") == "en"

    def test_italian(self):
        assert resolve_lang("it") == "it"

    def test_with_region_code(self):
        assert resolve_lang("it-IT") == "it"
        assert resolve_lang("en-US") == "en"
        assert resolve_lang("en-GB") == "en"

    def test_unsupported_language(self):
        assert resolve_lang("de") == "en"
        assert resolve_lang("fr") == "en"
        assert resolve_lang("zh") == "en"

    def test_case_insensitive(self):
        assert resolve_lang("IT") == "it"
        assert resolve_lang("EN") == "en"


class TestTranslate:
    def test_english_simple(self):
        result = t("not_authorized", "en")
        assert result == "You are not authorized to use this bot."

    def test_italian_simple(self):
        result = t("not_authorized", "it")
        assert result == "Non sei autorizzato ad usare questo bot."

    def test_interpolation_english(self):
        result = t("welcome", "en", username="Alice")
        assert result == "Hi Alice, welcome! Use /add_channel to add a channel to monitor."

    def test_interpolation_italian(self):
        result = t("welcome", "it", username="Alice")
        assert result == "Ciao Alice, benvenuto! Usa /add_channel per aggiungere un canale da monitorare."

    def test_fallback_unsupported_language(self):
        result = t("not_authorized", "de")
        assert result == "You are not authorized to use this bot."

    def test_fallback_missing_key(self):
        result = t("nonexistent_key", "en")
        assert result == "nonexistent_key"

    def test_fallback_missing_key_other_lang(self):
        result = t("nonexistent_key", "it")
        assert result == "nonexistent_key"

    def test_timed_out_with_command(self):
        result = t("timed_out", "en", command="/add_channel")
        assert result == "Timed out. Try again with /add_channel."

    def test_timed_out_italian(self):
        result = t("timed_out", "it", command="/add_channel")
        assert result == "Tempo scaduto. Riprova con /add_channel."

    def test_backfill_matches_interpolation(self):
        result = t("backfill_matches", "en", count=5)
        assert "5" in result

    def test_watch_active_interpolation(self):
        result = t("watch_active", "en", product="iphone", price_info=" at ≤799.00", cat_info=" [electronics]")
        assert "iphone" in result
        assert "799.00" in result

    def test_notify_price_line_float_format(self):
        result = t("notify_price_line", "en", price=749.0, target=800.0)
        assert "749.00" in result
        assert "800.00" in result


class TestCompleteness:
    def test_all_en_keys_exist_in_it(self):
        en_keys = set(MESSAGES["en"].keys())
        it_keys = set(MESSAGES["it"].keys())
        missing = en_keys - it_keys
        assert not missing, f"Italian translation missing keys: {missing}"

    def test_all_it_keys_exist_in_en(self):
        en_keys = set(MESSAGES["en"].keys())
        it_keys = set(MESSAGES["it"].keys())
        extra = it_keys - en_keys
        assert not extra, f"Italian has extra keys not in English: {extra}"

    def test_supported_languages_have_messages(self):
        for lang in SUPPORTED_LANGUAGES:
            assert lang in MESSAGES, f"No messages defined for supported language '{lang}'"

    def test_default_language_is_supported(self):
        assert DEFAULT_LANGUAGE in SUPPORTED_LANGUAGES

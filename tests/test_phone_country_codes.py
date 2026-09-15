from pathlib import Path

from backend.phone_country_codes import PHONE_COUNTRY_CODES, phone_country_options


def test_phone_country_catalog_is_complete_and_has_valid_values():
    assert len(PHONE_COUNTRY_CODES) >= 200
    assert PHONE_COUNTRY_CODES[:4] == (
        {"region": "DE", "dial_code": "+49"},
        {"region": "TM", "dial_code": "+993"},
        {"region": "US", "dial_code": "+1"},
        {"region": "RU", "dial_code": "+7"},
    )
    assert all(item["region"].isalpha() and len(item["region"]) == 2 for item in PHONE_COUNTRY_CODES)
    assert all(item["dial_code"].startswith("+") and item["dial_code"][1:].isdigit() for item in PHONE_COUNTRY_CODES)


def test_phone_country_options_returns_safe_copies():
    options = phone_country_options()
    options[0]["dial_code"] = "+0"

    assert PHONE_COUNTRY_CODES[0]["dial_code"] == "+49"


def test_registration_template_uses_structured_phone_catalog():
    template = Path("frontend/register.html").read_text(encoding="utf-8")
    script = Path("static/register.js").read_text(encoding="utf-8")

    assert "{% for country in phone_countries %}" in template
    assert 'data-region="{{ country.region }}"' in template
    assert "Германия +49" not in template
    assert "Intl.DisplayNames" in script
    assert "regionFlag" in script

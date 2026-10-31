import json
import os
import re
from urllib.parse import unquote

import pytest
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

load_dotenv()

TARGET_URL = os.getenv("TARGET_URL", "https://geolizr.myshopify.com/").strip()
IP_CHECK_URL = os.getenv("IP_CHECK_URL", "https://ipapi.co/json/").strip()

# Three tested proxy regions. Keep browser language/timezone identical
# so the proxy exit country is the primary variable.
REGIONS = [
    {"name": "US", "expected_country": "US", "expected_currency": "USD"},
    {"name": "UK", "expected_country": "GB", "expected_currency": "GBP"},
    {"name": "DE", "expected_country": "DE", "expected_currency": "EUR"},
]

BROWSER_LOCALE = os.getenv("BROWSER_LOCALE", "en-US")
BROWSER_TIMEZONE = os.getenv("BROWSER_TIMEZONE", "UTC")


def required_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        pytest.fail(f"Missing environment variable: {name}")
    return value


def parse_cookie_value(cookies, name):
    for cookie in cookies:
        if cookie.startswith(name + "="):
            return cookie.split("=", 1)[1]
    return None


def parse_geolizr_data(raw_value):
    """Decode Geolizr's URL-encoded JSON cookie, if present."""
    if not raw_value:
        return None
    try:
        decoded = unquote(raw_value)
        data = json.loads(decoded)
        return {
            "country_code": data.get("countryCode")
                or (data.get("country") or {}).get("code"),
            "country_name": data.get("countryName")
                or (data.get("country") or {}).get("country"),
            "currency_code": data.get("currencyCode")
                or (data.get("currency") or {}).get("code"),
            "city": data.get("city"),
            "region": data.get("regionName"),
            "timezone": data.get("timezone"),
            "ip_seen_by_geolizr": data.get("query"),
            "geoip_service": data.get("service"),
        }
    except (ValueError, TypeError):
        return {"parse_error": "Unable to decode geolizr_data cookie"}


def detect_visible_currencies(body_text):
    """Detect currency codes/symbols in page text; bare '$' is ambiguous."""
    patterns = [
        (r"\bUSD\b|US\$\s*[\d.,]+", "USD"),
        (r"\bGBP\b|£\s*[\d.,]+", "GBP"),
        (r"\bEUR\b|€\s*[\d.,]+", "EUR"),
        (r"\bCAD\b|CA\$\s*[\d.,]+", "CAD"),
        (r"\bAUD\b|AU\$\s*[\d.,]+", "AUD"),
        (r"(?<![A-Z])\$\s*[\d.,]+", "AMBIGUOUS_DOLLAR"),
    ]
    found = []
    for pattern, code in patterns:
        matches = re.findall(pattern, body_text, flags=re.IGNORECASE)
        if matches:
            found.append({
                "currency": code,
                "matches": list(dict.fromkeys(matches))[:10],
            })
    return found


def inspect_geolizr(page):
    # Wait briefly for the GeoIP widget to initialize and write its cookies.
    try:
        page.wait_for_function(
            "() => document.cookie.includes('geolizr_data=')",
            timeout=15000,
        )
    except PlaywrightTimeoutError:
        pass

    body_text = page.locator("body").inner_text(timeout=10000)
    browser_info = page.evaluate("""() => ({
        language: navigator.language,
        languages: navigator.languages,
        timezone: Intl.DateTimeFormat().resolvedOptions().timeZone,
        html_language: document.documentElement.lang
    })""")

    cookies = page.context.cookies()
    cookie_map = {
        item["name"]: item["value"]
        for item in cookies
        if item["domain"].lstrip(".").endswith("geolizr.myshopify.com")
    }

    geolizr_data = parse_geolizr_data(
        cookie_map.get("geolizr_data")
    )

    currency_switcher = page.evaluate("""() => {
        const nodes = Array.from(document.querySelectorAll(
            '[class*="currency" i], [id*="currency" i], '
            + '[name*="currency" i]'
        ));
        return nodes.slice(0, 12).map(el => ({
            tag: el.tagName,
            name: el.getAttribute('name'),
            value: el.value || null,
            text: (el.innerText || el.textContent || '')
                .trim().slice(0, 120)
        }));
    }""")

    return {
        "final_url": page.url,
        "page_title": page.title(),
        "page_language": browser_info["html_language"],
        "browser": browser_info,
        "body_currency_signals": detect_visible_currencies(body_text),
        "geolizr_cookie": geolizr_data,
        "currency_cookies": {
            key: value for key, value in cookie_map.items()
            if "currency" in key.lower()
        },
        "currency_switcher_elements": currency_switcher,
        "body_text_sample": body_text[:1200],
    }


@pytest.mark.parametrize(
    "region",
    REGIONS,
    ids=[region["name"] for region in REGIONS],
)
def test_geolizr_geoip_currency(region):
    proxy_region = region["name"]

    proxy_server = required_env("PROXY_SERVER")
    proxy_username = required_env(f"PROXY_USERNAME_{proxy_region}")
    proxy_password = required_env(f"PROXY_PASSWORD_{proxy_region}")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            proxy={
                "server": proxy_server,
                "username": proxy_username,
                "password": proxy_password,
            },
        )

        # A fresh context per region prevents previous cookies/local storage
        # from influencing the next region's result.
        context = browser.new_context(
            locale=BROWSER_LOCALE,
            timezone_id=BROWSER_TIMEZONE,
            viewport={"width": 1440, "height": 1000},
        )

        try:
            page = context.new_page()
            page.set_default_timeout(20000)

            # Verify the actual proxy exit country.
            ip_response = page.goto(
                IP_CHECK_URL,
                wait_until="domcontentloaded",
                timeout=45000,
            )
            assert ip_response and ip_response.ok, "IP check request failed"
            ip_data = ip_response.json()
            actual_country = (ip_data.get("country_code") or "").upper()

            assert actual_country == region["expected_country"], (
                f"Proxy country mismatch: expected "
                f"{region['expected_country']}, got {actual_country}"
            )

            # Visit the same Geolizr demo URL for every region.
            response = page.goto(
                TARGET_URL,
                wait_until="domcontentloaded",
                timeout=60000,
            )
            assert response and response.ok, "Target website request failed"

            try:
                page.wait_for_load_state("networkidle", timeout=10000)
            except PlaywrightTimeoutError:
                pass

            page.wait_for_timeout(2500)
            result = inspect_geolizr(page)

            geo_cookie = result["geolizr_cookie"] or {}
            detected_country = geo_cookie.get("country_code")
            detected_currency = geo_cookie.get("currency_code")

            report = {
                "region": proxy_region,
                "proxy_ip_check": {
                    "ip": ip_data.get("ip"),
                    "country_code": actual_country,
                    "expected_country": region["expected_country"],
                    "status": "PASS",
                },
                "expected_currency": region["expected_currency"],
                "geolizr": result,
                "checks": {
                    "geolizr_country_matches_proxy": (
                        detected_country == actual_country
                    ),
                    "geolizr_currency_matches_expected": (
                        detected_currency == region["expected_currency"]
                    ),
                },
            }

            print("\n" + "=" * 72)
            print(f"GEOLIZR GEOIP TEST: {proxy_region}")
            print("=" * 72)
            print(json.dumps(report, indent=2, ensure_ascii=False))

            # Validate GeoIP cookie values, not just a currency symbol.
            assert detected_country == actual_country, (
                f"Geolizr detected {detected_country}, "
                f"but proxy country is {actual_country}"
            )
            assert detected_currency == region["expected_currency"], (
                f"Expected currency {region['expected_currency']}, "
                f"Geolizr detected {detected_currency}"
            )

        finally:
            context.close()
            browser.close()

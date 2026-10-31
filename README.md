# KindProxy GeoIP Benchmark

A small Playwright test project that checks whether a website identifies visitors by their proxy exit IP and assigns the corresponding country and currency.

## Tested target

- **Geolizr Demo Store:** https://geolizr.myshopify.com/

## Tested regions

| Proxy region | Expected country code | Expected currency |
|---|---|---|
| US | US | USD |
| UK | GB | GBP |
| DE | DE | EUR |

The browser environment is held constant for all regions:

- Locale: `en-US`
- Timezone: `UTC`
- A fresh browser context is created for every test.
- Cookies and LocalStorage are not shared between regions.

This helps isolate the proxy exit country as the main changing variable.

## What the test checks

1. Confirms the proxy exit country using `ipapi.co`.
2. Opens the same Geolizr demo URL for each region.
3. Reads the `geolizr_data` cookie written by Geolizr.
4. Extracts the detected country, currency, city, timezone and IP reported by Geolizr.
5. Compares Geolizr's country/currency result with the expected values.

The test validates the GeoIP data reported by Geolizr. It does not claim that every e-commerce store uses the same detection logic, nor does it verify checkout totals.

## Requirements

- Python 3.10+
- Residential proxies in US, UK and DE
- Proxy endpoint supporting HTTP or HTTPS proxy connections
- A valid proxy username and password for each region

## Installation

```bash
git clone https://github.com/YOUR_USERNAME/kindproxy-geoip-benchmark.git
cd kindproxy-geoip-benchmark

python -m venv .venv
source .venv/bin/activate
# Windows PowerShell:
# .venv\\Scripts\\Activate.ps1

pip install -r requirements.txt
playwright install chromium
```

On Ubuntu, if browser system dependencies are missing:

```bash
playwright install --with-deps chromium
```

## Configuration

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

On Windows, copy the file manually or run:

```powershell
Copy-Item .env.example .env
```

Fill in your own proxy endpoint and credentials:

```env
PROXY_SERVER=http://your-proxy-host:your-port

PROXY_USERNAME_US=your_us_username
PROXY_PASSWORD_US=your_us_password

PROXY_USERNAME_UK=your_uk_username
PROXY_PASSWORD_UK=your_uk_password

PROXY_USERNAME_DE=your_de_username
PROXY_PASSWORD_DE=your_de_password

TARGET_URL=https://geolizr.myshopify.com/
IP_CHECK_URL=https://ipapi.co/json/
BROWSER_LOCALE=en-US
BROWSER_TIMEZONE=UTC
```

**Never commit `.env` or publish proxy credentials.** `.gitignore` already excludes `.env`.

## Run

Run all three regions:

```bash
python -m pytest -v -s
```

Run only Germany:

```bash
python -m pytest -v -s -k DE
```

Run only the UK:

```bash
python -m pytest -v -s -k UK
```

Run only the US:

```bash
python -m pytest -v -s -k US
```

## Expected result

The current tested configuration produced:

| Proxy exit country | Geolizr detected country | Geolizr detected currency |
|---|---|---|
| US | US | USD |
| GB | GB | GBP |
| DE | DE | EUR |

Results can change if the demo store, GeoIP database, app configuration or proxy IP changes. The test asserts the expected country and currency, so a changed result will fail with a useful assertion message.

## Project structure

```text
kindproxy-geoip-benchmark/
├── tests/
│   └── test_geolizr_geoip.py
├── .env.example
├── .gitignore
├── pytest.ini
├── README.md
└── requirements.txt
```

## Notes

- Geolizr's demo page describes its currency widget as automatically converting prices to match visitor location.
- The test reads Geolizr's own `geolizr_data` cookie as the primary evidence of the country/currency it detected.
- A visible currency symbol alone is not treated as proof of GeoIP detection.
- The GeoBeacon URL tested in an earlier experiment was its product/marketing homepage, not an actual configured merchant storefront demo. It is intentionally not included in this benchmark.

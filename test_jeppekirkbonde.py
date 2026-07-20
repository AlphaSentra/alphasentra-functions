import os
import sys
from pathlib import Path

base = Path('/Users/daivieth/Documents/_G8I/Development/alphasentra-functions')
_port_dir = base / 'Functions' / 'port'
if str(_port_dir) not in sys.path:
    sys.path.insert(0, str(_port_dir))
env_path = base / '.env'
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        k, v = line.split('=', 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))

from Functions.port.selection import (
    _search_user_full,
    _get_period_gain,
    _get_rankings,
    _prefetch_country_data,
    _country_html,
)

USERNAME = "JeppeKirkBonde"

print(f"\n=== Looking up {USERNAME} ===\n")

item = _search_user_full(USERNAME)
if not item:
    print(f"No results found for {USERNAME}")
    sys.exit(0)

print(f"userName:       {item.get('userName')}")
print(f"fullName:       {item.get('fullName')}")
print(f"aumTierDesc:    {item.get('aumTierDesc')}")
print(f"aumValue:       {item.get('aumValue')}")
print(f"copiers:        {item.get('copiers')}")
print(f"baseLineCopiers:{item.get('baseLineCopiers')}")
print(f"gain (1M):      {item.get('gain')}")
print(f"country raw:    {item.get('country')}")
print(f"countryId raw:  {item.get('countryId')}")
print(f"subType:        {item.get('subType')}")

print(f"\n=== Country mapping ===")
print(f"Input country={item.get('country')!r}  countryId={item.get('countryId')!r}")

_prefetch_country_data([item])
country_html = _country_html(item.get("country"))
print(f"Rendered country HTML: {country_html}")

print(f"\n=== Period gains for {USERNAME} ===\n")

for label, period in [("1M", "1m"), ("3M", "3m"), ("1Y", "1y")]:
    gain = _get_period_gain(USERNAME, period)
    print(f"{label}: {gain}")

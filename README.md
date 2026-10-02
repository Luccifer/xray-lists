# xray-lists

Small, frequently updated domain lists for selective tunnelling (xray / dnsmasq nftset / RouterOS),
built from upstream geosite files plus our own lists.

## Download (always the latest)

| File | Use |
|---|---|
| [`geosite.dat`](../../releases/latest/download/geosite.dat) | xray: `"domain": ["ext:geosite.dat:proxy"]`, also `exclude`, `manual`, `zapret-zapad`, `youtube`, `telegram`, … |
| [`proxy.txt`](../../releases/latest/download/proxy.txt) | plain domains to tunnel (dnsmasq `nftset=`, RouterOS DNS FWD `address-list=`) |
| [`exclude.txt`](../../releases/latest/download/exclude.txt) | domains never to tunnel: Russian commercial + government services, RU TLDs |
| [`cidr.txt`](../../releases/latest/download/cidr.txt) | IPv4 subnets to tunnel (Telegram) |
| [`sha256sums.txt`](../../releases/latest/download/sha256sums.txt) | poll this first; download the rest only if it changed |

URL pattern: `https://github.com/<owner>/xray-lists/releases/latest/download/<file>`

## Editing

- `lists/proxy.txt`: our own domains. One per line; `domain` (default, includes subdomains), `full:`, `keyword:`, `regexp:`.
  Only domain/full entries reach `proxy.txt`; keyword/regexp work in `geosite.dat` only.
- `lists/exclude.txt`: extra domains never to tunnel. EXCLUDE also includes v2fly `CATEGORY-RU` (Russian commercial
  services), `CATEGORY-GOV-RU` (government) and `TLD-RU` (`.ru`, `.su`, `.рф`, …).
  Precedence: `lists/proxy.txt` > EXCLUDE > upstream proxy categories. TLD entries mean "direct by default" and
  never remove a specific domain from PROXY.
- `lists/cidr.txt`: IPv4 subnets.
- `sources.txt`: `<proxy|exclude> <name> <url> <CATEGORIES>`: upstream `.dat` files and which categories go where
  (proxy: `zapret.dat` → ZAPRET-ZAPAD, v2fly `dlc.dat` → 37 service categories; exclude: v2fly RU categories).

A push to `lists/` publishes a new release in about a minute. Upstream is re-checked every 2 hours, and a release is
created only when something changed. If `proxy.txt` would shrink by more than 20% (broken upstream), the build fails
and the previous release stays.

Local build: `python3 build.py` (stdlib only) → `dist/`.

## Sources

- https://github.com/kutovoys/ru_gov_zapret (ZAPRET-ZAPAD)
- https://github.com/v2fly/domain-list-community

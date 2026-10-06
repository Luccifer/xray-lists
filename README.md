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
| [`nets.txt`](../../releases/latest/download/nets.txt) | IPv4 prefixes of the hosting/CDN networks in `lists/asn.txt` (aggregated) |
| [`nets.rsc`](../../releases/latest/download/nets.rsc) | RouterOS: the same as address-list `to-xray-net-new` (timeout 3d); a router script imports it and swaps lists |
| [`mikrotik.rsc`](../../releases/latest/download/mikrotik.rsc) | RouterOS: DNS FWD entries → address-list `to-xray` (+ cidr.txt subnets); `/import` it |
| [`sha256sums.txt`](../../releases/latest/download/sha256sums.txt) | poll this first; download the rest only if it changed |

URL pattern: `https://github.com/<owner>/xray-lists/releases/latest/download/<file>`

## Editing

- `lists/proxy.txt`: our own domains. One per line; `domain` (default, includes subdomains), `full:`, `keyword:`, `regexp:`.
  Only domain/full entries reach `proxy.txt`; keyword/regexp work in `geosite.dat` only.
- `lists/packages.txt`: package repositories/registries (Debian, Ubuntu, Alpine, Fedora/RHEL, Arch, HashiCorp, Docker, k8s,
  PyPI, npm, Go, crates, Maven, vendor repos). Some answer 403 to RU IPs. Same syntax, same precedence as proxy.txt; category `PACKAGES`.
- `lists/exclude.txt`: extra domains never to tunnel. EXCLUDE also includes v2fly `CATEGORY-RU` (Russian commercial
  services), `CATEGORY-GOV-RU` (government) and `TLD-RU` (`.ru`, `.su`, `.рф`, …).
  Precedence: `lists/proxy.txt` > EXCLUDE > upstream proxy categories. TLD entries mean "direct by default" and
  never remove a specific domain from PROXY.
- `lists/cidr.txt`: IPv4 subnets.
- `lists/asn.txt`: AS numbers (or literal CIDRs) tunnelled by IP (Cloudflare, Hetzner, DigitalOcean, …: Russian DPI freezes TLS to them after ~16 KB).
  Prefixes come from RIPEstat at build time; the build fails if an AS returns none or the total shrinks by more than 20%.
- `sources.txt`: `<proxy|exclude> <name> <url> <CATEGORIES>`: upstream `.dat` files and which categories go where
  (proxy: `zapret.dat` → ZAPRET-ZAPAD, v2fly `dlc.dat` → 37 service categories; exclude: v2fly RU categories).

A push to `lists/` publishes a new release in about a minute. Upstream is re-checked every 2 hours, and a release is
created only when something changed. If `proxy.txt` would shrink by more than 20% (broken upstream), the build fails
and the previous release stays.

Local build: `python3 build.py` (stdlib only) → `dist/`.

## Sources

- https://github.com/kutovoys/ru_gov_zapret (ZAPRET-ZAPAD)
- https://github.com/v2fly/domain-list-community

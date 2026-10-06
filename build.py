#!/usr/bin/env python3
"""Build small xray geosite.dat + plain-text lists from upstream .dat files and lists/*.txt.

Inputs:  sources.txt (name url CATEGORIES), lists/proxy.txt, lists/exclude.txt, lists/cidr.txt, lists/asn.txt
Outputs (dist/):
  geosite.dat   categories: PROXY (everything to tunnel), EXCLUDE, plus one per upstream category
  proxy.txt     domains to tunnel (domain/full entries only, for dnsmasq nftset / RouterOS)
  exclude.txt   domains never to tunnel
  cidr.txt      IPv4 subnets to tunnel
  nets.txt      IPv4 prefixes of the networks in lists/asn.txt (aggregated)
  nets.rsc      RouterOS: the same as address-list "to-xray-net-new" entries (the router script swaps lists)
  stats.txt, sha256sums.txt
No dependencies (stdlib only).
"""
import hashlib, ipaddress, json, os, re, sys, urllib.request

DIST = "dist"
# GeoSite Domain.Type
PLAIN, REGEX, DOMAIN, FULL = 0, 1, 2, 3
PREFIX = {"keyword": PLAIN, "regexp": REGEX, "domain": DOMAIN, "full": FULL}
NAME = {v: k for k, v in PREFIX.items()}


def varint(b, i):
    r = s = 0
    while True:
        x = b[i]; i += 1; r |= (x & 0x7F) << s; s += 7
        if x < 0x80:
            return r, i


def fields(b):
    """Yield (field_no, wire_type, value) for a protobuf message."""
    i = 0
    while i < len(b):
        key, i = varint(b, i)
        wt = key & 7
        if wt == 0:
            v, i = varint(b, i)
        elif wt == 2:
            n, i = varint(b, i); v = b[i:i + n]; i += n
        elif wt == 5:
            v = b[i:i + 4]; i += 4
        elif wt == 1:
            v = b[i:i + 8]; i += 8
        else:
            raise ValueError(f"wire type {wt}")
        yield key >> 3, wt, v


def parse_geosite(b, want):
    """Return {CATEGORY: [(type, value), ...]} for wanted categories (upper-case set)."""
    out = {}
    for fno, _, site in fields(b):
        if fno != 1:
            continue
        code, doms = None, []
        for f, _, v in fields(site):
            if f == 1:
                code = v.decode().upper()
                if code not in want:
                    break
            elif f == 2:
                t, val = 0, None
                for df, _, dv in fields(v):
                    if df == 1: t = dv
                    elif df == 2: val = dv.decode()
                if val:
                    doms.append((t, val))
        if code in want:
            out[code] = doms
    return out


def enc_varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F; n >>= 7
        out.append(b | 0x80 if n else b)
        if not n:
            return bytes(out)


def enc_field(fno, payload):
    return enc_varint(fno << 3 | 2) + enc_varint(len(payload)) + payload


def enc_geosite(code, doms):
    body = enc_field(1, code.encode())
    for t, v in doms:
        d = (enc_varint(1 << 3) + enc_varint(t) if t else b"") + enc_field(2, v.encode())
        body += enc_field(2, d)
    return enc_field(1, body)


def read_list(path):
    items = []
    for line in open(path, encoding="utf-8"):
        line = line.split("#", 1)[0].strip().lower()
        if not line:
            continue
        t = DOMAIN
        m = re.match(r"^(keyword|regexp|domain|full):(.+)$", line)
        if m:
            t, line = PREFIX[m.group(1)], m.group(2).strip()
        items.append((t, line))
    return items


def dedup(doms):
    seen, out = set(), []
    for d in doms:
        if d not in seen:
            seen.add(d); out.append(d)
    return sorted(out, key=lambda d: (d[0], d[1]))


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "xray-lists-build"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return r.read()


def asn_prefixes():
    """IPv4 prefixes announced by the AS numbers in lists/asn.txt (plus literal CIDR lines), aggregated.
    Fails the build if any AS returns none."""
    nets, stats = [], []
    for line in open("lists/asn.txt"):
        asn = line.split("#", 1)[0].strip().upper()
        if not asn:
            continue
        if "/" in asn:  # a literal prefix (provider without its own AS, e.g. Vercel inside AS16509)
            nets.append(ipaddress.ip_network(asn))
            continue
        d = json.loads(fetch(f"https://stat.ripe.net/data/announced-prefixes/data.json?resource={asn}&sourceapp=xray-lists"))
        got = [ipaddress.ip_network(p["prefix"]) for p in d["data"]["prefixes"] if ":" not in p["prefix"]]
        if not got:
            sys.exit(f"{asn}: no IPv4 prefixes from RIPEstat, refusing to publish")
        stats.append(f"{asn}: {len(got)}")
        nets += got
    return list(ipaddress.collapse_addresses(nets)), stats


def main():
    os.makedirs(DIST, exist_ok=True)
    cats = {"proxy": {}, "exclude": {}}
    stats, cache = [], {}
    for line in open("sources.txt", encoding="utf-8"):
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        target, name, url, want = line.split(None, 3)
        if target not in cats:
            sys.exit(f"sources.txt: unknown target {target!r} (use proxy or exclude)")
        want = {c.strip().upper() for c in want.split(",") if c.strip()}
        if url not in cache:
            cache[url] = fetch(url)
        got = parse_geosite(cache[url], want)
        missing = want - got.keys()
        if missing:
            sys.exit(f"{name}: categories not found upstream: {', '.join(sorted(missing))}")
        for c, doms in got.items():
            cats[target][c] = dedup(cats[target].get(c, []) + doms)
        stats.append(f"{target} {name}: {len(cache[url])/1e6:.1f} MB, {len(got)} categories, "
                     f"{sum(len(d) for d in got.values())} entries")

    packages = dedup(read_list("lists/packages.txt"))
    manual = dedup(read_list("lists/proxy.txt") + packages)
    exclude = dedup([d for doms in cats["exclude"].values() for d in doms] + read_list("lists/exclude.txt"))
    # Precedence: manual proxy > exclude > upstream proxy.
    # An exclude entry drops an upstream proxy entry if it is the same domain or a parent of it;
    # single-label entries (TLDs like "ru") only mean "direct by default" and drop nothing.
    excl_domains = {v for t, v in exclude if t in (DOMAIN, FULL) and "." in v}
    def excluded(v):
        parts = v.split(".")
        return any(".".join(parts[i:]) in excl_domains for i in range(len(parts) - 1))
    manual_vals = {v for _, v in manual}
    upstream = dedup([d for doms in cats["proxy"].values() for d in doms])
    dropped = sorted({v for t, v in upstream if v not in manual_vals and excluded(v)})
    proxy = dedup([d for d in upstream if d[1] in manual_vals or not excluded(d[1])] + manual)
    exclude = [d for d in exclude if d[1] not in manual_vals]
    excl_vals = {v for _, v in exclude}
    if dropped:
        stats.append(f"dropped from PROXY by exclude ({len(dropped)}): {', '.join(dropped[:30])}"
                     + (" ..." if len(dropped) > 30 else ""))

    out = {"PROXY": proxy, "EXCLUDE": exclude, "MANUAL": manual, "PACKAGES": packages, **cats["proxy"], **cats["exclude"]}
    with open(f"{DIST}/geosite.dat", "wb") as f:
        for code in sorted(out):
            f.write(enc_geosite(code, out[code]))

    # Plain lists: only domain/full entries are usable by dnsmasq nftset / RouterOS DNS.
    plain = sorted({v for t, v in proxy if t in (DOMAIN, FULL)})
    skipped = sum(1 for t, _ in proxy if t not in (DOMAIN, FULL))
    open(f"{DIST}/proxy.txt", "w").write("\n".join(plain) + "\n")
    open(f"{DIST}/exclude.txt", "w").write("\n".join(sorted(excl_vals)) + "\n")
    cidrs = [l.split("#", 1)[0].strip() for l in open("lists/cidr.txt") if l.split("#", 1)[0].strip()]
    open(f"{DIST}/cidr.txt", "w").write("\n".join(cidrs) + "\n")

    # RouterOS: DNS FWD entries put resolved IPs of listed domains into address-list "to-xray".
    full = {v for t, v in proxy if t == FULL}
    with open(f"{DIST}/mikrotik.rsc", "w") as f:
        f.write("# xray-lists for RouterOS: /import file-name=mikrotik.rsc\n")
        f.write('/ip dns static remove [find comment="xray-lists"]\n')
        for v in plain:
            sub = "no" if v in full else "yes"
            f.write(f':do {{ /ip dns static add name="{v}" type=FWD forward-to=1.1.1.1 match-subdomain={sub} '
                    f'address-list=to-xray comment="xray-lists" }} on-error={{}}\n')
        for c in cidrs:
            f.write(f':do {{ /ip firewall address-list add list=to-xray address={c} comment="xray-lists" }} on-error={{}}\n')
        f.write(f':log info "xray-lists: imported {len(plain)} domains, {len(cidrs)} subnets"\n')

    nets, nstats = asn_prefixes()
    open(f"{DIST}/nets.txt", "w").write("\n".join(map(str, nets)) + "\n")
    with open(f"{DIST}/nets.rsc", "w") as f:
        f.write("/ip firewall address-list\n")
        for n in nets:
            f.write(f"add list=to-xray-net-new address={n} timeout=3d comment=xray-nets\n")

    stats += [f"NETS: {len(nets)} aggregated prefixes ({', '.join(nstats)})"]
    stats += [f"PROXY: {len(proxy)} entries ({len(plain)} in proxy.txt, {skipped} keyword/regexp only in .dat)",
              f"EXCLUDE: {len(excl_vals)}  CIDR: {len(cidrs)}",
              f"geosite.dat: {os.path.getsize(DIST + '/geosite.dat')/1e3:.1f} KB, categories: {', '.join(sorted(out))}"]
    open(f"{DIST}/stats.txt", "w").write("\n".join(stats) + "\n")

    # Guard against a broken upstream: refuse to publish if the list shrank a lot.
    prev = os.environ.get("PREV_PROXY_COUNT")
    if prev and prev.isdigit() and len(plain) < int(prev) * 8 // 10:
        sys.exit(f"proxy.txt shrank from {prev} to {len(plain)} (>20%), refusing to publish")
    prev = os.environ.get("PREV_NETS_COUNT")
    if prev and prev.isdigit() and len(nets) < int(prev) * 8 // 10:
        sys.exit(f"nets.txt shrank from {prev} to {len(nets)} (>20%), refusing to publish")

    with open(f"{DIST}/sha256sums.txt", "w") as f:
        for n in ("geosite.dat", "proxy.txt", "exclude.txt", "cidr.txt", "mikrotik.rsc", "nets.txt", "nets.rsc"):
            f.write(f"{hashlib.sha256(open(f'{DIST}/{n}', 'rb').read()).hexdigest()}  {n}\n")
    print("\n".join(stats))


if __name__ == "__main__":
    main()

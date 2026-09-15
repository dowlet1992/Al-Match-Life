# Production HTTP security

The application enables secure session cookies in production, uses
`SameSite=Strict`, and emits HSTS only for HTTPS requests. When TLS terminates
at a reverse proxy, set `TRUST_PROXY=1` only if the application is reachable
exclusively through that trusted proxy. The proxy must overwrite, rather than
append, `X-Forwarded-For`, `X-Forwarded-Proto`, and `X-Forwarded-Host`.

For nginx, hide implementation details at the public edge:

```nginx
server_tokens off;
proxy_hide_header Server;
proxy_hide_header X-Powered-By;
proxy_set_header X-Forwarded-Proto $scheme;
proxy_set_header X-Forwarded-Host $host;
proxy_set_header X-Forwarded-For $remote_addr;
```

Do not expose the Flask development server in production.

The application-level middleware removes upstream `Server` and
`X-Powered-By` headers, but a WSGI server can add its own `Server` header after
the application returns. Therefore the public reverse proxy/CDN removal above
is mandatory and must be verified against the public URL.

## SNMP

Al-Match-Life does not use SNMP and has no SNMP package, configuration, or
listener. On the production host, disable and mask the operating-system SNMP
daemon and block UDP ports 161 and 162 at the host and cloud firewalls:

```sh
sudo systemctl disable --now snmpd
sudo systemctl mask snmpd
sudo ss -lunp | grep -E ':(161|162)\b'
```

The final command must return no listener. Apply equivalent controls on
non-systemd systems.

## Verification

Run Nuclei against the public HTTPS origin after deployment:

```sh
nuclei -u https://YOUR_PRODUCTION_HOST \
  -tags misconfig,exposure,cors,headers \
  -severity info,low,medium,high,critical
```

Also verify the edge response directly:

```sh
curl -sSIk https://YOUR_PRODUCTION_HOST/
curl -sSik -X OPTIONS -H 'Origin: https://evil.example' https://YOUR_PRODUCTION_HOST/api/health
```

The public response must not identify Werkzeug, Python, Flask, or a server
version. The cross-origin OPTIONS request must not contain any
`Access-Control-Allow-*` response headers.

# Security verification report

Initial verification: 2026-07-27
Latest repeat verification: 2026-07-28
Target: local production-mode HTTPS endpoint (`https://127.0.0.1:5443`)
Scanner: ProjectDiscovery Nuclei v3.8.0, official macOS arm64 release
Archive SHA-256: `872b49984a014eb6bf9022eb95889c9e5935900624d06880b1d856914606e80f`

The downloaded archive checksum matched the checksum published with the
official release.

## Nuclei result

The final scan produced zero findings for:

- `cookies-without-secure`
- `cookies-without-httponly`
- `missing-cookie-samesite-strict`
- `weak-csp-detect`
- `weak-hsts-detect`
- `http-missing-security-headers`
- `x-backend-server-header-detect`
- `cors-misconfig`

The same profile was run again on 2026-07-28 after the complete 730-test
suite passed. It again produced zero findings.

The test endpoint used production environment settings, a temporary
self-signed TLS certificate, and a strong scan-only Flask secret. No scan
credentials or certificate private keys were written to the repository.

## Observed HTTPS response

- Session cookie: `Secure; HttpOnly; SameSite=Strict`
- HSTS: `max-age=31536000; includeSubDomains; preload`
- CSP: nonce-based `script-src`; `script-src-attr 'none'`
- COEP: `require-corp`
- `X-Permitted-Cross-Domain-Policies: none`
- No `Server` or `X-Powered-By` header
- Cross-origin OPTIONS: HTTP 403 and no `Access-Control-Allow-*` headers

## Automated and static checks

- Full pytest suite: 730 tests passed
- POST forms without a visible CSRF token: none
- CSRF mismatch response: HTTP 403
- SQL values use parameter binding; the remaining dynamic SQL identifiers are
  restricted by explicit allowlists
- No project SNMP dependency or configuration
- No local UDP listener on ports 161 or 162 during verification

## Production boundary

This report validates the application and a local TLS endpoint. The public
deployment must be scanned again because a load balancer, CDN, WSGI server, or
reverse proxy can add/remove headers and because host-level SNMP cannot be
controlled by Flask. Follow `docs/SECURITY_DEPLOYMENT.md` on the production
host, then repeat the same Nuclei template set against the public HTTPS URL.

# Security Policy

## Supported versions

This is a private production trading system. Only `main` is supported.

## Reporting a vulnerability

**Do not open a public issue for security problems.** Email
`sumitrevolt23@gmail.com` with:

- A clear description of the issue.
- Steps to reproduce, proof-of-concept if you have one.
- The commit hash / branch where you spotted it.
- Your contact details so we can acknowledge and follow up.

You should receive an acknowledgement within 72 hours. A fix timeline
depends on severity:

| Severity | Target response |
|----------|-----------------|
| Credential exposure, remote code exec, trading-account compromise | 24 h |
| Local privilege / data leak / broker-API abuse | 7 d |
| Low-impact info disclosure | 30 d |

## What counts as a vulnerability

- Hard-coded or committed secrets (broker passwords, Telegram tokens, API keys).
  These must never be committed — see `.gitignore` and the
  `forbid-env-files` pre-commit hook. Report any you find regardless.
- Command injection or arbitrary-code paths in anything that reads
  user/broker-controlled input (MT5 symbols, EA JSON signals,
  Telegram commands, news-feed payloads).
- Ability to bypass the risk/halt gates (`check_risk`, `/halt`, max-DD breaker).
- Supply-chain compromise (malicious dep, tampered wheel).

## What is *not* a vulnerability

- Rate-limiting/DoS on dev helpers (they're not exposed externally).
- Strategy alpha leakage through logs on a trusted dev box.
- Stylistic lint issues (file them as regular issues).

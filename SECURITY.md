# Security policy

Please do not publish credentials, registration tokens, private keys, account
identifiers or exploitable security details in a public issue.

Open a minimal issue requesting private contact for a suspected vulnerability.
Do not attach OPNsense configuration exports, `usque-nativetun` configuration
files or Cloudflare diagnostic archives to public reports.

The plugin must treat all generated runtime configuration as secret:

- root ownership and mode `0600`;
- no credential material in command-line arguments;
- no secrets in logs, process status or API responses;
- atomic file replacement;
- strict validation of UUIDs, interface names and configd parameters.

This development scaffold is not ready for production use.

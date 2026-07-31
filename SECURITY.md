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

## Browser enrollment secrets

The browser-assisted client enrollment endpoint accepts either the one-time
Cloudflare callback URI for the configured team or the extracted enrollment
JWT. It must never accept the token through a query string.

Security properties enforced by the implementation:

- authenticated POST-only MVC API and normal OPNsense CSRF handling;
- strict tunnel UUID, job ID and team-name validation;
- callback host must match the configured `<team>.cloudflareaccess.com`;
- one-use, mode-`0600`, size-bounded, five-minute browser handoff;
- root claim uses `O_NOFOLLOW` and verifies owner, type and link count;
- fixed server-side paths derived only from validated identifiers;
- configd receives no credential-bearing parameter;
- root JWT handoff and resulting instance configuration use mode `0600`;
- token fields are cleared in the browser and omitted from job state and logs.

A compromised authenticated OPNsense administrator can initiate registration,
as expected for firewall administration, but cannot use these endpoints to
select arbitrary command paths or files.

# Architecture

## Separation of responsibilities

`usque-nativetun` owns:

- Cloudflare registration and MASQUE enrollment;
- QUIC/HTTP/3 CONNECT-IP;
- native TUN creation and packet transport;
- PMTUD, keepalive and connection telemetry.

`os-usque` owns:

- OPNsense configuration and validation;
- one supervised process per enabled tunnel instance;
- root-only runtime credential files;
- service lifecycle and status presentation;
- publication of configured native FreeBSD `tunN` devices through the
  standard OPNsense virtual-device API;
- integration with the native interface, gateway, routing, firewall and NAT
  subsystems;
- the standard FreeBSD port that builds the unmodified tunnel engine.

The plugin must not implement a second routing or packet-filter engine. It
registers the TUN devices and lets the standard OPNsense components apply
administrator-selected network policy. Packaging must not fork protocol logic:
the port pins a reviewed `usque-rs-bsd` commit and builds it through the
FreeBSD Cargo framework.

## Instance model

Every instance has an OPNsense UUID, a unique display name, a unique native
FreeBSD `tunN` interface name and exactly one role:

- `client` for egress;
- `mesh-node` for ingress.

Separate configuration and state directories prevent one instance from
overwriting or controlling another. Both roles may run concurrently.

## Runtime layout

```text
/usr/local/etc/usque/instances/<uuid>.json   mode 0600
/usr/local/etc/usque/instances.json           non-secret generated manifest
/var/run/usque/<uuid>.supervisor.pid          locked daemon(8) supervisor PID
/var/run/usque/<uuid>.child.pid               locked Rust child PID
syslog tag usque-tunN                         tunnel process output
```

The instance credential path is created by enrollment and is never copied into
the OPNsense model or generated manifest. FreeBSD `daemon(8)` owns PID locking,
crash supervision and syslog delivery; OPNsense owns boot ordering and
configuration reconciliation through rc.d and configd.

## OPNsense layers

1. MVC model and API validate persistent configuration.
2. Jinja templates materialize bounded per-instance runtime inputs.
3. Configd exposes fixed privileged actions.
4. The rc.d service starts one `daemon(8)` supervisor per enabled instance.
5. A device hook publishes configured `tunN` names to OPNsense while tun-rs
   remains the sole owner of device creation and addressing.
6. OPNsense core handles assignment, gateway, policy routing, firewall and NAT.

## TUN ownership and persistent assignments

The lifecycle worker creates a root-owned mode-0600
`/var/run/usque/<uuid>.state.json` before starting an instance. This records
only the validated `tunN` name and is the authority required for cleanup. A
stop first validates and terminates the recorded daemon supervisor and Rust
child, then destroys only that owned cloned interface. Unsafe, missing or
malformed state never authorizes destruction.

OPNsense persists an interface assignment by device name independently of the
kernel object's lifetime. The usque device hook continues publishing stable
`tunN` names while stopped, matching WireGuard's volatile-device lifecycle.

No controller may interpolate unvalidated values into a shell command. Configd
parameters will be restricted to instance UUIDs and resolved server-side.

## Status semantics

Process state, TUN existence and Cloudflare session state are different facts.
The future UI must not label a tunnel connected merely because its process is
running. The existing `usque-nativetun` connect/disconnect hooks may provide
the first implementation. A small machine-readable runtime status interface
may later be added to the Rust project if hooks cannot represent shutdown and
reconnection accurately.

## Enrollment privilege boundary

Browser enrollment is intentionally split across three trust levels:

```text
authenticated MVC API (www)
  -> random /var/tmp handoff (0600, token, <= 5 minutes)
  -> configd action (job UUID + tunnel UUID only)
  -> root enrollment worker
  -> root-owned JWT file (0600)
  -> usque-nativetun --jwt-file
  -> /usr/local/etc/usque/instances/<uuid>.json (0600)
```

The worker opens the browser handoff with `O_NOFOLLOW`, validates its owner,
mode, regular-file type, link count, size and age, then unlinks it regardless of
success. State files contain only the job state, bounded diagnostics and the
tunnel UUID. The callback token, registration access token and private P-256
key are never returned through the plugin API.

Registration availability is also resolved by the root worker. It opens the
per-instance configuration with `O_NOFOLLOW`, verifies owner-only metadata and
the client role, and returns booleans only. The web process never reads or
returns the credential-bearing JSON.

This workflow applies only to the `client` role. Mesh connector registration
continues to use its separate Cloudflare-generated token-file workflow.

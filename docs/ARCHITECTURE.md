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

The service command is role-specific: `client` maps to `nativetun`, and
`mesh-node` maps to the Rust `mesh-node` subcommand. Mesh omits the redundant
`--always-reconnect` flag because the Rust Mesh role maintains its edge session.

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
## Mesh return-path ownership

Cloudflare's default Mesh Device IP networks are `100.96.0.0/12` and
`2606:4700:cf1:1000::/64`. Per ingress Mesh instance, return-route management
is enabled by default with those values. An operator may disable it completely,
or provide deployment-specific canonical IPv4 and IPv6 CIDRs; an empty family
is intentionally omitted. The root lifecycle worker strictly parses each CIDR
and uses the native FreeBSD `route(8) -interface` form only after the Rust Mesh
command has created the device. A node that publishes a downstream network
needs the applicable return routes through its TUN so replies do not follow the
WAN default route.

The routes are limited to the Mesh role. Each is recorded after a successful
add in the same private runtime state as the TUN. During shutdown the worker
verifies the FIB resolves the exact route through the recorded interface and
removes only such a match before destroying the TUN. Routes replaced outside
the plugin are not deleted. This implementation neither configures NAT nor
takes ownership of firewall, policy-routing, gateway, or general static routes.

parameters will be restricted to instance UUIDs and resolved server-side.

## Status semantics

Process state, TUN existence and Cloudflare session state are different facts.
The future UI must not label a tunnel connected merely because its process is
running. The existing `usque-nativetun` connect/disconnect hooks may provide
the first implementation. A small machine-readable runtime status interface
may later be added to the Rust project if hooks cannot represent shutdown and
reconnection accurately.

## Enrollment privilege boundary

All enrollment workflows are intentionally split across three trust levels:

```text
authenticated MVC API (www)
  -> random /var/tmp handoff (0600, <= 5 minutes)
  -> configd action (job UUID + tunnel UUID only)
  -> root enrollment worker
  -> browser/Mesh: root-owned token file (0600)
     or service token: XML-escaped root-owned MDM file (0600)
  -> usque-nativetun --jwt-file, --mdm-file, or mesh-register --token-file
  -> /usr/local/etc/usque/instances/<uuid>.json (0600)
```

The worker opens the browser handoff with `O_NOFOLLOW`, validates its owner,
mode, regular-file type, link count, size and age, then unlinks it regardless of
success. State files contain only the job state, bounded diagnostics and the
tunnel UUID. The callback token, registration access token and private P-256
key are never returned through the plugin API.

Registration availability is also resolved by the root worker. It opens the
per-instance configuration with `O_NOFOLLOW`, verifies owner-only metadata and
the selected role, and returns booleans only. The web process never reads or
returns the credential-bearing JSON.

The client role accepts either the browser callback/JWT workflow or Cloudflare's
documented `organization`, `auth_client_id` and `auth_client_secret` MDM
parameters. Service-token secrets cross the privilege boundary only in a
bounded one-use JSON handoff, then a root-only XML-escaped MDM file; neither is
stored in the model, command arguments or resulting client configuration. The
Mesh role accepts
only a Cloudflare-generated connector token and requires explicit ToS and Linux
platform-claim acknowledgements before the existing Rust Mesh registration
command is invoked. Neither path stores its one-time input in the MVC model.

Tunnel deletion uses the lifecycle worker's shared exclusive lock. It is
allowed only after the persistent global service setting is disabled, the
generated manifest is disabled, no managed PID is live and no TUN ownership
state remains. The root worker reopens and validates the role-specific
credential, then verifies its inode immediately before unlinking it. Only after
that succeeds does the MVC controller remove the tunnel row. OPNsense interface
assignments and network policy are intentionally outside this deletion.

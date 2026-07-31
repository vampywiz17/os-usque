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
- registration of `usqueN` devices with OPNsense;
- integration with the native interface, gateway, routing, firewall and NAT
  subsystems.

The plugin must not implement a second routing or packet-filter engine. It
registers the TUN devices and lets the standard OPNsense components apply
administrator-selected network policy.

## Instance model

Every instance has an OPNsense UUID, a unique display name, a unique `usqueN`
interface name and exactly one role:

- `client` for egress;
- `mesh-node` for ingress.

Separate configuration and state directories prevent one instance from
overwriting or controlling another. Both roles may run concurrently.

## Planned runtime layout

```text
/usr/local/etc/usque/instances/<uuid>.json   mode 0600
/var/run/usque/<uuid>.pid
/var/run/usque/<uuid>.state.json
/var/log/usque/<uuid>.log
```

These paths are design targets, not yet created by the scaffold.

## OPNsense layers

1. MVC model and API validate persistent configuration.
2. Jinja templates materialize bounded per-instance runtime inputs.
3. Configd exposes fixed privileged actions.
4. An rc.d-compatible supervisor starts one process per enabled instance.
5. Plugin device registration exposes `usqueN` interfaces to OPNsense.
6. OPNsense core handles assignment, gateway, policy routing, firewall and NAT.

No controller may interpolate unvalidated values into a shell command. Configd
parameters will be restricted to instance UUIDs and resolved server-side.

## Status semantics

Process state, TUN existence and Cloudflare session state are different facts.
The future UI must not label a tunnel connected merely because its process is
running. The existing `usque-nativetun` connect/disconnect hooks may provide
the first implementation. A small machine-readable runtime status interface
may later be added to the Rust project if hooks cannot represent shutdown and
reconnection accurately.

# os-usque

Experimental OPNsense 26.7 integration for
[`usque-rs-bsd`](https://github.com/vampywiz17/usque-rs-bsd).

The intended deployment supports two independent, tunnel-only roles:

- **Egress client:** selected OPNsense networks use a Cloudflare
  MASQUE/CONNECT-IP TUN interface for Internet egress.
- **Ingress Mesh node:** authorized Cloudflare Mesh devices reach networks
  published behind OPNsense.

Multiple instances of either role are an explicit design requirement. Routing,
policy routing, gateways, NAT and packet-filter policy remain owned by
OPNsense. The Rust client remains responsible only for registration, the TUN
interface and its standards-based QUIC/MASQUE data plane.

> [!WARNING]
> This repository is an early development scaffold. It does not yet start a
> tunnel and must not be installed on a production firewall.

## Repository boundary

This repository contains the OPNsense plugin, its packaging metadata, tests and
OPNsense-specific integration code. Changes to the underlying Rust client
belong in
[`vampywiz17/usque-rs-bsd`](https://github.com/vampywiz17/usque-rs-bsd).

The plugin source is kept at `security/usque`, matching its eventual location
inside the official `opnsense/plugins` tree. OPNsense does not accept
precompiled service binaries inside plugins. The plugin therefore depends on
the separately built `usque-nativetun` package:

```make
PLUGIN_DEPENDS= usque-nativetun
```

Its standard FreeBSD port lives at `ports/security/usque-nativetun`. The port
uses the official Cargo ports framework, an exact source commit, a committed
Cargo lockfile and checksummed crate distfiles. No tunnel, QUIC, MASQUE or TUN
behavior is patched for OPNsense packaging.

## Quick validation

Portable structural checks:

```sh
make validate
```

Prepare local copies of the official OPNsense 26.7 plugin framework:

```sh
make prepare
```

Prepare, verify and package the Rust FreeBSD port on FreeBSD:

```sh
make ports-prepare
make port-check
make port-package
```

On an OPNsense/FreeBSD development host with the package installed and the
required PHP tooling:

```sh
make lint
make style
make package
```

The build helpers operate only below the ignored `.build/` directory and never
modify `/usr/plugins` or `/usr/ports`. See
[development setup](docs/DEVELOPMENT.md), [port packaging](docs/PORTING.md),
and [architecture](docs/ARCHITECTURE.md) before contributing.

## Project status

The current foundation contains:

- OPNsense-compatible package metadata;
- an MVC model for global settings and multiple role-separated instances;
- menu and ACL declarations;
- a read-only foundation page;
- native plugin registration for future `usqueN` TUN interfaces;
- pinned OPNsense 26.7 validation and packaging helpers;
- a reproducible, checksummed FreeBSD port for `usque-nativetun` 0.7.0.

Service execution, credential enrollment, generated runtime configuration,
interface assignment automation and routing integration are deliberately not
implemented yet.

## Independence and truthful operation

This is an independent interoperability project. It is not affiliated with,
endorsed by or reviewed by Cloudflare or OPNsense. It does not claim to be an
official Cloudflare client and must only report truthful runtime information.
Cloudflare product names and trademarks belong to Cloudflare, Inc.

The experimental FreeBSD Mesh mode has additional unsupported-platform and
account-enforcement risks documented by `usque-rs-bsd`. Operators must review
that project's legal and protocol-source notices before enabling Mesh mode.

## License

The OPNsense plugin is licensed under the BSD 2-Clause License, matching the
OPNsense plugin contribution requirement. The underlying Rust program remains
under its own MIT license.

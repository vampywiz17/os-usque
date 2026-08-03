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
> This repository is under active development. Enrollment, service lifecycle
> and the required default Mesh return routes are implemented. General
> policy-routing integration is not production-ready.

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

## Installation from a release

Release assets are built for **OPNsense 26.7 / FreeBSD 15 amd64** only. Download
both packages from the matching GitHub release and copy them to the firewall,
for example to `/tmp`. The native tunnel package must be installed before the
plugin:

```sh
pkg install -f /tmp/usque-nativetun-0.8.1.pkg
pkg install -f /tmp/os-usque-0.2_16.pkg
service configd restart
```

Then open **VPN -> usque** in the OPNsense web interface. Create and register an
egress client or an ingress Mesh node, enable the service and instance, and
choose **Apply changes**. The package installation does not create routes,
gateways, firewall rules, NAT or interface assignments automatically; those
remain explicit OPNsense administrator actions.

Before upgrading either package, disable the usque service and choose **Apply
changes** so the managed TUN processes stop cleanly. Install the updated native
package first, then the plugin package, and restart `configd` as shown above.

These are experimental packages. Do not install them on another OPNsense major
version or FreeBSD ABI.

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
- a native tunnel CRUD page, browser-assisted egress enrollment and explicit
  connector-token Mesh registration workflows;
- configured native FreeBSD `tunN` interfaces published through the standard
  OPNsense virtual-device hook;
- native rc.d/configd lifecycle management with one supervised FreeBSD
  `daemon(8)` process per enabled instance;
- an Apply action that renders runtime metadata and reconciles all instances;
- pinned OPNsense 26.7 validation and packaging helpers;
- a reproducible, checksummed FreeBSD port for `usque-nativetun` 0.8.1.

Interface assignment automation and Mesh return-route reconciliation are implemented. Both enrollment paths create the root-only per-instance configuration.

## Mesh return routes

Cloudflare Mesh clients use the configured Device IP ranges. Each ingress Mesh
instance enables return-route management by default and starts with Cloudflare's
currently known ranges: `100.96.0.0/12` and `2606:4700:cf1:1000::/64`.
Operators can disable this management when OPNsense owns routing elsewhere, or
replace either CIDR with the network assigned to that Mesh deployment. Leaving
one family empty intentionally omits that family. These controls are shown only
for the ingress Mesh role; egress client dialogs do not expose irrelevant
routing settings. Every configured CIDR is strictly parsed before the lifecycle
worker can call FreeBSD `route(8)`.

After a **Mesh node** is ready, the plugin installs these native FreeBSD
`route(8) -interface` routes. They use the point-to-point TUN name rather
than a synthetic peer gateway, so they remain valid if Cloudflare changes the
assigned tunnel address. Egress client instances never receive these routes.

Each successful route is recorded in the root-only runtime ownership state.
When the instance stops, the plugin first confirms the exact route still
resolves to its recorded `tunN`, then removes it before destroying the
interface. A route that was changed outside the plugin is left untouched.

The default Device IP ranges have one route target per FreeBSD FIB. Do not
start two Mesh nodes using the same default ranges in the same FIB; use a
deliberately separate routing design for that advanced topology. Firewall,
NAT, gateways, and policy routing remain administrator-owned OPNsense policy.

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

## Browser-assisted egress enrollment

The tunnel list stores only non-secret metadata, including the Cloudflare Zero
Trust team subdomain. Registration follows the documented team enrollment flow:

1. Select an egress client instance and open the generated
   `https://<team>.cloudflareaccess.com/warp` URL.
2. Authenticate using the organization's Cloudflare Access identity provider.
3. Paste the resulting `com.cloudflare.warp://.../auth?token=...` callback URI
   into the enrollment dialog.
4. Explicitly accept the Cloudflare Application Terms and start registration.
5. The UI polls a non-secret asynchronous job state until registration completes.

The browser receives no device private key. The PHP controller writes the
one-time token to a random owner-only handoff file and passes only random job
and tunnel UUIDs to configd. The root worker claims that file with
`O_NOFOLLOW`, validates type, link count, owner, mode, size and a five-minute
TTL, deletes the handoff, and invokes `usque-nativetun --jwt-file`. Tokens are
never stored in `config.xml`, command arguments, logs, state responses or the
resulting plugin model. The per-instance Rust configuration is mode `0600`.

When an egress row is selected, the UI asks the root worker whether its
owner-only configuration exists and is valid. A registered or blocked instance
keeps the enrollment button disabled; the API never returns configuration
contents or credentials.

Cloudflare's custom protocol normally launches the official desktop client.
OPNsense does not register or imitate that protocol handler; the one-time
callback is pasted back manually. A fully automatic HTTPS callback should only
be added if Cloudflare documents a third-party redirect mechanism.

## Mesh node registration

Select an ingress Mesh instance and choose **Register selected Mesh node**.
Paste the Cloudflare connector token generated for that node, then explicitly
accept both the Cloudflare Application Terms and the unsupported-platform
acknowledgement. The plugin invokes the existing
`usque-nativetun mesh-register --token-file` interface with the required
`--acknowledge-linux-platform-claim` flag; it does not reimplement the
Cloudflare protocol or alter the Rust tunnel engine.

Cloudflare currently documents Mesh nodes for its Linux client. The independent
FreeBSD implementation therefore makes a disclosed Linux compatibility claim
only after explicit operator acknowledgement. It does not claim to be the
official client. Cloudflare may detect, reject, restrict or sanction its use;
the operator assumes that risk and the authors accept no liability for account
or service action.

The connector token uses the same bounded, one-use, mode-0600 handoff and root
worker boundary as egress enrollment. It is never written to `config.xml`,
command arguments, application logs or asynchronous status files. The plugin
does not create Cloudflare routes or OPNsense policy automatically.

## Service lifecycle

Enable the service and each registered instance, then choose **Apply changes**.
The plugin renders a non-secret instance manifest and reconciles the
running processes. Every instance is launched by FreeBSD `daemon(8)` with
separate supervisor and child PID files, a five-second crash restart delay and
the Rust client's own `--always-reconnect` transport recovery. Output is sent
to the OPNsense system log under an instance-specific `usque-tunN` syslog tag.

The generated manifest contains only UUIDs, names, roles and TUN interface
names. Registration credentials remain in root-owned mode-0600 files under
`/usr/local/etc/usque/instances`. The lifecycle worker revalidates ownership,
permissions, link count, size, role, UUID and native `tunN` naming before a
process is started.

Stop any manually launched `usque-nativetun` process before applying the
plugin configuration. An existing `tunN` interface without the plugin's
private runtime ownership record is rejected rather than taken over. The
service records each managed interface in a root-owned mode-0600 state file,
stops its validated supervisor and child, and then destroys only that recorded
cloned TUN device.

The lifecycle worker maps roles to the Rust CLI explicitly: egress instances
run the `nativetun` subcommand with `--always-reconnect`, while ingress
instances run the self-maintaining `mesh-node` subcommand.

OPNsense interface assignments are persistent configuration keyed by the
stable `tunN` name. Destroying the runtime device during a stop does not delete
its assignment; it is temporarily down and reconnects when tun-rs recreates
the same name. This follows OPNsense's WireGuard lifecycle. Routes bound to the
interface disappear while it is down. Gateway, policy-routing, firewall and
NAT configuration remain explicit OPNsense administrator actions.

Applying the configuration also writes `/etc/rc.conf.d/usque`, so enabled
instances are restored by the normal FreeBSD rc order during boot.

Before deleting any tunnel row, disable the global usque service and choose
**Apply changes**. The API and root worker both enforce this condition. The
worker also refuses deletion while a managed PID or TUN ownership state exists.
After validating the UUID, role, ownership, permissions, link count and inode,
deleting the row removes its matching private registration JSON. This prevents
orphaned credentials while ensuring a running service cannot lose the
configuration it is using. Interface assignments remain separate OPNsense
configuration and are not removed implicitly.

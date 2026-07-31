# FreeBSD package

The OPNsense plugin never embeds a precompiled executable. Its
`usque-nativetun` dependency is built from source by the standard FreeBSD ports
framework under `ports/security/usque-nativetun`.

The port is pinned to an exact `usque-rs-bsd` Git commit and uses the committed
`Cargo.lock`. `Makefile.crates` and `distinfo` are generated from that lockfile,
so Cargo builds with vendored, checksummed crates and does not access the
network during compilation.

## Build

On a supported FreeBSD build host:

```sh
make ports-prepare
make port-check
make port-package
```

`port-check` runs checksum validation, a staged build, stage QA, plist checking,
and `portfmt`/`portclippy` when those tools are installed. `port-package`
produces the standard FreeBSD package in the disposable ports work directory.

The default ports branch is `master`, matching the OPNsense 26.7 tools
configuration. A release builder can pin a reviewed ports commit:

```sh
OPNSENSE_PORTS_REF=<commit> make port-check
```

## Updating the Rust source pin

1. Commit and test the new `Cargo.lock` in `usque-rs-bsd`.
2. Update `GH_TAGNAME` to the reviewed source commit.
3. Overlay the port with `make ports-prepare`.
4. In the overlaid port, run `make clean makesum`, then `make cargo-crates`.
5. Copy the generated `distinfo` and crate list back to this repository.
6. Run `make port-check` and `make port-package`.

Do not manually add arbitrary crates or fetch dependencies during the build.
Do not change the Rust tunnel engine merely to accommodate plugin packaging.

## Verified baseline

The initial port was built on FreeBSD 15.0 amd64 with Rust 1.96.1. It passed
checksum, stage QA, plist, and package creation checks. The resulting stripped
PIE executable linked only to FreeBSD base-system libraries and reported
`usque-nativetun` 0.7.0 with both native TUN client and optional Mesh node
modes.

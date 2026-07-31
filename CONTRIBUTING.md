# Contributing

Keep the boundary between the two projects explicit:

- OPNsense MVC/API, configd, rc.d, interface, routing and packaging work belongs
  here.
- QUIC, MASQUE, Cloudflare registration, TUN packet handling and portable
  runtime behavior belong in `usque-rs-bsd`.

The FreeBSD port in this repository must package a reviewed, pinned
`usque-rs-bsd` commit without carrying protocol or runtime behavior patches.
Changes to Cargo dependencies require a committed and tested upstream
`Cargo.lock`, regenerated crate metadata, and a full FreeBSD port check.

New plugin code must follow the OPNsense 26.7 MVC/API and configd architecture.
Web API controllers must not run privileged commands directly. Backend scripts
must not read or modify `config.xml`; configuration is supplied through the
OPNsense model and template systems.

Before submitting portable or plugin-only changes, run:

```sh
make validate
make prepare
make lint
make style
```

For port or Rust source-pin changes, also run on FreeBSD:

```sh
make ports-prepare
make port-check
make port-package
```

Do not commit credentials, generated registration files, tokens, private keys,
build trees or packages. AI-assisted contributions must disclose the tool and
model when submitted upstream, as required by the OPNsense contribution guide.

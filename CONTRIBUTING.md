# Contributing

Keep the boundary between the two projects explicit:

- OPNsense MVC/API, configd, rc.d, interface, routing and packaging work belongs
  here.
- QUIC, MASQUE, Cloudflare registration, TUN packet handling and portable
  runtime behavior belong in `usque-rs-bsd`.

New plugin code must follow the OPNsense 26.7 MVC/API and configd architecture.
Web API controllers must not run privileged commands directly. Backend scripts
must not read or modify `config.xml`; configuration is supplied through the
OPNsense model and template systems.

Before submitting changes, run:

```sh
make validate
make prepare
make lint
make style
```

Do not commit credentials, generated registration files, tokens, private keys,
build trees or packages. AI-assisted contributions must disclose the tool and
model when submitted upstream, as required by the OPNsense contribution guide.

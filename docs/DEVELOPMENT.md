# OPNsense 26.7 development

## Supported baseline

- OPNsense ABI: `26.7`
- Plugin and core framework branches: `stable/26.7`
- OPNsense release runtime: FreeBSD 15.1, PHP 8.5 and Python 3.13
- Official full image build host baseline: FreeBSD 14.3

The lightweight workflow below validates and packages one plugin. A full
OPNsense release build should use the official `opnsense/tools` repository and
its `config/26.7` configuration.

## Portable checks

`scripts/validate.sh` checks repository layout, XML syntax, PHP syntax when PHP
is installed, Python syntax when Python is installed and POSIX shell syntax.

## Framework checkout

Run:

```sh
make prepare
```

This clones or refreshes the following disposable checkouts:

```text
.build/opnsense-plugins
.build/core
```

Both are pinned to `stable/26.7`. The core checkout is required because the
plugin framework delegates its current lint and style targets to `core/Mk`.
The helper then overlays `security/usque` into the plugin checkout.

Override the checkout locations or refs if needed:

```sh
OPNSENSE_PLUGINS_DIR=/safe/path/plugins \
OPNSENSE_CORE_DIR=/safe/path/core \
OPNSENSE_PLUGINS_REF=stable/26.7 \
OPNSENSE_CORE_REF=stable/26.7 \
make prepare
```

The destinations must be dedicated checkouts. The script refuses to replace an
existing `security/usque` directory that it did not previously mark as managed.

## OPNsense-native lint and package

On OPNsense 26.7 or a compatible FreeBSD development host:

```sh
make prepare
make lint
make style
```

The framework receives:

```text
PLUGIN_ABI=26.7
PLUGIN_PHP=85
PLUGIN_PYTHON=313
```

Package creation additionally requires an installed package named
`usque-nativetun`:

```sh
pkg info usque-nativetun
make package
```

No precompiled Rust binary is copied into the plugin. The dependency must
eventually be provided by a FreeBSD port or an OPNsense package repository.

## Full official build

Follow the official `opnsense/tools` setup on a dedicated FreeBSD build host.
Use `ABI=26.7`, place this plugin at `plugins/security/usque`, add
`security/usque` to `config/26.7/plugins.conf.local`, and make the
`usque-nativetun` port available to the ports build before running the plugins
stage.

The official build downloads and builds a complete OPNsense tree and requires
root access, at least 40 GB of storage and at least 8 GB of memory. This
repository intentionally does not automate that destructive, host-wide setup.

# OPNsense 26.7 development

## Supported baseline

- OPNsense ABI: `26.7`
- Plugin and core framework branches: `stable/26.7`
- OPNsense ports branch: `master`, matching the 26.7 tools configuration
- OPNsense release runtime: FreeBSD 15.1, PHP 8.5 and Python 3.13
- Official full image build host baseline: FreeBSD 14.3

The lightweight workflow below validates and packages one plugin and its Rust
service dependency. A full OPNsense release build should use the official
`opnsense/tools` repository and its `config/26.7` configuration.

## Portable checks

`scripts/validate.sh` checks repository layout, the pinned Cargo port metadata,
XML syntax, PHP syntax when PHP is installed, Python syntax when Python is
installed, and POSIX shell syntax.

## Framework checkouts

Run:

```sh
make prepare
make ports-prepare
```

This creates or refreshes disposable checkouts:

```text
.build/opnsense-plugins
.build/core
.build/opnsense-ports
```

The plugin and core checkouts are pinned to `stable/26.7`. The core checkout is
required because the plugin framework delegates its current lint and style
targets to `core/Mk`. The helpers overlay this repository's plugin and port
into their corresponding official trees.

Override checkout locations or refs if needed:

```sh
OPNSENSE_PLUGINS_DIR=/safe/path/plugins \
OPNSENSE_CORE_DIR=/safe/path/core \
OPNSENSE_PORTS_DIR=/safe/path/ports \
OPNSENSE_PLUGINS_REF=stable/26.7 \
OPNSENSE_CORE_REF=stable/26.7 \
OPNSENSE_PORTS_REF=<reviewed-commit> \
make prepare ports-prepare
```

Destinations must be dedicated checkouts. The scripts refuse to replace
unmanaged `security/usque` or `security/usque-nativetun` directories.

## Rust service package

On a FreeBSD build host:

```sh
make port-check
make port-package
```

The port fetches only checksummed source distfiles, builds through `USES=cargo`,
stages into the ports work directory, runs QA and plist checks, and creates a
normal FreeBSD package. It does not embed a binary in the plugin. See
`docs/PORTING.md` for the source-update procedure.

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

Install the locally built `usque-nativetun` package into the isolated package
build environment before creating the plugin package:

```sh
pkg info usque-nativetun
make package
```

## Full official build

Follow the official `opnsense/tools` setup on a dedicated FreeBSD build host.
Use `ABI=26.7`, place this plugin at `plugins/security/usque`, add
`security/usque` to `config/26.7/plugins.conf.local`, and make the
`usque-nativetun` port available to the ports build before running the plugins
stage.

The official build downloads and builds a complete OPNsense tree and requires
root access, at least 40 GB of storage and at least 8 GB of memory. This
repository intentionally does not automate that destructive, host-wide setup.

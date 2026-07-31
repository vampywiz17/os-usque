#!/bin/sh

set -eu

[ "$#" -eq 1 ] ||
    {
        echo "usage: $0 lint|style|package" >&2
        exit 64
    }

target=$1
case "${target}" in
    lint | style | package)
        ;;
    *)
        echo "unsupported OPNsense target: ${target}" >&2
        exit 64
        ;;
esac

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
plugins_dir=${OPNSENSE_PLUGINS_DIR:-"${repo_dir}/.build/opnsense-plugins"}
plugin_dir="${plugins_dir}/security/usque"

"${repo_dir}/scripts/prepare-opnsense-tree.sh"

if [ "${target}" = package ] && ! pkg info -e usque-nativetun >/dev/null 2>&1; then
    echo "package: required FreeBSD package usque-nativetun is not installed" >&2
    echo "package: OPNsense forbids embedding a precompiled service binary" >&2
    exit 1
fi

make -C "${plugin_dir}" "${target}" \
    PLUGIN_ABI=${OPNSENSE_ABI:-26.7} \
    PLUGIN_PHP=${OPNSENSE_PHP:-85} \
    PLUGIN_PYTHON=${OPNSENSE_PYTHON:-313}

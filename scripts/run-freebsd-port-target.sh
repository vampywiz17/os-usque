#!/bin/sh

set -eu

[ "$#" -eq 1 ] ||
    {
        echo "usage: $0 check|package|clean" >&2
        exit 64
    }

target=$1
case "${target}" in
    check | package | clean)
        ;;
    *)
        echo "unsupported FreeBSD port target: ${target}" >&2
        exit 64
        ;;
esac

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ports_dir=${OPNSENSE_PORTS_DIR:-"${repo_dir}/.build/opnsense-ports"}
port_dir="${ports_dir}/security/usque-nativetun"

"${repo_dir}/scripts/prepare-ports-tree.sh"

case "${target}" in
    check)
        make -C "${port_dir}" checksum
        make -C "${port_dir}" stage DEVELOPER=yes
        make -C "${port_dir}" stage-qa DEVELOPER=yes
        make -C "${port_dir}" check-plist DEVELOPER=yes
        if command -v portfmt >/dev/null 2>&1; then
            portfmt -D "${port_dir}/Makefile"
            portclippy "${port_dir}/Makefile"
        fi
        ;;
    package)
        make -C "${port_dir}" package DEVELOPER=yes
        ;;
    clean)
        make -C "${port_dir}" clean
        ;;
esac

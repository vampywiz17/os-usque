#!/bin/sh

set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
plugin_dir="${repo_dir}/security/usque"
port_dir="${repo_dir}/ports/security/usque-nativetun"

fail()
{
    echo "validate: $*" >&2
    exit 1
}

[ -f "${plugin_dir}/Makefile" ] || fail "missing plugin Makefile"
[ -f "${plugin_dir}/pkg-descr" ] || fail "missing plugin pkg-descr"
[ -f "${port_dir}/Makefile" ] || fail "missing FreeBSD port Makefile"
[ -f "${port_dir}/Makefile.crates" ] || fail "missing generated Cargo crate list"
[ -f "${port_dir}/distinfo" ] || fail "missing FreeBSD port distinfo"
[ -f "${port_dir}/pkg-descr" ] || fail "missing FreeBSD port pkg-descr"

grep -q '^PLUGIN_NAME=.*usque' "${plugin_dir}/Makefile" ||
    fail "PLUGIN_NAME must be usque"
grep -q '^PLUGIN_DEPENDS=.*usque-nativetun' "${plugin_dir}/Makefile" ||
    fail "missing usque-nativetun package dependency"
grep -q 'include "../../Mk/plugins.mk"' "${plugin_dir}/Makefile" ||
    fail "plugin Makefile does not include the OPNsense framework"
grep -q '^USES=.*cargo' "${port_dir}/Makefile" ||
    fail "FreeBSD port must use the ports cargo framework"
grep -Eq '^GH_TAGNAME=.*[0-9a-f]{40}$' "${port_dir}/Makefile" ||
    fail "FreeBSD port source must be pinned to a full Git commit"

find "${repo_dir}" -path "${repo_dir}/.build" -prune -o \
    -type f -name '*.sh' -exec sh -n {} \;

if command -v xmllint >/dev/null 2>&1; then
    find "${plugin_dir}/src" -type f -name '*.xml' -exec xmllint --noout {} \;
else
    echo "validate: xmllint unavailable; XML syntax check skipped" >&2
fi

if command -v php >/dev/null 2>&1; then
    find "${plugin_dir}/src" -type f -name '*.php' -exec php -l {} \;
else
    echo "validate: php unavailable; PHP syntax check skipped" >&2
fi

if command -v python3 >/dev/null 2>&1; then
    find "${plugin_dir}/src" -type f -name '*.py' \
        -exec python3 -m py_compile {} \;
fi

if command -v git >/dev/null 2>&1 &&
    git -C "${repo_dir}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "${repo_dir}" diff --check
fi

echo "validate: portable checks passed"

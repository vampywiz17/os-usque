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
grep -q '^PLIST_FILES=.*bin/usque-nativetun' "${port_dir}/Makefile" ||
    fail "FreeBSD port must install usque-nativetun under /usr/local/bin"
grep -q 'BINARY = Path("/usr/local/bin/usque-nativetun")' \
    "${plugin_dir}/src/opnsense/scripts/OPNsense/Usque/enrollment.py" ||
    fail "enrollment worker binary path does not match the FreeBSD port"
enrollment_worker="${plugin_dir}/src/opnsense/scripts/OPNsense/Usque/enrollment.py"
grep -Fq '"mesh-register"' "${enrollment_worker}" &&
    grep -Fq '"--acknowledge-linux-platform-claim"' "${enrollment_worker}" ||
    fail "Mesh registration must use the existing explicit Rust CLI contract"
grep -Fq 'delete-registration' "${enrollment_worker}" ||
    fail "missing stopped-service credential deletion worker"
grep -Fq '"--mdm-file"' "${enrollment_worker}" ||
    fail "Access service-token registration must use the reviewed Rust MDM file contract"

enrollment_actions="${plugin_dir}/src/opnsense/service/conf/actions.d/actions_usque.conf"
grep -Fq '[mesh_register]' "${enrollment_actions}" ||
    fail "missing configd Mesh registration action"
grep -Fq '[client_service_token_register]' "${enrollment_actions}" ||
    fail "missing configd Access service-token registration action"
grep -Fq '[delete_registration]' "${enrollment_actions}" ||
    fail "missing configd credential deletion action"
grep -Fq 'acknowledge_linux_platform_claim' \
    "${plugin_dir}/src/opnsense/mvc/app/controllers/OPNsense/Usque/Api/EnrollmentController.php" ||
    fail "Mesh registration must require explicit unsupported-platform acknowledgement"

device_hook="${plugin_dir}/src/etc/inc/plugins.inc.d/usque.inc"
[ -f "${device_hook}" ] || fail "missing OPNsense virtual-device hook"
grep -Fq "'pattern' => '^tun[0-9]{1,3}$'" "${device_hook}" ||
    fail "device hook must publish native FreeBSD tunN names"
grep -q "'configurable' => false" "${device_hook}" ||
    fail "tun-rs-owned interfaces must not be IP-configured by the device hook"
grep -q "'names' => \$names" "${device_hook}" ||
    fail "device hook must publish configured instances to Assignments"

settings_api="${plugin_dir}/src/opnsense/mvc/app/controllers/OPNsense/Usque/Api/SettingsController.php"
grep -Fq "getModel()->general->getNodes()" "${settings_api}" ||
    fail "general settings must use singleton model access"
if grep -Fq "getBase('general'" "${settings_api}"; then
    fail "general settings must not use array-item getBase access"
fi

service_view="${plugin_dir}/src/opnsense/mvc/app/views/OPNsense/Usque/index.volt"
grep -Fq "{{ lang._('Apply changes') }}" "${service_view}" ||
    fail "service reconcile action must use state-neutral wording"
if grep -Fqi 'Apply and start tunnels' "${service_view}"; then
    fail "service reconcile action must not imply start-only behavior"
fi
syslog_filter="${plugin_dir}/src/opnsense/service/templates/OPNsense/Syslog/local/usque.conf"
[ -f "${syslog_filter}" ] || fail "missing OPNsense local syslog filter"
grep -Fq 'filter f_local_usque' "${syslog_filter}" ||
    fail "usque syslog filter must use the OPNsense local-filter naming contract"
grep -Fq 'program("^usque-tun[0-9]{1,3}$" type("pcre"))' "${syslog_filter}" ||
    fail "usque syslog filter must accept only validated instance tags"
grep -Fq '"-l", "local3"' "${plugin_dir}/src/opnsense/scripts/OPNsense/Usque/service.py" ||
    fail "usque tunnel output must use the standard VPN syslog facility"
grep -Fq 'url="/ui/diagnostics/log/core/usque"' \
    "${plugin_dir}/src/opnsense/mvc/app/models/OPNsense/Usque/Menu/Menu.xml" ||
    fail "missing OPNsense-native usque log viewer menu entry"
grep -Fq 'ui/diagnostics/log/core/usque/*' \
    "${plugin_dir}/src/opnsense/mvc/app/models/OPNsense/Usque/ACL/ACL.xml" ||
    fail "missing usque log viewer ACL"


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
    find "${plugin_dir}/src" -type f -name '*.py' -exec \
        python3 -c 'import ast, pathlib, sys; ast.parse(pathlib.Path(sys.argv[1]).read_text())' {} \;
    PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s "${plugin_dir}/tests" -p 'test_*.py'
fi

if command -v git >/dev/null 2>&1 &&
    git -C "${repo_dir}" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    git -C "${repo_dir}" diff --check
fi

echo "validate: portable checks passed"

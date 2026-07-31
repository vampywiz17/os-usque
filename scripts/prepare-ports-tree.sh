#!/bin/sh

set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_dir="${repo_dir}/ports/security/usque-nativetun"
ports_dir=${OPNSENSE_PORTS_DIR:-"${repo_dir}/.build/opnsense-ports"}
ports_ref=${OPNSENSE_PORTS_REF:-master}
destination="${ports_dir}/security/usque-nativetun"
marker="${ports_dir}/security/.os-usque-nativetun-managed"

case "${ports_dir}" in
    /*)
        ;;
    *)
        echo "ports-prepare: destination must resolve to an absolute path" >&2
        exit 1
        ;;
esac

if [ ! -d "${ports_dir}/.git" ]; then
    [ ! -e "${ports_dir}" ] ||
        {
            echo "ports-prepare: ${ports_dir} exists but is not a git checkout" >&2
            exit 1
        }
    mkdir -p "$(dirname -- "${ports_dir}")"
    git clone --branch "${ports_ref}" --depth 1 \
        https://github.com/opnsense/ports.git "${ports_dir}"
else
    git -C "${ports_dir}" fetch --depth 1 origin "${ports_ref}"
    git -C "${ports_dir}" checkout --detach FETCH_HEAD
fi

if [ -e "${destination}" ] && [ ! -f "${marker}" ]; then
    echo "ports-prepare: refusing to replace unmanaged ${destination}" >&2
    exit 1
fi

if [ -d "${destination}" ]; then
    find "${destination}" -mindepth 1 -maxdepth 1 -exec rm -rf -- {} +
else
    mkdir -p "${destination}"
fi

(
    cd "${source_dir}"
    tar -cf - .
) | (
    cd "${destination}"
    tar -xf -
)
touch "${marker}"

echo "ports-prepare: OPNsense ports ${ports_ref} tree ready at ${ports_dir}"
echo "ports-prepare: overlaid security/usque-nativetun"

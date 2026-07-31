#!/bin/sh

set -eu

repo_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
source_dir="${repo_dir}/security/usque"
plugins_dir=${OPNSENSE_PLUGINS_DIR:-"${repo_dir}/.build/opnsense-plugins"}
core_dir=${OPNSENSE_CORE_DIR:-"$(dirname -- "${plugins_dir}")/core"}
plugins_ref=${OPNSENSE_PLUGINS_REF:-stable/26.7}
core_ref=${OPNSENSE_CORE_REF:-stable/26.7}
destination="${plugins_dir}/security/usque"
marker="${destination}/.os-usque-managed"

case "${plugins_dir}" in
    /*)
        ;;
    *)
        echo "prepare: plugin destination must resolve to an absolute path" >&2
        exit 1
        ;;
esac

case "${core_dir}" in
    /*)
        ;;
    *)
        echo "prepare: core destination must resolve to an absolute path" >&2
        exit 1
        ;;
esac

clone_or_refresh()
{
    repository=$1
    checkout=$2
    ref=$3

    if [ ! -d "${checkout}/.git" ]; then
        [ ! -e "${checkout}" ] ||
            {
                echo "prepare: ${checkout} exists but is not a git checkout" >&2
                exit 1
            }
        mkdir -p "$(dirname -- "${checkout}")"
        git clone --branch "${ref}" --depth 1 "${repository}" "${checkout}"
    else
        git -C "${checkout}" fetch --depth 1 origin "${ref}"
        git -C "${checkout}" checkout --detach FETCH_HEAD
    fi
}

clone_or_refresh \
    https://github.com/opnsense/plugins.git "${plugins_dir}" "${plugins_ref}"
clone_or_refresh \
    https://github.com/opnsense/core.git "${core_dir}" "${core_ref}"

if [ -e "${destination}" ] && [ ! -f "${marker}" ]; then
    echo "prepare: refusing to replace unmanaged ${destination}" >&2
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

echo "prepare: OPNsense plugin ${plugins_ref} tree ready at ${plugins_dir}"
echo "prepare: OPNsense core ${core_ref} tree ready at ${core_dir}"

#!/bin/bash
if [ -z "$1" ]; then
echo "Usage: $0 <blender_executable> <platform> [...blender args]"
echo "Missing <blender_executable>"
exit 1
fi

if [ -z "$2" ]; then
    echo "Usage: $0 <blender_executable> <platform> [...blender args]"
    echo "Missing <platform>"
    exit 1
fi


set -euo pipefail


SCRIPT_DIR=$( cd -- "$( dirname -- "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )
LOG_FILE="$(pwd)/tmp/dev_log.txt"

BUILD_DIR="$(pwd)/builds"
DEV_REPO_DIR="$(pwd)/tmp/dev_repo"

VALID_PLATFORMS=("windows_x64" "macos_x64" "macos_arm64" "linux_x64" "linux_arm64")

function clear_dir() {
    local glob="${2:-*.zip}"
    for file in "$1"/$glob; do
        if [ ! -f "$file" ]; then continue; fi
        rm -f "$file"
    done
}

echo "" > $LOG_FILE  # Clear log

if [[ -d $BUILD_DIR ]]; then
    echo -e "Clearing old builds...\n"
    clear_dir "$BUILD_DIR" "*.zip"
else
    mkdir -p $BUILD_DIR
fi

echo -e "Regenerating Builds\n"
blend_path="$1"
echo -e "\n\"$SCRIPT_DIR\"/build.sh \"$blend_path\"" >> $LOG_FILE
"$SCRIPT_DIR"/build.sh "$blend_path" >> $LOG_FILE


# Check the given platform
platform="$2"
extension_zip=$(echo $BUILD_DIR/*$2.zip)
if [[ ! -f $extension_zip ]]; then
    echo "Invalid platform! (  $(printf '%s  ' "${VALID_PLATFORMS[@]}"))"
    echo "[File not found: '$extension_zip']"
    exit 1
fi


echo -e "Generating Local Extension Repo\n"
echo >> $LOG_FILE
echo -e "\"$blend_path\" --command extension repo-remove vscode_development" >> $LOG_FILE
"$blend_path" --command extension repo-remove vscode_development >> $LOG_FILE
echo >> $LOG_FILE
echo "\"$blend_path\" --command extension repo-add vscode_development --directory \"$DEV_REPO_DIR\"" >> $LOG_FILE
"$blend_path" --command extension repo-add vscode_development --directory "$DEV_REPO_DIR" >> $LOG_FILE
echo >> $LOG_FILE
echo "\"$blend_path\" --command extension install-file \"$extension_zip\" --repo vscode_development --enable" >> $LOG_FILE
"$blend_path" --command extension install-file "$extension_zip" --repo vscode_development --enable >> $LOG_FILE

shift; shift; # Skip first 2 args in "$@"
echo -e "\n---\n\n"

echo -e "Opening Blender\n"
"$blend_path" $@
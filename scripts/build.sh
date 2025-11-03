#!/bin/bash
if [ -z "$1" ]; then
    echo "Usage: $0 <blender_executable>"
    exit 1
fi

set -euo pipefail

BUILD_DIR="$(pwd)/builds"
if [[ -d $BUILD_DIR ]]; then
    mkdir -p $BUILD_DIR 
else
    rmdir -rf $BUILD_DIR
fi

blend_path="$1"
"$blend_path" --command extension build --source-dir "blend-sanitizer/" --output-dir "$BUILD_DIR" --split-platforms

echo -e "\nSuccessfully built addon to $BUILD_DIR"
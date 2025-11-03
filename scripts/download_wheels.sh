set -euo pipefail

EXTENSION_NAME="blend-sanitizer"

PYTHON_VERSION="3.11"
CV2_VERSION="4.12.0.88"

PLATFORMS=("win_amd64" "manylinux_2_17_x86_64" "manylinux_2_17_aarch64" "macosx_13_0_x86_64" "macosx_13_0_arm64")

WHEELS_DIR="$(pwd)/$EXTENSION_NAME/.wheels"
MANIFEST_FILE="$(pwd)/$EXTENSION_NAME/blender_manifest.toml"

function clear_dir() {
    local glob="${2:-*.zip}"
    for file in "$1"/$glob; do
        if [ ! -f "$file" ]; then continue; fi
        rm -f "$file"
    done
}

echo -e "Fetching Python executable...\n"
python_executable="$(pwd)/.venv/Scripts/python.exe"
if [[ ! -f $python_executable ]]; then
    python_executable="$(pwd)/.venv/bin/python"
    if [[ ! -f $python_executable ]]; then
        echo "Could not find python executable in '$(pwd)/.venv'"
    fi
fi

if [[ -d $WHEELS_DIR ]]; then
    echo -e "Clearing old wheels...\n"
    clear_dir "$WHEELS_DIR" "*.whl"
else
    mkdir -p $WHEELS_DIR
fi

echo -e "Downloading new wheels..."
for platform in "${PLATFORMS[@]}"; do
    echo -e "Downloading opencv-python==$CV2_VERSION for platform $platform..."
    "$python_executable" -m pip download "opencv-python==$CV2_VERSION" --dest $WHEELS_DIR --only-binary=:all: --python-version="$PYTHON_VERSION" --platform="$platform"  -q -q --no-input

    wheel_file="$WHEELS_DIR/opencv_python-$CV2_VERSION"*"$platform*.whl"
    if [ ! -f $wheel_file ]; then
        echo "could not download" $wheel_file
        echo $([[ -f $wheel_file ]])
        exit 1
    fi
done


echo -e "\nAdding wheels to manifest...\n"

# Generate wheel list lines
wheel_lines=""
for f in "$WHEELS_DIR"/*.whl; do
    wheel_lines+="\t\"./.wheels/$(basename "$f")\",\n"
done

# Replace the entire wheels section
awk -v newlist="$wheel_lines" '
BEGIN { in_wheels=0 }
{
    if ($1 == "wheels" && $2 == "=") {
        print "wheels = ["
        printf "%s", newlist
        print "]"
        in_wheels=1
        next
    }
    if (in_wheels && $0 ~ /^\]/) { in_wheels=0; next }
    if (!in_wheels) print
}' "$MANIFEST_FILE" > "$MANIFEST_FILE.tmp"
mv "$MANIFEST_FILE.tmp" "$MANIFEST_FILE"
#!/bin/bash
# Generate a synthetic EXR sequence for Crunchize testing
# Requires: oiiotool (OpenImageIO) and bc

set -e

OUTPUT_DIR="test_data/src/synthetic_plate_v001"
START_FRAME=1001
END_FRAME=1048  # 2 seconds at 24fps
WIDTH=1920
HEIGHT=1080

# Check dependencies
if ! command -v oiiotool &> /dev/null; then
    echo "Error: oiiotool could not be found. Please install OpenImageIO-tools."
    exit 1
fi

if ! command -v bc &> /dev/null; then
    echo "Error: bc (basic calculator) could not be found."
    exit 1
fi

echo "Generating test sequence in $OUTPUT_DIR..."
mkdir -p "$OUTPUT_DIR"

for frame in $(seq $START_FRAME $END_FRAME); do
    # Calculate shifting colors based on frame number using sine waves
    # Normalized to 0.0-1.0 range
    r=$(echo "scale=4; s(($frame - $START_FRAME) * 0.2) * 0.4 + 0.5" | bc -l)
    g=$(echo "scale=4; c(($frame - $START_FRAME) * 0.15) * 0.4 + 0.5" | bc -l)
    b=$(echo "scale=4; s(($frame - $START_FRAME) * 0.1 + 1) * 0.4 + 0.5" | bc -l)

    filename="$OUTPUT_DIR/synthetic_plate_v001.$frame.exr"

    # 1. Create canvas filled with shifting color
    # 2. Add Frame Number (Bottom Right)
    # 3. Add Shot Name (Top Left)
    # 4. Add Moving Box (animation simulation)

    box_x=$(echo "($frame - $START_FRAME) * 30 + 100" | bc)

    oiiotool --create "${WIDTH}x${HEIGHT}" 3 \
        --fill "$r,$g,$b" \
        --text:size=80:x=1500:y=950 "$frame" \
        --text:size=50:x=100:y=100 "SYNTH_010_v001" \
        --box:color=1,1,1:fill=1 "${box_x},500,$(($box_x+100)),600" \
        -o "$filename"

    echo "  Generated: $filename"
done

echo "Success! Created 48 frames at $OUTPUT_DIR"
echo "You can now run a playbook against this path:"
echo "crunchize run playbooks/examples/07_vfx_dailies.yml -e input_pattern=\"$PWD/$OUTPUT_DIR/*.exr\""

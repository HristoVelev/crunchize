#!/usr/bin/env python3
import glob
import logging
import os
import re
import subprocess
import sys

from tqdm import tqdm

# Ensure we can import from the same directory
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

try:
    from exr_proxy import load_config, resolve_mapped_path
except ImportError:
    logging.error(
        "Error: Could not import 'exr_proxy.py'. Make sure it is in the same directory."
    )
    sys.exit(1)


def deduce_sequence_info(files):
    """
    Analyzes a list of files to determine the start frame and the ffmpeg input pattern (e.g. shot.%04d.jpg).
    Returns (start_frame, ffmpeg_pattern_name).
    If a consistent pattern cannot be determined, returns (None, None).
    """
    if not files:
        return None, None

    first_file = sorted(files)[0]
    basename = os.path.basename(first_file)

    # Look for the last sequence of digits before the extension
    # e.g. shot.1001.jpg -> group 1="1001", group 2=".jpg"
    match = re.search(r"(\d+)(\.[^.]+)$", basename)
    if not match:
        # Maybe separated by underscore? shot_1001.jpg
        match = re.search(r"(\d+)(\.[^.]+)$", basename)

    # If simple dot-extension match failed, try stricter regex or just look for digits
    if not match:
        match = re.search(r"(\d+)(?=\.[^\.]+$)", basename)
        if match:
            # Reconstruct parts
            frame_str = match.group(1)
            span = match.span(1)
            prefix = basename[: span[0]]
            suffix = basename[span[1] :]
        else:
            return None, None
    else:
        frame_str = match.group(1)
        prefix = basename[: match.start(1)]
        suffix = basename[
            match.end(1) :
        ]  # This is usually empty if we matched (\.[^.]+)$

    padding = len(frame_str)
    start_frame = int(frame_str)

    # Construct ffmpeg pattern
    # e.g. shot.%04d.jpg
    pattern_name = f"{prefix}%0{padding}d{suffix}"

    return start_frame, pattern_name


def process_sequence(dirname, files, config):
    """
    Generates an MP4 for a single sequence of files in a directory.
    """
    if not files:
        return

    files.sort()
    first_file = files[0]

    # 1. Determine Input Pattern for FFmpeg
    start_frame, pattern_name = deduce_sequence_info(files)
    use_glob = False

    if start_frame is not None:
        ffmpeg_input_path = os.path.join(dirname, pattern_name)
    else:
        # Fallback to glob if we couldn't detect frame number pattern
        logging.warning(
            f"Could not detect frame pattern for {dirname}, using glob *.jpg"
        )
        ffmpeg_input_path = os.path.join(dirname, "*.jpg")
        use_glob = True

    # 2. Determine Output MP4 Path
    # Clean the filename to remove frame number for the base name
    # e.g. shot.1001.jpg -> shot.jpg

    # We use the same regex logic as deduce_sequence_info to identify the frame part
    clean_source_path = first_file
    base = os.path.basename(first_file)
    match = re.search(r"(\d+)(?=\.[^\.]+$)", base)

    if match:
        frame_str = match.group(1)
        base_clean = base.replace(frame_str, "")
        # Cleanup separators (.. -> . , _. -> .)
        base_clean = base_clean.replace("..", ".")
        base_clean = base_clean.replace("_.", ".")
        clean_source_path = os.path.join(dirname, base_clean)

    mp4_config = config.get("mp4", {})
    mp4_mapping = mp4_config.get("path_mapping")

    if not mp4_mapping:
        logging.warning(
            f"No mp4.path_mapping found. Saving alongside JPGs in {dirname}"
        )
        mp4_output = os.path.splitext(clean_source_path)[0] + ".mp4"
    else:
        mp4_output = resolve_mapped_path(
            clean_source_path, mp4_mapping, default_ext=".mp4"
        )

    logging.info(f"Processing sequence: {dirname}")
    logging.info(f"  Input: {ffmpeg_input_path}")
    logging.info(f"  Output: {mp4_output}")

    if os.path.exists(mp4_output):
        logging.info(f"  Skipping MP4 creation: {mp4_output} (File exists)")
        return

    # 3. Construct FFmpeg command
    start_arg = []
    if not use_glob and start_frame is not None:
        start_arg = ["-start_number", str(start_frame)]

    extra_args = []
    if use_glob:
        extra_args = ["-pattern_type", "glob"]

    # Ensure output dir exists
    out_dir = os.path.dirname(mp4_output)
    if out_dir and not os.path.exists(out_dir):
        os.makedirs(out_dir, exist_ok=True)

    cmd = (
        [
            "ffmpeg",
            "-y",  # Overwrite output
        ]
        + start_arg
        + extra_args
        + [
            "-i",
            ffmpeg_input_path,
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-vf",
            "pad=ceil(iw/2)*2:ceil(ih/2)*2",
            "-crf",
            "23",
            mp4_output,
        ]
    )

    logging.info(f"  Command: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True, capture_output=True, text=True)
        logging.info(f"  Successfully created MP4: {mp4_output}")
    except subprocess.CalledProcessError as e:
        logging.error(f"  Error executing ffmpeg for {dirname}:")
        logging.error(e.stderr)


def create_mp4(config_path):
    """
    Creates MP4s for all proxy sequences defined in the config.
    """
    if not os.path.exists(config_path):
        logging.error(f"Error: Config file '{config_path}' does not exist.")
        return False

    config = load_config(config_path)
    if not config:
        return False

    # Check if enabled
    if not config.get("mp4", {}).get("enabled", True):
        logging.info("MP4 generation disabled in config.")
        return True

    # 1. Get original EXR pattern
    input_pattern = config.get("input", {}).get("pattern")
    if not input_pattern:
        logging.error("Error: input.pattern not found in config.")
        return False

    # 2. Resolve where the JPGs are (using EXR->JPG mapping)
    jpg_pattern = resolve_mapped_path(
        input_pattern,
        config.get("path_mapping"),
        config.get("proxy", {}).get("output_dir"),
        default_ext=".jpg",
    )

    if not jpg_pattern:
        logging.error("Error resolving JPG path.")
        return False

    # Handle hash to glob conversion for searching
    glob_pattern = jpg_pattern
    if "#" in jpg_pattern:
        glob_pattern = re.sub(r"#+", "*", jpg_pattern)

    logging.info(f"Scanning for JPGs using pattern: {glob_pattern}")

    files = sorted(glob.glob(glob_pattern))
    if not files:
        logging.error(f"Error: No JPG files found matching {glob_pattern}")
        return False

    # 3. Group files by directory
    sequences = {}
    for f in files:
        dirname = os.path.dirname(f)
        if dirname not in sequences:
            sequences[dirname] = []
        sequences[dirname].append(f)

    logging.info(f"Found {len(sequences)} sequences.")

    # 4. Process each sequence
    for dirname, seq_files in tqdm(
        sequences.items(), desc="MP4 Generation", unit="seq"
    ):
        process_sequence(dirname, seq_files, config)

    return True


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Create MP4 from JPG sequences defined in YAML config."
    )
    parser.add_argument("config_file", help="Path to YAML configuration file.")

    args = parser.parse_args()

    # Simple logging setup if run standalone (batch_proxy configures it otherwise)
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")

    if not create_mp4(args.config_file):
        sys.exit(1)


if __name__ == "__main__":
    main()

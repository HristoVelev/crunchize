#!/usr/bin/env python3
import argparse
import concurrent.futures
import glob
import logging
import os
import re
import sys

from tqdm import tqdm

# Ensure we can import exr_proxy from the same directory
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.append(script_dir)

try:
    from exr_proxy import create_proxy, load_config
    from mp4_proxy import create_mp4
except ImportError:
    print(
        "Error: Could not import helper scripts (exr_proxy.py, mp4_proxy.py). Make sure they are in the same directory."
    )
    sys.exit(1)


def resolve_files(input_pattern):
    """
    Resolves a file pattern (including #### or frame numbers) to a list of files.
    """
    files = []

    if not input_pattern:
        return []

    # Case 1: Hash pattern (e.g., shot.####.exr)
    if "#" in input_pattern:
        # Determine number of hashes
        hash_match = re.search(r"(#+)", input_pattern)
        if not hash_match:
            return []

        hashes = hash_match.group(1)
        num_hashes = len(hashes)

        # Create glob pattern: shot.####.exr -> shot.*.exr
        glob_pattern = input_pattern.replace(hashes, "*")
        candidates = glob.glob(glob_pattern)

        # Regex to verify strict digit count matching the hashes
        prefix, suffix = input_pattern.split(hashes, 1)
        # Escape for regex
        regex_pattern = f"^{re.escape(prefix)}(\\d{{{num_hashes}}}){re.escape(suffix)}$"

        for cand in candidates:
            if re.match(regex_pattern, cand):
                files.append(cand)

    # Case 2: Standard wildcards (e.g., shot.*.exr)
    elif "*" in input_pattern or "?" in input_pattern:
        files = glob.glob(input_pattern)

    # Case 3: Specific file (e.g., shot.1001.exr)
    else:
        # Check for "frame number enclosed by dots" e.g. .1001.
        # Regex: look for .digits. right before the extension or at end
        match = re.search(r"\.(\d+)\.([a-zA-Z0-9]+)$", input_pattern)
        if match:
            # It looks like a sequence file: name.NUMBER.ext
            start_idx = match.start(1)
            end_idx = match.end(1)

            # Create a glob pattern by replacing the digits with *
            glob_pattern = input_pattern[:start_idx] + "*" + input_pattern[end_idx:]

            candidates = glob.glob(glob_pattern)

            # Filter candidates to ensure they match the sequence structure (digits only)
            prefix = input_pattern[:start_idx]
            suffix = input_pattern[end_idx:]

            regex_pattern = f"^{re.escape(prefix)}(\\d+){re.escape(suffix)}$"

            for cand in candidates:
                if re.match(regex_pattern, cand):
                    files.append(cand)

            # If nothing found, fall back to the exact file if it exists
            if not files and os.path.exists(input_pattern):
                files = [input_pattern]

        # If no sequence detected, just check if the specific file exists
        elif os.path.exists(input_pattern):
            files = [input_pattern]

    return sorted(files)


def main():
    parser = argparse.ArgumentParser(
        description="Batch convert EXR sequences to proxies using a YAML configuration."
    )

    parser.add_argument(
        "config_file",
        help="Path to the YAML configuration file.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="List files that would be processed without running the conversion.",
    )

    args = parser.parse_args()

    # Load configuration
    if not os.path.exists(args.config_file):
        print(f"Error: Config file '{args.config_file}' not found.")
        sys.exit(1)

    try:
        config = load_config(args.config_file)
    except Exception as e:
        print(f"Error loading YAML file: {e}")
        sys.exit(1)

    if not config:
        print("Error: Configuration could not be loaded.")
        sys.exit(1)

    # Configure logging
    log_config = config.get("logging", {})
    log_file = log_config.get("log_file", "batch_proxy.log")
    log_file = os.path.expanduser(log_file)

    # Ensure log directory exists
    log_dir = os.path.dirname(log_file)
    if log_dir and not os.path.exists(log_dir):
        os.makedirs(log_dir, exist_ok=True)

    print(f"Logging to: {log_file}")

    logging.basicConfig(
        filename=log_file,
        filemode="w",
        level=logging.INFO,
        format="%(asctime)s - %(levelname)s - %(message)s",
        force=True,
    )

    # Extract input pattern from config
    input_section = config.get("input", {})
    input_pattern = input_section.get("pattern")

    if not input_pattern:
        print("Error: 'input.pattern' not defined in configuration file.")
        sys.exit(1)

    # Resolve files
    files = resolve_files(input_pattern)

    if not files:
        print(f"No files found matching pattern: {input_pattern}")
        sys.exit(1)

    msg = f"Found {len(files)} files to process based on pattern: {input_pattern}"
    print(msg)
    logging.info(msg)

    if args.dry_run:
        print("\n[Dry Run] Files to be processed:")
        for f in files:
            print(f"  - {f}")
        sys.exit(0)

    proxy_config = config.get("proxy", {})
    max_workers = proxy_config.get("threads", 8)

    msg = f"Processing with {max_workers} threads..."
    print(msg)
    logging.info(msg)

    success_count = 0
    fail_count = 0

    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(create_proxy, f, args.config_file): f for f in files
        }

        for future in tqdm(
            concurrent.futures.as_completed(future_to_file),
            total=len(files),
            unit="file",
        ):
            f = future_to_file[future]
            try:
                success = future.result()
                if success:
                    success_count += 1
                else:
                    fail_count += 1
            except Exception as e:
                logging.error(f"Failed to process {f}: {e}")
                fail_count += 1

    print("\n------------------------------------------------")
    print(f"Batch completed.")
    print(f"Successful: {success_count}")
    print(f"Failed:     {fail_count}")

    logging.info(f"Batch completed. Successful: {success_count}, Failed: {fail_count}")

    # Generate MP4 if enabled
    print("\n[MP4 Generation]")
    logging.info("Starting MP4 Generation")
    create_mp4(args.config_file)

    if fail_count > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()

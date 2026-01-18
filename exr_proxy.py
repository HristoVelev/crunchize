#!/usr/bin/env python3
import argparse
import functools
import logging
import os
import subprocess
import sys

import yaml


@functools.lru_cache(maxsize=1)
def load_config(config_path):
    """Load configuration from a YAML file. Cached to avoid repeated IO."""
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"Error loading YAML file '{config_path}': {e}")
        return None


def resolve_mapped_path(
    input_path, mapping_config, fallback_dir=None, default_ext=".jpg"
):
    """
    Resolves the output path based on mapping configuration or fallback directory.
    Creates the output directory if it doesn't exist.
    """
    abs_input = os.path.abspath(input_path)

    mapping_config = mapping_config or {}
    input_anchor = mapping_config.get("input_anchor")
    output_anchor = mapping_config.get("output_anchor")
    mapping_extension = mapping_config.get("extension", default_ext)

    final_output = None

    if input_anchor and output_anchor and input_anchor in abs_input:
        # Use path mapping logic
        new_path = abs_input.replace(input_anchor, output_anchor, 1)
        final_output = os.path.splitext(new_path)[0] + mapping_extension
    elif fallback_dir:
        base_name = os.path.splitext(os.path.basename(input_path))[0] + default_ext
        final_output = os.path.join(fallback_dir, base_name)
    else:
        # Default: Save in the same directory as the input
        final_output = os.path.splitext(input_path)[0] + default_ext

    # Ensure output directory exists
    output_dir_path = os.path.dirname(final_output)
    if not os.path.exists(output_dir_path):
        try:
            os.makedirs(output_dir_path)
        except OSError as e:
            logging.error(f"Error creating output directory '{output_dir_path}': {e}")
            return None

    return final_output


def create_proxy(input_exr, config_path):
    """
    Converts an EXR to a proxy using parameters read directly from the YAML config.

    Args:
        input_exr (str): Path to the input EXR file.
        config_path (str): Path to the YAML configuration file.
    """
    if not os.path.exists(input_exr):
        logging.error(f"Error: Input file '{input_exr}' does not exist.")
        return False

    if not os.path.exists(config_path):
        logging.error(f"Error: Config file '{config_path}' does not exist.")
        return False

    # Load configuration
    params = load_config(config_path)
    if params is None:
        return False

    # Extract OCIO settings
    ocio = params.get("ocio", {})
    ocio_config_path = ocio.get("config_path")
    input_cs = ocio.get("input_space", "ACES2065-1")
    output_cs = ocio.get("output_space", "sRGB - Display")

    if not ocio_config_path or not os.path.exists(ocio_config_path):
        logging.error(
            f"Error: OCIO config file not found or invalid in YAML: {ocio_config_path}"
        )
        return False

    # Extract Proxy settings
    proxy_settings = params.get("proxy", {})
    scale = proxy_settings.get("scale")
    output_dir = proxy_settings.get("output_dir")

    # Determine output filename
    final_output = resolve_mapped_path(
        input_exr, params.get("path_mapping"), output_dir
    )
    if not final_output:
        return False

    if os.path.exists(final_output):
        logging.info(f"Skipping: {final_output} (File exists)")
        return True

    # ---------------------------------------------------------
    # Step 1: Color Convert using ocioconvert
    # ---------------------------------------------------------
    logging.info(f"Converting colorspace ({input_cs} -> {output_cs})...")

    # Arguments: input, src_colorspace, output, dst_colorspace
    cmd_convert = [
        "ocioconvert",
        "--iconfig",
        ocio_config_path,
        input_exr,
        input_cs,
        final_output,
        output_cs,
    ]

    try:
        subprocess.run(cmd_convert, check=True, capture_output=True, text=True)
        logging.info(f"Created proxy: {final_output}")
    except subprocess.CalledProcessError as e:
        logging.error("Error executing ocioconvert:")
        logging.error(e.stdout)
        logging.error(e.stderr)
        return False

    # ---------------------------------------------------------
    # Step 2: Scale using oiiotool (if requested)
    # ---------------------------------------------------------
    if scale is not None:
        logging.info(f"Scaling image by factor of {scale}...")

        scale_percent = f"{scale * 100}%"

        cmd_scale = [
            "oiiotool",
            final_output,
            "--resize",
            scale_percent,
            "-o",
            final_output,
        ]

        try:
            subprocess.run(cmd_scale, check=True, capture_output=True, text=True)
            logging.info(f"Resized proxy saved to: {final_output}")
        except subprocess.CalledProcessError as e:
            logging.error("Error executing oiiotool for scaling:")
            logging.error(e.stdout)
            logging.error(e.stderr)
            return False

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Convert EXR to proxy using parameters from a YAML configuration file."
    )

    parser.add_argument("--exr", required=True, help="Path to input EXR file")
    parser.add_argument(
        "--config", required=True, help="Path to YAML configuration file"
    )

    args = parser.parse_args()

    success = create_proxy(args.exr, args.config)
    if not success:
        sys.exit(1)


if __name__ == "__main__":
    main()

import os
import subprocess
from typing import Any, Dict, List, Optional, Union

from crunchize.tasks.base import BaseTask


class ThumbnailTask(BaseTask):
    """
    Task to generate a thumbnail from a sequence of images.
    It picks a specific frame based on relative coordinates and resizes it using oiiotool.
    """

    def validate_args(self) -> None:
        """
        Validate required arguments.
        """
        # We need an output path for the thumbnail
        if "output_path" not in self.args and "item" not in self.args:
            raise ValueError("ThumbnailTask requires 'output_path' or 'item'.")

        # We need a list of files to pick from
        if "input_files" not in self.args and "item" not in self.args:
            raise ValueError("ThumbnailTask requires 'input_files' or 'item' sequence.")

        existing = self.args.get("existing", "replace")
        if existing not in ["skip", "replace"]:
            raise ValueError(
                f"Invalid value for 'existing': {existing}. Must be 'skip' or 'replace'."
            )

    def run(self) -> Optional[str]:
        """
        Execute the thumbnail generation based on provided sequence.
        """
        item = self.args.get("item")
        input_files = self.args.get("input_files")

        # Sequence Inference: Automatically extract file list from sequence objects.
        if not input_files and isinstance(item, dict) and "files" in item:
            input_files = item["files"]

        # Direct list support.
        if not input_files and isinstance(item, list):
            input_files = item

        if not input_files or not isinstance(input_files, list):
            self.logger.warning("ThumbnailTask received no file list to process.")
            return None

        # Framework path resolution: Resolve string paths from framework items.
        input_files = [
            self._resolve_path_from_item(f, prioritize_file=True)
            for f in input_files
            if f
        ]
        input_files = [f for f in input_files if f]

        if not input_files:
            self.logger.warning("ThumbnailTask could not resolve any input file paths.")
            return None

        # 2. Pick the source frame based on sourcelocation (relative 0.0 to 1.0)
        source_loc = self.args.get("sourcelocation", 0.5)

        # Clamp location between 0 and 1 and pick index
        source_loc = max(0.0, min(1.0, float(source_loc)))
        index = int(len(input_files) * source_loc)

        # Safety check for end of list
        if index >= len(input_files):
            index = len(input_files) - 1

        source_frame = input_files[index]
        self.logger.info(
            f"Picked frame for thumbnail: {source_frame} (Index {index}/{len(input_files)})"
        )

        # Output resolution: Inferred from sequence base_path or framework heuristics.
        output_path = self.args.get("output_path")
        if not output_path:
            if isinstance(item, dict) and "base_path" in item:
                output_path = item["base_path"]
            else:
                output_path = self._resolve_path_from_item(item, prioritize_file=False)

        if not output_path:
            raise ValueError("ThumbnailTask could not determine 'output_path'.")

        output_format = self.args.get("format", "jpg").lstrip(".")

        # Ensure output path has the correct extension
        base, _ = os.path.splitext(output_path)
        output_path = f"{base}.{output_format}"

        # Check if output already exists
        existing = self.args.get("existing", "replace")
        if existing == "skip" and os.path.exists(output_path):
            self.logger.info(f"Skipping thumbnail: {output_path} already exists.")
            return output_path

        # 4. Resolve size (Width in pixels)
        width = self.args.get("size")

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            self.logger.info(f"Creating output directory: {output_dir}")
            if not self.dry_run:
                os.makedirs(output_dir, exist_ok=True)

        # Construct system command for OpenImageIO's oiiotool CLI.
        # Format: oiiotool <source> --resize <Wx0> -o <target>
        cmd = ["oiiotool", source_frame]

        if width:
            cmd.extend(["--resize", f"{width}x0"])

        cmd.extend(["-o", output_path])

        self.logger.info(f"Executing: {' '.join(cmd)}")

        if self.dry_run:
            return output_path

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if result.stdout:
                self.logger.debug(result.stdout)

            self.logger.info(f"Successfully generated thumbnail: {output_path}")
            return output_path

        except subprocess.CalledProcessError as e:
            self.logger.error(f"oiiotool failed with return code {e.returncode}")
            self.logger.error(f"Stderr: {e.stderr}")
            raise RuntimeError(f"Thumbnail generation failed: {e.stderr}")
        except FileNotFoundError:
            self.logger.error(
                "oiiotool command not found. Please ensure OpenImageIO tools are installed."
            )
            raise RuntimeError("oiiotool command not found.")

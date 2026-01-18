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
        if "output_path" not in self.args:
            raise ValueError("ThumbnailTask requires 'output_path'.")

        # We need a list of files to pick from
        if "input_files" not in self.args and "item" not in self.args:
            raise ValueError(
                "ThumbnailTask requires 'input_files' or implicit 'item' list."
            )

        existing = self.args.get("existing", "replace")
        if existing not in ["skip", "replace"]:
            raise ValueError(
                f"Invalid value for 'existing': {existing}. Must be 'skip' or 'replace'."
            )

    def run(self) -> Optional[str]:
        """
        Execute the thumbnail generation.
        """
        # 1. Resolve input files
        # It can be a list passed explicitly or the 'item' if we are in a loop/batch
        input_files = self.args.get("input_files") or self.args.get("item")

        if not isinstance(input_files, list) or not input_files:
            self.logger.warning("ThumbnailTask received no file list to process.")
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

        # 3. Handle output path and format
        output_path = self.args["output_path"]
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

        # 5. Build oiiotool command
        # oiiotool source.exr --resize widthx0 -o thumb.jpg
        # widthx0 tells oiiotool to scale height proportionally
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

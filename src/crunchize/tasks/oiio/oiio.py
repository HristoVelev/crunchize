import os
import subprocess
from typing import Union

from crunchize.tasks.base import BaseTask


class OIIOToolTask(BaseTask):
    """
    Task to process images using OpenImageIO's oiiotool.
    Currently focused on scaling/resizing but supports arbitrary arguments.
    """

    def validate_args(self) -> None:
        """
        Validate required arguments.
        Requires 'output_path' and either 'input_path' or implicit 'item'.
        """
        if "output_path" not in self.args and "item" not in self.args:
            raise ValueError("OIIOToolTask requires 'output_path' or 'item'.")

        if "input_path" not in self.args and "item" not in self.args:
            raise ValueError("OIIOToolTask requires 'input_path' or 'item'.")

        existing = self.args.get("existing", "replace")
        if existing not in ["skip", "replace"]:
            raise ValueError(
                f"Invalid value for 'existing': {existing}. Must be 'skip' or 'replace'."
            )

    def run(self) -> str:
        """
        Execute the oiiotool command based on provided arguments.
        """
        # Resolve input and output paths using the framework's inference heuristics.
        # This allows the task to work seamlessly in implicit pipelines.
        item = self.args.get("item")
        input_path = self.args.get("input_path") or self._resolve_path_from_item(
            item, prioritize_file=True
        )

        # Resolve output path (explicit > inferred)
        output_path = self.args.get("output_path") or self._resolve_path_from_item(
            item, prioritize_file=False
        )

        if not input_path:
            raise ValueError("OIIOToolTask could not determine 'input_path'.")
        if not output_path:
            raise ValueError("OIIOToolTask could not determine 'output_path'.")

        # Check if output already exists
        existing = self.args.get("existing", "replace")
        if existing == "skip" and os.path.exists(output_path):
            self.logger.info(f"Skipping processing: {output_path} already exists.")
            return output_path

        width = self.args.get("width")
        height = self.args.get("height")
        scale = self.args.get("scale")
        extra_args = self.args.get("extra_args", [])

        # Ensure output directory exists
        output_dir = os.path.dirname(output_path)
        if output_dir and not os.path.exists(output_dir):
            self.logger.info(f"Creating output directory: {output_dir}")
            if not self.dry_run:
                try:
                    os.makedirs(output_dir, exist_ok=True)
                except OSError as e:
                    raise RuntimeError(
                        f"Failed to create output directory {output_dir}: {e}"
                    )

        # Build the system command for OpenImageIO's oiiotool CLI.
        cmd = ["oiiotool", input_path]

        # Handle explicit dimensions (width/height).
        if width and height:
            # Fit within width x height and pad to target canvas size (letterboxing).
            cmd.extend(["--fit", f"{width}x{height}", "--canvas", f"{width}x{height}"])
        elif width:
            # Scale proportionally based on target width.
            cmd.extend(["--resize", f"{width}x0"])
        elif height:
            # Scale proportionally based on target height.
            cmd.extend(["--resize", f"0x{height}"])

        # Apply additional scaling if requested (can be used independently or combined).
        if scale:
            # Automatically handle float scales (e.g., 0.5 -> "50%").
            if isinstance(scale, float):
                scale_str = f"{scale * 100}%"
            else:
                scale_str = str(scale)

            cmd.extend(["--resize", scale_str])

        # Add extra arguments (e.g. --colorconvert etc)
        if extra_args:
            if isinstance(extra_args, list):
                cmd.extend(extra_args)
            else:
                cmd.extend(extra_args.split())

        # Specify the output path.
        cmd.extend(["-o", output_path])

        self.logger.info(f"Executing: {' '.join(cmd)}")

        if self.dry_run:
            return output_path

        try:
            # oiiotool often outputs info to stdout, errors to stderr
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            # Log stdout as debug info
            if result.stdout:
                self.logger.debug(result.stdout)

            self.logger.info(f"Successfully processed: {output_path}")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"oiiotool failed with return code {e.returncode}")
            self.logger.error(f"Stderr: {e.stderr}")
            if e.stdout:
                self.logger.error(f"Stdout: {e.stdout}")
            raise RuntimeError(f"oiiotool failed: {e.stderr}")
        except FileNotFoundError:
            self.logger.error(
                "oiiotool command not found. Please ensure OpenImageIO tools are installed and in PATH."
            )
            raise RuntimeError("oiiotool command not found.")

        return output_path

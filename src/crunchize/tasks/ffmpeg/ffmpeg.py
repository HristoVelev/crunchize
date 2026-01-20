import logging
import os
import subprocess
from typing import List, Optional, Union

from crunchize.tasks.base import BaseTask


class FFmpegTask(BaseTask):
    """
    Task to encode video using FFmpeg.

    Supports both image sequence patterns (shot.%04d.jpg) and explicit file lists
    via the FFmpeg concat demuxer.
    """

    def validate_args(self) -> None:
        """
        Validate required arguments.
        """
        if "output_path" not in self.args and "item" not in self.args:
            raise ValueError(
                "FFmpegTask requires 'output_path' or 'item' for inference."
            )

        if (
            "input_path" not in self.args
            and "input_files" not in self.args
            and "item" not in self.args
        ):
            raise ValueError(
                "FFmpegTask requires 'input_path', 'input_files', or 'item'."
            )

        existing = self.args.get("existing", "replace")
        if existing not in ["skip", "replace"]:
            raise ValueError(
                f"Invalid value for 'existing': {existing}. Must be 'skip' or 'replace'."
            )

    def run(self) -> str:
        """
        Execute the FFmpeg command based on provided arguments.
        """
        item = self.args.get("item")
        input_path = self.args.get("input_path")
        input_files = self.args.get("input_files")

        # Sequence Inference: In the simplified model, 'item' is often a sequence object
        # containing a 'files' list and a 'base_path'.
        if not input_files and isinstance(item, dict) and "files" in item:
            input_files = item["files"]

        # If no input is provided, try to infer a single input_path from context.
        if not input_path and not input_files:
            input_path = self._resolve_path_from_item(item, prioritize_file=True)

        # Resolve output path: Prioritize base_path from mapping or inferred output location.
        output_path = self.args.get("output_path")
        if not output_path:
            if isinstance(item, dict) and "base_path" in item:
                output_path = item["base_path"]
            else:
                output_path = self._resolve_path_from_item(item, prioritize_file=False)

        if not output_path:
            raise ValueError("FFmpegTask could not determine 'output_path'.")

        # If input_files contains framework objects, resolve them to actual strings.
        if isinstance(input_files, list):
            input_files = [
                self._resolve_path_from_item(f, prioritize_file=True)
                for f in input_files
                if f
            ]
            input_files = [f for f in input_files if f]

        # Resolve timing: 'fps' is the preferred key, 'framerate' is supported as an alias.
        framerate = self.args.get("fps") or self.args.get("framerate", 24)

        width = self.args.get("width")
        height = self.args.get("height")

        # Container handling: Support overriding the extension (e.g. force .mp4).
        container = self.args.get("container")
        if container:
            container = container.lstrip(".")
            base, _ = os.path.splitext(output_path)
            output_path = f"{base}.{container}"
            self.logger.debug(f"Adjusted output path with container: {output_path}")

        # Check if output already exists
        existing = self.args.get("existing", "replace")
        if existing == "skip" and os.path.exists(output_path):
            self.logger.info(f"Skipping video creation: {output_path} already exists.")
            return output_path

        start_frame = self.args.get("start_frame")
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

        cmd = ["ffmpeg"]

        # Always overwrite by default if replace mode is on.
        if existing == "replace":
            cmd.append("-y")

        # Input Handling Strategy:
        if input_files and isinstance(input_files, list):
            # Use Concat Demuxer: Essential for sequences with non-sequential numbering
            # or mixed sources. We generate a temporary file list for FFmpeg.
            list_file_path = f"{output_path}.filelist.txt"

            if not self.dry_run:
                try:
                    with open(list_file_path, "w") as f:
                        for file_path in input_files:
                            # FFmpeg concat format: file '/path/to/image.jpg'
                            f.write(f"file '{file_path}'\n")
                except IOError as e:
                    raise RuntimeError(f"Failed to create concat file list: {e}")

            self.logger.info(f"Created concat list: {list_file_path}")

            cmd.extend(
                [
                    "-f",
                    "concat",
                    "-safe",
                    "0",
                    "-r",
                    str(framerate),
                    "-i",
                    list_file_path,
                ]
            )

        elif input_path:
            # Standard Pattern: Efficient for large, sequential image sequences (e.g. shot.%04d.exr)
            if start_frame is not None:
                cmd.extend(["-start_number", str(start_frame)])

            # Establishment of timebase before input for image sequences.
            cmd.extend(["-framerate", str(framerate)])
            cmd.extend(["-i", input_path])

        # Output configuration
        codec = self.args.get("codec")

        # Default to libx264 for high compatibility if no codec is provided.
        if (
            not codec
            and not any("-c:v" in arg for arg in extra_args)
            and not any("-vcodec" in arg for arg in extra_args)
        ):
            codec = "libx264"

        if codec:
            cmd.extend(["-c:v", codec])
            # Common default for x264 compatibility
            if codec == "libx264" and not any("-pix_fmt" in arg for arg in extra_args):
                cmd.extend(["-pix_fmt", "yuv420p"])

        # Filter Graph: Scaling and Letterboxing.
        if width or height:
            if width and height:
                # Automatic Letterboxing: Fit image inside target resolution and pad with black bars.
                scale_filter = (
                    f"scale=w={width}:h={height}:force_original_aspect_ratio=decrease,"
                    f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"
                )
            elif width:
                # Fixed Width: Preserve aspect ratio. Use -2 to ensure height is even (H.264 requirement).
                scale_filter = f"scale={width}:-2"
            else:
                # Fixed Height.
                scale_filter = f"scale=-2:{height}"

            cmd.extend(["-vf", scale_filter])

        # Add extra user arguments
        if extra_args:
            if isinstance(extra_args, list):
                cmd.extend(extra_args)
            else:
                # split string? usually list is safer
                cmd.extend(extra_args.split())

        cmd.append(output_path)

        self.logger.info(f"Executing: {' '.join(cmd)}")

        if self.dry_run:
            return output_path

        try:
            # Execute FFmpeg and capture streams to avoid console flooding.
            result = subprocess.run(
                cmd,
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            self.logger.info(f"Successfully created: {output_path}")

            # Cleanup list file if it exists
            if input_files and os.path.exists(f"{output_path}.filelist.txt"):
                os.remove(f"{output_path}.filelist.txt")

        except subprocess.CalledProcessError as e:
            self.logger.error(f"FFmpeg failed with return code {e.returncode}")
            # FFmpeg writes progress/errors to stderr usually
            self.logger.error(f"Stderr: {e.stderr}")
            raise RuntimeError(f"FFmpeg failed: {e.stderr}")
        except FileNotFoundError:
            self.logger.error("ffmpeg command not found in PATH.")
            raise RuntimeError("ffmpeg command not found.")

        return output_path

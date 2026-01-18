import logging
import os
import subprocess
from typing import List, Optional, Union

from crunchize.tasks.base import BaseTask


class FFmpegTask(BaseTask):
    """
    Task to encode video using FFmpeg.
    """

    def validate_args(self) -> None:
        """
        Validate required arguments.
        """
        if "output_path" not in self.args:
            raise ValueError("FFmpegTask requires 'output_path'.")

        # input_path is usually required, but might be implicit if we support list inputs later.
        # For now, require it.
        if "input_path" not in self.args and "input_files" not in self.args:
            raise ValueError("FFmpegTask requires 'input_path' or 'input_files'.")

        existing = self.args.get("existing", "replace")
        if existing not in ["skip", "replace"]:
            raise ValueError(
                f"Invalid value for 'existing': {existing}. Must be 'skip' or 'replace'."
            )

    def run(self) -> str:
        """
        Execute ffmpeg command.
        """
        input_path = self.args.get("input_path")
        input_files = self.args.get("input_files")
        output_path = self.args["output_path"]

        # Resolve fps/framerate (fps takes precedence)
        framerate = self.args.get("fps") or self.args.get("framerate", 24)

        # Support container override
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

        if existing == "replace":
            cmd.append("-y")

        # Input handling
        if input_files and isinstance(input_files, list):
            # If we have a list of explicit files, use the concat demuxer
            # We need to create a temporary file list
            # Note: In a real robust system, we should use tempfile module and cleanup
            # taking simplified approach for clarity, or assuming input_path is preferred.

            # For this implementation, let's assume input_path (pattern) is the primary way
            # and input_files (list) is mapped to a concat list.
            list_file_path = f"{output_path}.filelist.txt"

            if not self.dry_run:
                try:
                    with open(list_file_path, "w") as f:
                        for file_path in input_files:
                            # escapte paths?
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

            # Concat doesn't handle framerate on input easily for image sequences the same way pattern does
            # often need -r before input or filters.
            # Usually users use patterns for image sequences.
            # If input_files is used, assume it's a sequence of video clips or we just force framerate on output.

        elif input_path:
            # Standard pattern or file input
            if start_frame is not None:
                cmd.extend(["-start_number", str(start_frame)])

            # Apply framerate to input for image sequences to establish timebase
            cmd.extend(["-framerate", str(framerate)])
            cmd.extend(["-i", input_path])

        # Output options
        codec = self.args.get("codec")

        # Ensure we use libx264 by default if no codec specified
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
            # Capture output to avoid spamming console, but log if error
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

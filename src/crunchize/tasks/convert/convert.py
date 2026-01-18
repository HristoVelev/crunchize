import os
import subprocess

from crunchize.tasks.base import BaseTask


class ConvertTask(BaseTask):
    """
    Task to convert images using OpenColorIO's ocioconvert command line tool.
    """

    def validate_args(self) -> None:
        """
        Validate that all required arguments are present.
        """
        required = [
            "input_path",
            "output_path",
            "config_path",
            "input_space",
            "output_space",
        ]
        missing = [arg for arg in required if arg not in self.args]

        if missing:
            raise ValueError(
                f"Missing required arguments for ConvertTask: {', '.join(missing)}"
            )

        existing = self.args.get("existing", "replace")
        if existing not in ["skip", "replace"]:
            raise ValueError(
                f"Invalid value for 'existing': {existing}. Must be 'skip' or 'replace'."
            )

        # Basic check for config file existence
        config_path = self.args["config_path"]
        if not os.path.exists(config_path) and not self.dry_run:
            self.logger.warning(f"OCIO config file not found at: {config_path}")

    def run(self) -> str:
        """
        Execute the ocioconvert command.
        """
        input_path = self.args["input_path"]
        output_path = self.args["output_path"]
        config_path = self.args["config_path"]
        input_space = self.args["input_space"]
        output_space = self.args["output_space"]
        output_format = self.args.get("output_format")

        if output_format:
            # Strip dot if present
            output_format = output_format.lstrip(".")
            base, ext = os.path.splitext(output_path)
            if ext.lower() != f".{output_format}".lower():
                output_path = f"{base}.{output_format}"
                self.logger.debug(f"Adjusted output path extension to: {output_path}")

        # Check if output already exists
        existing = self.args.get("existing", "replace")
        if existing == "skip" and os.path.exists(output_path):
            self.logger.info(f"Skipping conversion: {output_path} already exists.")
            return output_path

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

        cmd = [
            "ocioconvert",
            "--iconfig",
            config_path,
            input_path,
            input_space,
            output_path,
            output_space,
        ]

        self.logger.info(f"Executing: {' '.join(cmd)}")

        if self.dry_run:
            return output_path

        try:
            result = subprocess.run(cmd, check=True, capture_output=True, text=True)
            if result.stdout:
                self.logger.debug(result.stdout)

            self.logger.info(f"Successfully converted: {output_path}")

            return output_path

        except subprocess.CalledProcessError as e:
            self.logger.error(f"ocioconvert failed with return code {e.returncode}")
            self.logger.error(f"Stdout: {e.stdout}")
            self.logger.error(f"Stderr: {e.stderr}")
            raise RuntimeError(f"ocioconvert failed: {e.stderr}")
        except FileNotFoundError:
            self.logger.error(
                "ocioconvert command not found. Please ensure OpenColorIO tools are installed and in PATH."
            )
            raise RuntimeError("ocioconvert command not found.")

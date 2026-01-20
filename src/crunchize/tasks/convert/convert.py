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
        # OCIO-specific required parameters
        required = [
            "config_path",
            "input_space",
            "output_space",
        ]
        missing = [arg for arg in required if arg not in self.args]

        # Input and output paths can be explicit or inferred from the framework item
        if "input_path" not in self.args and "item" not in self.args:
            missing.append("input_path")
        if "output_path" not in self.args and "item" not in self.args:
            missing.append("output_path")

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
        item = self.args.get("item")

        # Automatically resolve paths using the framework's inference engine.
        # This allows 'convert' to work seamlessly after 'pathmap'.
        input_path = self.args.get("input_path") or self._resolve_path_from_item(
            item, prioritize_file=True
        )
        output_path = self.args.get("output_path") or self._resolve_path_from_item(
            item, prioritize_file=False
        )

        if not input_path:
            raise ValueError("ConvertTask could not determine 'input_path'.")
        if not output_path:
            raise ValueError("ConvertTask could not determine 'output_path'.")

        config_path = self.args["config_path"]
        input_space = self.args["input_space"]
        output_space = self.args["output_space"]
        output_format = self.args.get("output_format")

        # If a specific format is requested, ensure the file extension is updated.
        # This is vital when converting from .exr to .jpg proxies.
        if output_format:
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

        # Construct the system command for OpenColorIO's CLI tool.
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

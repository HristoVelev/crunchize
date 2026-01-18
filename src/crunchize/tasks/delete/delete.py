import os
from typing import Union

from crunchize.tasks.base import BaseTask


class DeleteTask(BaseTask):
    """
    Task to delete files.
    Can accept 'path' argument or implicit 'item' argument from loop/input.
    """

    def validate_args(self) -> None:
        """
        Validate required arguments.
        Requires either 'path' or 'item' (injected by engine).
        """
        if "path" not in self.args and "item" not in self.args:
            raise ValueError("DeleteTask requires 'path' or implicit 'item'.")

    def run(self) -> Union[str, None]:
        """
        Delete the specified file.
        """
        # Prefer explicit path, fall back to injected item
        target_path = self.args.get("path") or self.args.get("item")

        if not target_path or not isinstance(target_path, str):
            self.logger.warning(
                f"Skipping delete: Invalid path provided ({target_path})"
            )
            return None

        self.logger.info(f"Deleting: {target_path}")

        if self.dry_run:
            return target_path

        try:
            if os.path.exists(target_path):
                os.remove(target_path)
            else:
                self.logger.warning(f"File not found: {target_path}")
        except OSError as e:
            self.logger.error(f"Error deleting file {target_path}: {e}")
            raise

        return target_path

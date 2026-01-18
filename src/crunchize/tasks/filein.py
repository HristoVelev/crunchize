import glob
from typing import List

from crunchize.tasks.base import BaseTask


class FileInTask(BaseTask):
    """
    Task to gather files using glob patterns.
    """

    def validate_args(self) -> None:
        """
        Validate that the required 'pattern' argument is present.
        """
        if "pattern" not in self.args:
            raise ValueError("FileInTask requires a 'pattern' argument.")

    def run(self) -> List[str]:
        """
        Run the glob pattern and return the list of matched files.
        """
        pattern = self.args["pattern"]
        recursive = self.args.get("recursive", False)

        self.logger.info(
            f"Searching for files with pattern: {pattern} (recursive={recursive})"
        )

        # Globbing is safe to run in dry_run as it is read-only
        matches = glob.glob(pattern, recursive=recursive)
        matches.sort()

        self.logger.info(f"Found {len(matches)} files.")

        return matches

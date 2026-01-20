import glob
import logging
import re
from collections import defaultdict
from typing import List

from crunchize.tasks.base import BaseTask


class FileInTask(BaseTask):
    """
    Task to gather files using glob patterns.
    This is typically the entry point for a pipeline.
    """

    def validate_args(self) -> None:
        """
        Validate that the required 'pattern' argument is present.
        """
        if "pattern" not in self.args:
            raise ValueError("FileInTask requires a 'pattern' argument.")

    def run(self) -> List[str]:
        """
        Execute the file discovery based on glob pattern.
        """
        pattern = self.args["pattern"]
        recursive = self.args.get("recursive", False)

        self.logger.info(
            f"Searching for files with pattern: {pattern} (recursive={recursive})"
        )

        # Globbing is safe to run in dry_run as it is a read-only operation.
        matches = glob.glob(pattern, recursive=recursive)
        # Ensure consistent order across different filesystems.
        matches.sort()

        self.logger.info(f"Found {len(matches)} files.")

        if self.dry_run or self.logger.isEnabledFor(logging.DEBUG):
            self.log_sequences(matches)

        return matches

    def _format_ranges(self, frames: List[int]) -> str:
        """
        Format a list of integers into a human-readable range string (e.g. '1001-1005, 1007').
        """
        if not frames:
            return ""
        frames.sort()
        ranges = []
        start = frames[0]
        prev = frames[0]

        for f in frames[1:]:
            if f == prev + 1:
                prev = f
            else:
                if start == prev:
                    ranges.append(str(start))
                else:
                    ranges.append(f"{start}-{prev}")
                start = f
                prev = f

        # Add last range
        if start == prev:
            ranges.append(str(start))
        else:
            ranges.append(f"{start}-{prev}")

        return ", ".join(ranges)

    def log_sequences(self, matches: List[str]) -> None:
        """
        Group discovered files by sequence for informative logging.
        """
        groups = defaultdict(list)
        # Identify standard VFX naming conventions: base + separator + frame + ext.
        pattern = re.compile(r"^(.*?)([._])(\d+)(\.[a-zA-Z0-9]+)$")

        for m in matches:
            match = pattern.match(m)
            if match:
                base, sep, frame, ext = match.groups()
                groups[(base, sep, ext)].append(int(frame))
            else:
                # Non-sequence file
                groups[(m, "", "")].append(None)

        # Sort by base name to present a clean summary in the logs.
        for (base, sep, ext), frames in sorted(groups.items(), key=lambda x: x[0]):
            if frames[0] is None:
                self.logger.info(f"  - {base}")
            else:
                range_str = self._format_ranges(frames)
                self.logger.info(f"  - {base}{sep}[{range_str}]{ext}")

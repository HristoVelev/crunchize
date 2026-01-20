import re
from typing import Any, Dict, Optional, Union

from crunchize.tasks.base import BaseTask


class ParsepathTask(BaseTask):
    """
    Task to extract metadata from file paths or strings using regular expressions.

    Captured named groups are returned as a dictionary and automatically
    registered in the global variable scope under the task's name.
    """

    def validate_args(self) -> None:
        """
        Validate required arguments.
        """
        if "pattern" not in self.args:
            raise ValueError("ParsepathTask requires a 'pattern' argument (regex).")

    def run(self) -> Union[Dict[str, Any], Any]:
        """
        Execute the regex parsing based on provided arguments.
        """
        item = self.args.get("item")

        # Resolve the source string to parse.
        # Prioritize explicit input_path, then fall back to context-aware inference.
        source = self.args.get("input_path")

        if source is None:
            if isinstance(item, str):
                source = item
            elif isinstance(item, dict):
                # Try to find a string path in the dictionary using framework heuristics.
                source = item.get("src") or item.get("dst") or item.get("item") or item.get("input_path")

        if not source or not isinstance(source, str):
            self.logger.warning(
                "ParsepathTask received no valid source string to parse."
            )
            return {}

        pattern_str = self.args["pattern"]

        try:
            # Compile and execute the regular expression.
            regex = re.compile(pattern_str)
            match = regex.search(source)

            if match:
                # Extract named groups as a dictionary.
                # These will be registered as top-level variables by the engine.
                metadata = match.groupdict()
                self.logger.info(f"Successfully parsed metadata: {metadata}")
                return metadata
            else:
                self.logger.warning(
                    f"No match found for pattern '{pattern_str}' in source '{source}'"
                )
                return {}

        except re.error as e:
            self.logger.error(f"Invalid regex pattern: {e}")
            raise ValueError(f"Invalid regex pattern: {e}")

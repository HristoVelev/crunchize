import abc
import logging
from typing import Any, Dict, Union


class BaseTask(abc.ABC):
    """
    Abstract base class for all Crunchize tasks.

    A task is a standalone unit of work that receives arguments and an optional
    input item, and returns a result. Tasks are designed to be chainable and
    aware of the framework's path resolution heuristics.
    """

    def __init__(self, args: Dict[str, Any], dry_run: bool = False):
        """
        Initialize the task.

        Args:
            args: Dictionary of arguments for the task.
            dry_run: If True, the task should log actions but not execute side-effects.
        """
        self.args = args
        self.dry_run = dry_run
        self.logger = logging.getLogger(f"crunchize.tasks.{self.__class__.__name__}")
        self.validate_args()

    @abc.abstractmethod
    def run(self) -> Any:
        """
        Execute the task logic.
        Must be implemented by subclasses.
        """
        pass

    def validate_args(self) -> None:
        """
        Validate arguments passed to the task.
        Subclasses should override this method to check for required arguments
        and raise ValueError if validation fails.
        """
        pass

    def _resolve_path_from_item(self, item: Any, prioritize_file: bool = True) -> str:
        """
        Intelligently resolve a file path from a string or dictionary item.

        This method implements the framework's core path inference heuristics,
        allowing tasks to automatically find their input or output files within
        the current execution context.

        Heuristics order:
        1. If item is a string, return it directly.
        2. Search for explicit keys: 'src', 'path', or 'item' (inputs) or 'dst', 'path', or 'item' (outputs).
        3. Fallback to legacy keys like 'source'.
        4. Look for keys ending in '_file' (inputs) or '_path' (outputs).
        5. If the dictionary contains exactly one string value, use that.
        """
        if isinstance(item, str):
            return item
        if not isinstance(item, dict):
            return ""

        # Phase 1: Prioritize explicit 'src'/'dst' keys for the simplified model.
        # 'src' is favored for inputs, 'dst' for outputs.
        search_keys = ["src", "path", "item"] if prioritize_file else ["dst", "path", "item"]
        for k in search_keys:
            if k in item and isinstance(item[k], str):
                return item[k]

        # Phase 2: Fallback to legacy keys or keys using common naming conventions.
        legacy_keys = ["source"] if prioritize_file else []
        for k in legacy_keys:
            if k in item and isinstance(item[k], str):
                return item[k]

        # Iterate through keys looking for framework-standard suffixes (_file, _path).
        for k, v in item.items():
            if not isinstance(v, str):
                continue
            if prioritize_file and k.endswith("_file"):
                return v
            if not prioritize_file and k.endswith("_path"):
                return v

        # Phase 3: Last resort. If the dictionary contains exactly one string value,
        # we assume it is the intended path.
        string_vals = [v for v in item.values() if isinstance(v, str)]
        if len(string_vals) == 1:
            return string_vals[0]

        return ""

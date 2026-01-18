import abc
import logging
from typing import Any, Dict


class BaseTask(abc.ABC):
    """
    Abstract base class for all Crunchize tasks.
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

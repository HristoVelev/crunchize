import concurrent.futures
import importlib
import logging
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def run_task_wrapper(task_cls, args: Dict[str, Any], dry_run: bool):
    """
    Wrapper function to instantiate and run a task.
    Must be at module level for ProcessPoolExecutor pickling.
    """
    task = task_cls(args, dry_run=dry_run)
    return task.run()


class CrunchizeEngine:
    """
    Core engine for parsing playbooks and executing tasks.
    """

    def __init__(self, playbook_path: str, dry_run: bool = False):
        self.playbook_path = Path(playbook_path)
        self.dry_run = dry_run
        self.logger = logging.getLogger("crunchize.engine")
        self.variables = {}
        self.task_results = {}
        self.playbook = self._load_playbook()

        # Initialize variables from playbook
        if "vars" in self.playbook:
            self.variables.update(self.playbook["vars"])

    def _load_playbook(self) -> Dict[str, Any]:
        """Load and parse the YAML playbook."""
        if not self.playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {self.playbook_path}")

        with open(self.playbook_path, "r") as f:
            try:
                return yaml.safe_load(f)
            except yaml.YAMLError as e:
                raise ValueError(f"Error parsing YAML: {e}")

    def _resolve_variable(
        self, value: Any, context: Dict[str, Any], depth: int = 0
    ) -> Any:
        """
        Recursively substitute {{ variable }} in strings, lists, and dicts.
        """
        if depth > 10:
            self.logger.warning(f"Max recursion depth reached resolving: {value}")
            return value

        if isinstance(value, str):
            # Find all {{ var }} patterns
            pattern = r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}"
            matches = re.findall(pattern, value)

            if not matches:
                return value

            new_value = value
            for var_name in matches:
                if var_name in context:
                    var_val = context[var_name]
                    # If the entire string is just the variable, replace with the variable's value directly
                    # (preserves types like int, list, etc.)
                    if new_value.strip() == f"{{{{ {var_name} }}}}":
                        return self._resolve_variable(var_val, context, depth + 1)

                    # Otherwise cast to string for text interpolation
                    new_value = new_value.replace(f"{{{{ {var_name} }}}}", str(var_val))

                    # Also handle tighter spacing {{var}}
                    new_value = new_value.replace(f"{{{{{var_name}}}}}", str(var_val))
                else:
                    self.logger.warning(f"Variable '{var_name}' not found in context.")

            if new_value != value:
                return self._resolve_variable(new_value, context, depth + 1)

            return new_value

        elif isinstance(value, list):
            return [self._resolve_variable(item, context, depth) for item in value]
        elif isinstance(value, dict):
            return {
                k: self._resolve_variable(v, context, depth) for k, v in value.items()
            }
        else:
            return value

    def _get_task_class(self, task_type: str):
        """
        Dynamically load task class based on type.
        """
        # Convention: module_name -> ClassNameTask
        # e.g. type: 'convert' -> crunchize.tasks.convert.ConvertTask

        module_name = task_type.lower()

        # Heuristic for class name: 'ocio_convert' -> 'OcioConvertTask' or special mapping
        # Let's support explicit mapping or simple CamelCase conversion
        if task_type == "convert":
            class_name = "ConvertTask"
        elif task_type == "filein":
            class_name = "FileInTask"
        elif task_type == "ffmpeg":
            class_name = "FFmpegTask"
        elif task_type == "delete":
            class_name = "DeleteTask"
        elif task_type == "oiio":
            class_name = "OIIOToolTask"
        elif task_type == "pathmap":
            class_name = "PathMappingTask"
        else:
            # Snake case to CamelCase
            class_name = "".join(x.capitalize() for x in task_type.split("_")) + "Task"

        try:
            module = importlib.import_module(f"crunchize.tasks.{module_name}")
            task_class = getattr(module, class_name)
            return task_class
        except (ImportError, AttributeError) as e:
            raise ValueError(
                f"Could not load task type '{task_type}' (Expected class {class_name} in crunchize.tasks.{module_name}): {e}"
            )

    def run(self):
        """Execute the playbook."""
        self.logger.info(f"Starting execution of playbook: {self.playbook_path}")

        tasks_def = self.playbook.get("tasks", [])

        for i, task_def in enumerate(tasks_def):
            name = task_def.get("name", f"Task {i}")
            task_type = task_def.get("type")
            task_args = task_def.get("args", {})
            loop_items = task_def.get("loop", None)
            input_ref = task_def.get("input", None)
            register_var = task_def.get("register")
            batch_mode = task_def.get("batch", False)

            if not task_type:
                self.logger.error(f"Skipping task '{name}': No type specified.")
                continue

            self.logger.info(f"Running task: {name} [{task_type}]")

            try:
                task_cls = self._get_task_class(task_type)
            except ValueError as e:
                self.logger.error(str(e))
                continue

            # Determine items to process from 'input' or 'loop'
            items_to_process = None

            if input_ref:
                # Try to find input in task results (by name)
                if input_ref in self.task_results:
                    items_to_process = self.task_results[input_ref]
                # Try to find input in variables
                elif input_ref in self.variables:
                    items_to_process = self.variables[input_ref]
                else:
                    self.logger.warning(
                        f"Input '{input_ref}' not found in task results or variables."
                    )
            elif loop_items:
                items_to_process = self._resolve_variable(loop_items, self.variables)

            # Store the final result of this task here
            task_output = None

            if items_to_process and isinstance(items_to_process, list):
                if batch_mode:
                    self.logger.info(
                        f"Running task in batch mode with {len(items_to_process)} items."
                    )
                    context = self.variables.copy()
                    resolved_args = self._resolve_variable(task_args, context)
                    resolved_args["items"] = items_to_process

                    self.logger.debug(f"Task '{name}' (Batch) Input: {resolved_args}")

                    try:
                        task_output = run_task_wrapper(
                            task_cls, resolved_args, self.dry_run
                        )
                        self.logger.debug(
                            f"Task '{name}' (Batch) Output: {task_output}"
                        )
                    except Exception as e:
                        self.logger.error(f"Batch task execution failed: {e}")

                else:
                    self.logger.info(
                        f"Parallelizing task over {len(items_to_process)} items."
                    )

                    futures = []
                    # Adjust max_workers as needed, or let it default to CPU count
                    with concurrent.futures.ProcessPoolExecutor() as executor:
                        for item in items_to_process:
                            # Create context for this iteration
                            context = self.variables.copy()
                            context["item"] = item

                            # If item is a dictionary, unpack it into context
                            if isinstance(item, dict):
                                context.update(item)

                            # Resolve arguments with the item context
                            resolved_args = self._resolve_variable(task_args, context)

                            # Inject 'item' into args so tasks can access it directly
                            if (
                                isinstance(resolved_args, dict)
                                and "item" not in resolved_args
                            ):
                                resolved_args["item"] = item

                            futures.append(
                                executor.submit(
                                    run_task_wrapper,
                                    task_cls,
                                    resolved_args,
                                    self.dry_run,
                                )
                            )

                    # Wait for all to complete and collect results
                    loop_results = []
                    for future in futures:
                        try:
                            res = future.result()
                            self.logger.debug(
                                f"Task '{name}' (Parallel Item) Output: {res}"
                            )
                            loop_results.append(res)
                        except Exception as e:
                            self.logger.error(f"Parallel task execution failed: {e}")
                            loop_results.append(None)

                    task_output = loop_results

            else:
                # Single execution
                context = self.variables.copy()
                if items_to_process is not None:
                    context["item"] = items_to_process
                    # If item is a dictionary, unpack it into context
                    if isinstance(items_to_process, dict):
                        context.update(items_to_process)

                resolved_args = self._resolve_variable(task_args, context)

                # Inject 'item' into args if we have one
                if (
                    items_to_process is not None
                    and isinstance(resolved_args, dict)
                    and "item" not in resolved_args
                ):
                    resolved_args["item"] = items_to_process

                self.logger.debug(f"Task '{name}' Input: {resolved_args}")

                try:
                    task_output = run_task_wrapper(
                        task_cls, resolved_args, self.dry_run
                    )
                    self.logger.debug(f"Task '{name}' Output: {task_output}")
                except Exception as e:
                    self.logger.error(f"Task execution failed: {e}")

            # Register results
            self.task_results[name] = task_output
            if register_var:
                self.variables[register_var] = task_output
                self.logger.debug(f"Registered result to variable '{register_var}'")

        self.logger.info("Playbook execution complete.")

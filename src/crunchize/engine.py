import concurrent.futures
import importlib
import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


def run_task_wrapper(
    task_cls, args: Dict[str, Any], dry_run: bool, task_info: str = None
):
    """
    Wrapper function to instantiate and run a task.
    Must be at module level for ProcessPoolExecutor pickling.
    """
    if task_info:
        setattr(logging, "_crunchize_task_context", task_info)
    task = task_cls(args, dry_run=dry_run)
    return task.run()


class CrunchizeEngine:
    """
    Core engine for parsing playbooks and executing tasks.
    """

    def __init__(
        self,
        playbook_path: str,
        dry_run: bool = False,
        file_amount: float = 1.0,
    ):
        self.playbook_path = Path(playbook_path)
        self.dry_run = dry_run
        self.file_amount = file_amount
        self.logger = logging.getLogger("crunchize.engine")
        self.variables = {}
        self.task_results = {}
        self.playbook = self._load_playbook()

        # Load global defaults
        self.globals = self._load_globals()

        # Resolve every_nth from playbook or globals
        playbook_config = self.playbook.get("config") or {}
        self.every_nth = playbook_config.get("every_nth")
        if self.every_nth is None:
            self.every_nth = self.globals.get("every_nth", 1)

        # Resolve file_amount from playbook or globals (CLI override takes precedence if not 1.0)
        if self.file_amount == 1.0:
            config_file_amount = playbook_config.get("file_amount")
            if config_file_amount is None:
                config_file_amount = self.globals.get("file_amount", 1.0)
            self.file_amount = config_file_amount

        # Setup logging and other global configs
        self._setup_global_config()

        # Initialize variables from playbook
        if "vars" in self.playbook:
            self.variables.update(self.playbook["vars"])

    def _load_globals(self) -> Dict[str, Any]:
        """Load global defaults from config.yml."""
        # Look for config.yml in a few likely places
        search_paths = [
            Path(__file__).parent.parent.parent / "config.yml",
            Path("config.yml"),
            Path("crunchize/config.yml"),
            Path("~/.crunchize/config.yml").expanduser(),
        ]

        for p in search_paths:
            if p.exists():
                try:
                    with open(p, "r") as f:
                        return yaml.safe_load(f) or {}
                except yaml.YAMLError as e:
                    self.logger.warning(f"Error parsing config YAML at {p}: {e}")
        return {}

    def _setup_global_config(self):
        """Configure logging and other global settings based on globals and playbook overrides."""
        # Log path
        playbook_config = self.playbook.get("config") or {}
        log_path = playbook_config.get("log_path")
        if log_path is None:
            log_path = self.globals.get("log_path")

        wipe_log = playbook_config.get("wipe_log")
        if wipe_log is None:
            wipe_log = self.globals.get("wipe_log", False)

        if log_path:
            log_path = Path(log_path).expanduser()
            try:
                if log_path.parent:
                    log_path.parent.mkdir(parents=True, exist_ok=True)

                mode = "w" if wipe_log else "a"
                file_handler = logging.FileHandler(log_path, mode=mode)
                file_handler.setFormatter(
                    logging.Formatter(
                        "%(asctime)s [%(levelname)s] %(name)s%(task_info)s: %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S",
                    )
                )
                logging.getLogger().addHandler(file_handler)
                self.logger.info(f"Logging to: {log_path}")
            except Exception as e:
                self.logger.error(f"Failed to setup file logging at {log_path}: {e}")

    def _dump_state(self):
        """Dump the final state of variables and task results to a file."""
        playbook_config = self.playbook.get("config") or {}
        dump_path = playbook_config.get("dump_path")
        if dump_path is None:
            dump_path = self.globals.get("dump_path")
        if dump_path:
            dump_path = Path(dump_path).expanduser()
            try:
                if dump_path.parent:
                    dump_path.parent.mkdir(parents=True, exist_ok=True)

                state = {"task_results": self.task_results, "variables": self.variables}

                with open(dump_path, "w") as f:
                    yaml.dump(state, f, default_flow_style=False, sort_keys=False)
                self.logger.info(f"State dumped to: {dump_path}")
            except Exception as e:
                self.logger.error(f"Failed to dump state to {dump_path}: {e}")

    def _load_playbook(self) -> Dict[str, Any]:
        """Load and parse the YAML playbook."""
        if not self.playbook_path.exists():
            raise FileNotFoundError(f"Playbook not found: {self.playbook_path}")

        with open(self.playbook_path, "r") as f:
            try:
                return yaml.safe_load(f) or {}
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
            # Find all {{ var }} patterns (supports simple dot notation for dicts)
            pattern = r"\{\{\s*([a-zA-Z0-9_.]+)\s*\}\}"
            matches = re.findall(pattern, value)

            if not matches:
                return value

            new_value = value
            for var_name in matches:
                var_val = None
                found = False

                # Handle dot notation (e.g., item.files)
                if "." in var_name:
                    parts = var_name.split(".")
                    if parts[0] in context:
                        var_val = context[parts[0]]
                        try:
                            for part in parts[1:]:
                                if isinstance(var_val, dict):
                                    var_val = var_val[part]
                                else:
                                    var_val = getattr(var_val, part)
                            found = True
                        except (KeyError, AttributeError, TypeError):
                            pass
                elif var_name in context:
                    var_val = context[var_name]
                    found = True

                if found:
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
        task_was_loop = {}  # Track if a task performed iteration/filtering

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

            task_info = f"[{i + 1}/{len(tasks_def)} {name}]"
            setattr(logging, "_crunchize_task_context", task_info)

            self.logger.info(f"Running task: {name} [{task_type}]")

            try:
                task_cls = self._get_task_class(task_type)
            except ValueError as e:
                self.logger.error(str(e))
                continue

            # Determine items to process from 'input' or 'loop'
            items_to_process = None
            should_filter = False

            if input_ref:
                # Try to find input in task results (by name)
                if input_ref in self.task_results:
                    items_to_process = self.task_results[input_ref]
                    # Only filter if the source task didn't already iterate (and thus filter)
                    if not task_was_loop.get(input_ref, False):
                        should_filter = True
                # Try to find input in variables
                elif input_ref in self.variables:
                    items_to_process = self.variables[input_ref]
                    should_filter = True
                else:
                    self.logger.warning(
                        f"Input '{input_ref}' not found in task results or variables."
                    )
            elif loop_items:
                items_to_process = self._resolve_variable(loop_items, self.variables)
                should_filter = True

            # Apply every_nth and file_amount filtering if applicable
            if (
                should_filter
                and items_to_process
                and isinstance(items_to_process, list)
            ):
                # 1. Apply file_amount (relative slice from start)
                if self.file_amount < 1.0:
                    original_count = len(items_to_process)
                    limit = max(0, int(original_count * self.file_amount))
                    items_to_process = items_to_process[:limit]
                    self.logger.info(
                        f"Filtering items with file_amount={self.file_amount}: {original_count} -> {len(items_to_process)}"
                    )

                # 2. Apply every_nth
                if self.every_nth > 1:
                    original_count = len(items_to_process)
                    items_to_process = items_to_process[:: self.every_nth]
                    self.logger.info(
                        f"Filtering items with every_nth={self.every_nth}: {original_count} -> {len(items_to_process)}"
                    )

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
                            task_cls, resolved_args, self.dry_run, task_info
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
                                    task_info,
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
                        task_cls, resolved_args, self.dry_run, task_info
                    )
                    self.logger.debug(f"Task '{name}' Output: {task_output}")
                except Exception as e:
                    self.logger.error(f"Task execution failed: {e}")

            # Register results
            self.task_results[name] = task_output
            task_was_loop[name] = items_to_process is not None and isinstance(
                items_to_process, list
            )

            if register_var:
                self.variables[register_var] = task_output
                self.logger.debug(f"Registered result to variable '{register_var}'")

            setattr(logging, "_crunchize_task_context", "")

        self.logger.info("Playbook execution complete.")
        self._dump_state()

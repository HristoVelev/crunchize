import concurrent.futures
import importlib
import logging
import os
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Type

import yaml


def run_task_wrapper(
    task_cls, args: Dict[str, Any], dry_run: bool, task_info: str = None
):
    """
    Isolated wrapper to instantiate and execute a task.

    This function must remain at the module level to be picklable by
    ProcessPoolExecutor for parallel processing across multiple CPU cores.
    """
    if task_info:
        setattr(logging, "_crunchize_task_context", task_info)
    task = task_cls(args, dry_run=dry_run)
    return task.run()


class CrunchizeEngine:
    """
    Core engine for parsing playbooks and executing tasks.

    The engine manages:
    - Playbook and global configuration loading.
    - Recursive variable and template resolution (Jinja2-style).
    - Implicit and explicit data flow between tasks.
    - Parallel execution and sequence-aware filtering.
    """

    def __init__(
        self,
        playbook_path: str,
        dry_run: bool = False,
        file_amount: float = 1.0,
        every_nth: int = None,
        extra_vars: Dict[str, Any] = None,
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

        # Resolve every_nth from playbook or globals (CLI override takes precedence)
        self.every_nth = every_nth
        if self.every_nth is None:
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

        # Overload with CLI extra_vars
        if extra_vars:
            self.variables.update(extra_vars)

        # Resolve variables against each other (except task_results which we want live)
        self.variables = self._resolve_variable(self.variables, self.variables)

        # Provide access to raw task results in templates (as a live reference)
        self.variables["task_results"] = self.task_results

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
                        data = yaml.safe_load(f)
                        return data if isinstance(data, dict) else {}
                except yaml.YAMLError as e:
                    self.logger.warning(f"Error parsing config YAML at {p}: {e}")
        return {}

    def _setup_global_config(self):
        """
        Configure logging and global engine settings.
        Playbook-level configuration takes precedence over global defaults.
        """
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
                data = yaml.safe_load(f)
                return data if isinstance(data, dict) else {}
            except yaml.YAMLError as e:
                raise ValueError(f"Error parsing YAML: {e}")

    def _resolve_variable(
        self, value: Any, context: Dict[str, Any], depth: int = 0
    ) -> Any:
        """
        Recursively substitute {{ variable }} templates in strings, lists, and dicts.

        Supports:
        - Nested access: {{ task.key.subkey }}
        - Bracketed access: {{ task['Complex Key Name'] }}
        - List indexing: {{ results[0] }}
        - Filters: | basename, | dirname, | replace('old', 'new'), | map(attribute='...')
        """
        if depth > 10:
            self.logger.warning(f"Max recursion depth reached resolving: {value}")
            return value

        if isinstance(value, str):
            # Check if the whole string is exactly one template {{ ... }} (robust to whitespace)
            full_match = re.fullmatch(r"^\s*\{\{\s*(?P<expr>[^}]+)\s*\}\}\s*$", value)

            def resolve_expr(expr_str):
                # Remove outer parentheses if any (e.g. (task_results['a'])[0])
                expr_str = expr_str.strip()
                while expr_str.startswith("(") and expr_str.endswith(")"):
                    expr_str = expr_str[1:-1].strip()

                # Handle filters (e.g. var | filter1 | filter2)
                if "|" in expr_str:
                    parts = [x.strip() for x in expr_str.split("|")]
                    var_expr = parts[0].strip()
                    filters = parts[1:]
                else:
                    var_expr = expr_str.strip()
                    filters = []

                var_val = None
                found = False

                # Robust part extraction: identifiers or bracketed content
                # (e.g. identifiers, [0], ['key'], ["key"])
                path_parts = re.findall(
                    r"([a-zA-Z0-9_]+|\[\d+\]|\[['\"][^'\"]+['\"]\])", var_expr
                )

                if path_parts and path_parts[0] in context:
                    var_val = context[path_parts[0]]
                    found = True
                    try:
                        for part in path_parts[1:]:
                            if part.startswith("[") and part.endswith("]"):
                                inner = part[1:-1]
                                if (inner.startswith("'") and inner.endswith("'")) or (
                                    inner.startswith('"') and inner.endswith('"')
                                ):
                                    key = inner[1:-1]
                                    var_val = var_val[key]
                                else:
                                    # Integer index
                                    var_val = var_val[int(inner)]
                            elif isinstance(var_val, dict):
                                var_val = var_val[part]
                            else:
                                var_val = getattr(var_val, part)
                    except (KeyError, AttributeError, TypeError, IndexError):
                        found = False
                elif var_expr in context:
                    var_val = context[var_expr]
                    found = True

                if found:
                    # Apply filters sequentially
                    for filter_expr in filters:
                        filter_expr = filter_expr.strip()
                        if filter_expr.startswith("replace"):
                            replace_match = re.search(
                                r"replace\(\s*['\"]([^'\"]*)['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)",
                                filter_expr,
                            )
                            if replace_match:
                                old, new = replace_match.groups()
                                if isinstance(var_val, str):
                                    var_val = var_val.replace(old, new)
                        elif filter_expr == "basename":
                            if isinstance(var_val, str):
                                var_val = os.path.basename(var_val)
                        elif filter_expr == "dirname":
                            if isinstance(var_val, str):
                                var_val = os.path.dirname(var_val)
                        elif filter_expr.startswith("map"):
                            attr_match = re.search(
                                r"attribute=['\"]([^'\"]+)['\"]", filter_expr
                            )
                            if attr_match and isinstance(var_val, list):
                                attr = attr_match.group(1)
                                var_val = [
                                    (
                                        item.get(attr)
                                        if isinstance(item, dict)
                                        else getattr(item, attr, None)
                                    )
                                    for item in var_val
                                ]
                        elif filter_expr == "list":
                            if not isinstance(var_val, list):
                                var_val = list(var_val)
                    return var_val
                else:
                    # Warn only if it's not a known dynamic variable
                    root = path_parts[0] if path_parts else var_expr
                    if root not in [
                        "item",
                        "items",
                        "task_results",
                        "frame",
                        "first_frame",
                        "last_frame",
                        "filename",
                        "frame_index",
                    ]:
                        self.logger.warning(
                            f"Variable expression '{var_expr}' could not be resolved."
                        )
                return None

            if full_match:
                resolved = resolve_expr(full_match.group("expr"))
                if resolved is not None:
                    # If it's a direct match, return the raw type (list, dict, etc.)
                    if isinstance(resolved, (str, list, dict)):
                        return self._resolve_variable(resolved, context, depth + 1)
                    return resolved

            # Otherwise, do string interpolation for all templates found
            def substitute(m):
                resolved = resolve_expr(m.group(1))
                return str(resolved) if resolved is not None else m.group(0)

            # Use a pattern that doesn't capture extra inner whitespace into the expression
            new_value = re.sub(r"\{\{\s*([^}]+?)\s*\}\}", substitute, value)

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
        elif task_type == "parsepath":
            class_name = "ParsepathTask"
        elif task_type == "inscribe":
            class_name = "InscribeTask"
        elif task_type == "thumbnail":
            class_name = "ThumbnailTask"
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
        last_task_name = None

        for i, task_def in enumerate(tasks_def):
            name = task_def.get("name", f"Task {i}")
            task_type = task_def.get("type")
            task_args = task_def.get("args", {})
            loop_items = task_def.get("loop", None)
            input_ref = task_def.get("input", None)
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

            # Implicit linear flow: if no input/loop is specified, automatically
            # use the result of the previous task as the current task's input.
            if not input_ref and not loop_items and last_task_name:
                input_ref = last_task_name

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
                # 1. Apply file_amount (Stride logic per sequence)
                # Instead of taking the first N frames, we pick frames evenly across
                # every detected sequence to ensure representative shot coverage.
                if self.file_amount < 1.0:
                    original_count = len(items_to_process)
                    groups = defaultdict(list)
                    # Regex to find: base + separator + frame + ext
                    pattern = re.compile(r"^(.*?)[._](\d+)(\.[a-zA-Z0-9]+)$")

                    # Group items by sequence to apply filtering per-shot
                    for item in items_to_process:
                        path = ""
                        if isinstance(item, str): path = item
                        elif isinstance(item, dict):
                            path = item.get("src") or item.get("dst") or item.get("path") or item.get("item") or ""

                        match = pattern.search(os.path.basename(path)) if path else None
                        if match:
                            groups[(os.path.dirname(path), match.group(1), match.group(3))].append(item)
                        else:
                            groups[("single", path, id(item))].append(item)

                    filtered_items = []
                    for key in sorted(groups.keys()):
                        seq_items = groups[key]
                        seq_count = len(seq_items)

                        # Calculate frame count per sequence, ensuring a 2-frame minimum.
                        limit = max(min(2, seq_count), int(seq_count * self.file_amount))

                        if limit >= seq_count:
                            filtered_items.extend(seq_items)
                        else:
                            # Stride logic: pick frames evenly spaced across the range.
                            stride = max(1.0, (seq_count - 1) / (limit - 1))
                            for j in range(limit):
                                index = min(int(round(j * stride)), seq_count - 1)
                                frame_item = seq_items[index]
                                if frame_item not in filtered_items:
                                    filtered_items.append(frame_item)

                    items_to_process = filtered_items
                    self.logger.info(
                        f"Filtering items with file_amount={self.file_amount} (stride per sequence): {original_count} -> {len(items_to_process)}"
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
                    context.update(
                        {
                            "items": items_to_process,
                            "total": len(items_to_process),
                            "first_item": items_to_process[0]
                            if items_to_process
                            else None,
                            "last_item": items_to_process[-1]
                            if items_to_process
                            else None,
                        }
                    )
                    resolved_args = self._resolve_variable(task_args, context)
                    if isinstance(resolved_args, dict):
                        resolved_args["items"] = items_to_process
                        resolved_args["_variables"] = self.variables

                    self.logger.debug(f"Task '{name}' (Batch) Input: {resolved_args}")

                    try:
                        res = run_task_wrapper(
                            task_cls, resolved_args, self.dry_run, task_info
                        )
                        self.logger.debug(f"Task '{name}' (Batch) Output: {res}")

                        # Return task result directly (Simplified data model)
                        task_output = res
                    except Exception as e:
                        self.logger.error(f"Batch task execution failed: {e}")

                else:
                    self.logger.info(
                        f"Parallelizing task over {len(items_to_process)} items."
                    )

                    futures = []
                    total = len(items_to_process)
                    first_item = items_to_process[0] if total > 0 else None
                    last_item = items_to_process[-1] if total > 0 else None

                    # Parallel Execution: Image-per-frame tasks are distributed across
                    # multiple processes to maximize throughput on many-core workstations.
                    with concurrent.futures.ProcessPoolExecutor() as executor:
                        for idx, item in enumerate(items_to_process):
                            # Create context for this iteration
                            context = self.variables.copy()
                            context.update(
                                {
                                    "item": item,
                                    "index": idx,
                                    "total": total,
                                    "first_item": first_item,
                                    "last_item": last_item,
                                }
                            )

                            # If item is a dictionary, unpack it into context (preserving 'item' itself)
                            if isinstance(item, dict):
                                context.update(
                                    {k: v for k, v in item.items() if k not in context}
                                )

                            # Resolve arguments with the item context
                            resolved_args = self._resolve_variable(task_args, context)

                            # Inject 'item' and context into args so tasks can access them directly
                            if isinstance(resolved_args, dict):
                                if "item" not in resolved_args:
                                    resolved_args["item"] = item
                                resolved_args["_variables"] = self.variables

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
                    task_output = []
                    for future in futures:
                        try:
                            res = future.result()
                            self.logger.debug(
                                f"Task '{name}' (Parallel Item) Output: {res}"
                            )
                            task_output.append(res)
                        except Exception as e:
                            self.logger.error(f"Parallel task execution failed: {e}")
                            task_output.append(None)

            else:
                # Single execution
                context = self.variables.copy()
                if items_to_process is not None:
                    context.update(
                        {
                            "item": items_to_process,
                            "index": 0,
                            "total": 1,
                            "first_item": items_to_process,
                            "last_item": items_to_process,
                        }
                    )
                    # If item is a dictionary, unpack it into context (preserving 'item' itself)
                    if isinstance(items_to_process, dict):
                        context.update(
                            {
                                k: v
                                for k, v in items_to_process.items()
                                if k not in context
                            }
                        )

                resolved_args = self._resolve_variable(task_args, context)

                # Inject 'item' and context into args if we have one
                if isinstance(resolved_args, dict):
                    if items_to_process is not None and "item" not in resolved_args:
                        resolved_args["item"] = items_to_process
                    resolved_args["_variables"] = self.variables

                self.logger.debug(f"Task '{name}' Input: {resolved_args}")

                try:
                    res = run_task_wrapper(
                        task_cls, resolved_args, self.dry_run, task_info
                    )
                    self.logger.debug(f"Task '{name}' Output: {res}")
                    task_output = res
                except Exception as e:
                    self.logger.error(f"Task execution failed: {e}")

            # Register results
            self.task_results[name] = task_output
            task_was_loop[name] = items_to_process is not None and isinstance(
                items_to_process, list
            )

            # Auto-register result to variables using the task name.
            # This enables referencing any previous task's output as a variable.
            self.variables[name] = task_output
            last_task_name = name

            setattr(logging, "_crunchize_task_context", "")

        self.logger.info("Playbook execution complete.")
        self._dump_state()

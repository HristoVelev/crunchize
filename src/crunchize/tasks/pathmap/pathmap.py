import re
from collections import defaultdict
from typing import Any, Dict, List, Optional, Union

from crunchize.tasks.base import BaseTask


class PathMappingTask(BaseTask):
    """
    Task to manipulate file paths by performing string substitution.
    Useful for rerooting paths or changing directory structures in a pipeline.
    """

    def validate_args(self) -> None:
        """
        Validate required arguments.
        Requires 'search' and 'replace'.
        """
        if "search" not in self.args:
            raise ValueError("PathMappingTask requires 'search' argument.")
        if "replace" not in self.args:
            raise ValueError("PathMappingTask requires 'replace' argument.")

    def run(self) -> Union[Dict[str, str], List[Dict[str, Any]], None]:
        """
        Perform string substitution on the input path.

        In standard mode, it returns a transition object {src, dst}.
        In batch mode with 'reduce: true', it groups frames into sequence objects.
        """
        # Batch reduction mode: used to group frames into shots (e.g. for ffmpeg)
        items = self.args.get("items")
        if items and isinstance(items, list) and self.args.get("reduce"):
            return self.reduce_paths(items)

        # Standard rerooting mode: used to prepare output paths for processing tasks
        item = self.args.get("item")
        input_path = self.args.get("input_path")
        input_key = self.args.get("input_key")

        # Resolve source string
        source_string = self._resolve_source(item, input_path, input_key)

        if not source_string or not isinstance(source_string, str):
            self.logger.warning("No valid source string found for mapping.")
            return None

        search = self.args["search"]
        replace = self.args["replace"]
        use_regex = self.args.get("regex", False)

        if use_regex:
            new_path = re.sub(search, replace, source_string)
        else:
            # Heuristic: if search ends with separator but replace doesn't, append it
            if (search.endswith("/") or search.endswith("\\")) and not (
                replace.endswith("/") or replace.endswith("\\")
            ):
                replace += search[-1]

            # Perform simple string substitution
            new_path = source_string.replace(search, replace)

        self.logger.debug(f"Mapped: {source_string} -> {new_path}")

        # Return transition object: 'src' is the input to follow-up tasks,
        # 'dst' is the intended output path for those tasks.
        return {"src": source_string, "dst": new_path}

    def _resolve_source(
        self, item: Any, input_path: Optional[str], input_key: Optional[str]
    ) -> Optional[str]:
        """Helper to resolve the source string from various inputs."""
        if input_path:
            return input_path
        if isinstance(item, str):
            return item
        if isinstance(item, dict):
            if input_key:
                return item.get(input_key)
            # Prioritize 'dst' from previous mapping, then 'src', then 'item'
            return item.get("dst") or item.get("src") or item.get("item")
        return None

    def reduce_paths(self, items: List[Any]) -> List[Dict[str, Any]]:
        """
        Group items by sequence pattern and map the base name.

        This identifies frames belonging to the same shot (e.g. shot.1001.exr, shot.1002.exr)
        and returns a single shot object for downstream tasks like video encoding.
        """
        search = self.args["search"]
        replace = self.args["replace"]
        use_regex = self.args.get("regex", False)

        if not use_regex:
            # Heuristic: if search ends with separator but replace doesn't, append it
            if (search.endswith("/") or search.endswith("\\")) and not (
                replace.endswith("/") or replace.endswith("\\")
            ):
                replace += search[-1]

        input_key = self.args.get("input_key")

        groups = defaultdict(list)

        # 1. Group items by (base_name, extension)
        # This uses a VFX-standard regex to identify frame numbers.
        # Optimized to handle multiple dots and standard VFX naming conventions
        pattern = re.compile(r"^(.*?)[._](\d+)(\.[a-zA-Z0-9]+)$")

        for item in items:
            path = self._resolve_source(item, None, input_key)
            if not path:
                continue

            # Apply mapping to the full path BEFORE grouping to allow combining sequences from different source folders
            if use_regex:
                mapped_path = re.sub(search, replace, path)
            else:
                mapped_path = path.replace(search, replace)

            match = pattern.search(mapped_path)
            if match:
                mapped_base, frame, ext = match.groups()
                # Key by mapped base and ext to handle multiple sequences in one list
                groups[(mapped_base, ext)].append(item)
            else:
                # Fallback for non-sequence files
                groups[(mapped_path, "")].append(item)

        results = []

        # 2. Consolidate groups into sequence objects
        for (mapped_base, ext), group_items in groups.items():
            # Sort items by filename to ensure correct frame order for video
            sorted_items = sorted(
                group_items,
                key=lambda x: self._resolve_source(x, None, input_key) or "",
            )

            # Return 'files' (the list of inputs) and 'base_path' (the mapped output name)
            res = {
                "files": sorted_items,
                "base_path": mapped_base,
            }
            results.append(res)

        self.logger.info(f"Reduced {len(items)} items into {len(results)} sequences.")
        return results

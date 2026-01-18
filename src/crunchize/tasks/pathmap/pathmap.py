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

    def run(self) -> Union[Optional[str], Dict[str, Any], List[Dict[str, Any]]]:
        """
        Perform string substitution on the input path.
        If output_key is provided, returns a dictionary with the new path added.
        If 'items' is present (batch mode) and 'reduce' is True, performs sequence reduction.
        """
        items = self.args.get("items")
        if items and isinstance(items, list) and self.args.get("reduce"):
            return self.reduce_paths(items)

        item = self.args.get("item")
        input_path = self.args.get("input_path")
        output_key = self.args.get("output_key")
        input_key = self.args.get("input_key")

        # Resolve source string
        source_string = self._resolve_source(item, input_path, input_key)

        if not source_string or not isinstance(source_string, str):
            self.logger.warning("No valid source string found for mapping.")
            return None

        search = self.args["search"]
        replace = self.args["replace"]

        # Heuristic: if search ends with separator but replace doesn't, append it
        if (search.endswith("/") or search.endswith("\\")) and not (
            replace.endswith("/") or replace.endswith("\\")
        ):
            replace += search[-1]

        # Perform simple string substitution
        new_path = source_string.replace(search, replace)

        if output_key:
            # Construct result dictionary
            if isinstance(item, dict):
                result = item.copy()
            else:
                result = {"item": item}

            result[output_key] = new_path
            self.logger.debug(
                f"Mapped: {source_string} -> {new_path} (stored in '{output_key}')"
            )
            return result
        else:
            self.logger.debug(f"Mapped: {source_string} -> {new_path}")
            return new_path

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
            if "item" in item:
                return item["item"]
        return None

    def reduce_paths(self, items: List[Any]) -> List[Dict[str, Any]]:
        """
        Group items by sequence pattern and map the base name.
        Returns a list of dictionaries containing the grouped files and mapped base path.
        """
        search = self.args["search"]
        replace = self.args["replace"]

        # Heuristic: if search ends with separator but replace doesn't, append it
        if (search.endswith("/") or search.endswith("\\")) and not (
            replace.endswith("/") or replace.endswith("\\")
        ):
            replace += search[-1]

        output_key = self.args.get("output_key", "mapped_path")
        input_key = self.args.get("input_key")

        groups = defaultdict(list)

        # 1. Group items by (base_name, extension)
        # Regex to find: name + separator + numbers + extension
        # e.g. "shot.1001.exr" -> "shot", "1001", ".exr"
        pattern = re.compile(r"^(.*)[._](\d+)(\..+)$")

        for item in items:
            path = self._resolve_source(item, None, input_key)
            if not path:
                continue

            match = pattern.search(path)
            if match:
                base, frame, ext = match.groups()
                # Key by base and ext to handle multiple sequences in one list
                groups[(base, ext)].append(item)
            else:
                # Fallback for non-sequence files
                groups[(path, "")].append(item)

        results = []

        # 2. Process groups
        for (base, ext), group_items in groups.items():
            # Apply mapping to the base name
            # User requirement: "without frame number... no extension"
            # So we use 'base' which excludes frame and extension.
            mapped_base = base.replace(search, replace)

            # Sort items to ensure frames are in order
            sorted_items = sorted(
                group_items,
                key=lambda x: self._resolve_source(x, None, input_key) or "",
            )

            res = {
                "files": sorted_items,
                output_key: mapped_base,
            }
            results.append(res)

        self.logger.info(f"Reduced {len(items)} items into {len(results)} sequences.")
        return results

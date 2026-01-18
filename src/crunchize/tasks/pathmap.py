from typing import Optional, Union

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

    def run(self) -> Optional[Union[str, dict]]:
        """
        Perform string substitution on the input path.
        If output_key is provided, returns a dictionary with the new path added.
        """
        item = self.args.get("item")
        input_path = self.args.get("input_path")
        output_key = self.args.get("output_key")
        input_key = self.args.get("input_key")

        # Resolve source string
        source_string = input_path
        if not source_string:
            if isinstance(item, str):
                source_string = item
            elif isinstance(item, dict):
                if input_key:
                    source_string = item.get(input_key)
                # Fallback to 'item' key if it exists (common pattern)
                elif "item" in item:
                    source_string = item["item"]

        if not source_string or not isinstance(source_string, str):
            self.logger.warning("No valid source string found for mapping.")
            return None

        search = self.args["search"]
        replace = self.args["replace"]

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

# PathMap Task

The `pathmap` task is a powerful utility for manipulating file paths and strings within a workflow. It is essential for rerooting paths (e.g., changing `/mnt/plates` to `/tmp/work`), changing directory structures, or grouping individual frames into sequence objects for batch processing.

## Parameters

| Name         | Type    | Required | Default | Description                                                                                   |
|--------------|---------|----------|---------|-----------------------------------------------------------------------------------------------|
| `search`     | String  | Yes      | -       | The substring to search for in the source path.                                               |
| `replace`    | String  | Yes      | -       | The string to replace the search match with.                                                  |
| `input_path` | String  | No       | -       | Explicit source string. If not provided, the task uses the implicit `item` from the engine.   |
| `output_key` | String  | No       | -       | If provided, the task returns a dictionary containing the new path under this key.            |
| `input_key`  | String  | No       | -       | If the input is a dictionary, use this key as the source string.                              |
| `reduce`     | Boolean | No       | `false` | (Batch mode only) If true, groups files into sequences and returns a list of sequence objects. |

## Features

- **Smart Separators**: If the `search` string ends with a path separator (`/` or `\`) but the `replace` string does not, the task automatically appends the separator to maintain path integrity.
- **Sequence Reduction**: When `batch: true` and `reduce: true` are set, the task identifies image sequences (e.g., `shot.1001.exr`, `shot.1002.exr`) and groups them into a single object containing a list of files and a mapped base path.
- **Context Preservation**: When using `output_key`, the task returns the original input dictionary (if applicable) merged with the new mapped value, preserving metadata across the pipeline.

## Example Usage

### Simple Path Rerooting
```yaml
- name: "Map Plates to Work"
  type: "pathmap"
  input: "Find Source Plates"
  args:
    search: "/mnt/prod/plates/"
    replace: "/tmp/local_work/"
```

### Sequence Reduction for Video Encoding
```yaml
- name: "Group Frames for Video"
  type: "pathmap"
  batch: true
  input: "Scaled JPGs"
  args:
    reduce: true
    search: "/scaled/"
    replace: "/movies/"
    output_key: "video_base"
```

## Internal Operation
The task uses standard string replacement and regular expression patterns to identify frame numbers and extensions. It is highly optimized for handling large lists of files in batch mode.
# FileIn Task

The `filein` task is the primary entry point for gathering source files in a Crunchize workflow. It uses glob patterns to scan the filesystem and returns a sorted list of matched file paths.

## Parameters

| Name        | Type    | Required | Default | Description                                                                 |
|-------------|---------|----------|---------|-----------------------------------------------------------------------------|
| `pattern`   | String  | Yes      | -       | The glob pattern used to search for files (e.g., `/path/to/plates/*.exr`).   |
| `recursive` | Boolean | No       | `false` | If true, the pattern `**` will match any files and zero or more directories. |

## Features

- **Sequence Detection**: During execution, the task automatically groups matched files into sequences and logs them in a condensed format (e.g., `shot.[1001-1050].exr`) for better readability in the logs.
- **Natural Sorting**: Matches are sorted alphabetically to ensure image sequences are processed in the correct order.
- **Read-Only**: This task does not perform any side effects on the filesystem, making it safe to run even when not in dry-run mode.

## Example Usage

### Basic Glob
```yaml
- name: "Find Source Plates"
  type: "filein"
  args:
    pattern: "/mnt/projects/show/shot/plates/main/*.exr"
```

### Recursive Search
```yaml
- name: "Find All Textures"
  type: "filein"
  args:
    pattern: "/mnt/projects/show/assets/**/textures/*.tif"
    recursive: true
```

## Internal Operation
The task uses Python's standard `glob` module. Note that the performance of this task depends on the speed of the underlying filesystem and the breadth of the search pattern.
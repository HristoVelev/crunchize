# Delete Task

The `delete` task provides a simple utility for removing files from the filesystem. It is primarily used for cleaning up intermediate cache files or temporary sequences generated during a multi-step workflow.

## Parameters

| Name   | Type   | Required | Default | Description                                                                 |
|--------|--------|----------|---------|-----------------------------------------------------------------------------|
| `path` | String | No*      | -       | The full path to the file to be deleted.                                    |

> **Note**: While `path` is listed as the primary argument, the task will also accept an implicit `item` provided by the engine (e.g., when iterating over a list or receiving input from a previous task). One of these must be present.

## Features

- **Safe Deletion**: Checks for file existence before attempting removal to avoid errors.
- **Dry Run Support**: If the engine is in dry-run mode, the task logs which file would be deleted without actually removing it.
- **Error Handling**: Catches and logs `OSError` if permissions or system issues prevent deletion.

## Example Usage

### Explicit Path
```yaml
- name: "Remove temporary log"
  type: "delete"
  args:
    path: "/tmp/process_cache.tmp"
```

### From Previous Task (Cleanup)
```yaml
- name: "Cleanup Scaled JPGs"
  type: "delete"
  input: "Scale to 50%" # Deletes every file returned by the 'Scale to 50%' task
```

## Internal Operation
The task uses standard Python `os.remove()` for file deletion. It does not currently support directory deletion or recursive globbing for safety reasons.
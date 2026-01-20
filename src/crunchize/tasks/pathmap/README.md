# Path Mapping Task

The `pathmap` task is a versatile tool for manipulating file paths. It is primarily used for **rerooting** (changing base directories) or **sequence reduction** (grouping individual frames into shot objects).

## Simplified Data Model

In the modern Crunchize pipeline, the `pathmap` task acts as a bridge between storage locations. 

- **Individual Mapping**: When mapping single files (default), it returns a mapping object: `{"src": original_path, "dst": mapped_path}`. This allows downstream processing tasks (like `convert` or `oiio`) to automatically resolve their input and output requirements.
- **Implicit Input**: It prioritizes the `dst` key of a previous task as its new `src`, enabling effortless chaining.

## Parameters

| Name | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `search` | String | Yes | - | The string or pattern to find in the path. |
| `replace` | String | Yes | - | The replacement string. |
| `regex` | Boolean | No | `false` | If true, `search` and `replace` are treated as regular expressions. |
| `reduce` | Boolean | No | `false` | (Batch only) If true, groups mapped files into sequence objects. |
| `input_key` | String | No | - | Force mapping on a specific dictionary key. |

## Sequence Reduction (`reduce: true`)

When used with `batch: true` and `reduce: true`, this task transforms a flat list of files into a list of **sequence objects**. This is a critical step before tasks that operate on entire shots, such as `ffmpeg`.

**Output Structure:**
```json
{
  "files": ["/path/shot.0001.jpg", "/path/shot.0002.jpg", ...],
  "base_path": "/path/shot"
}
```

## Example Usage

### 1. Rerooting for Conversion
Prepares a destination path for a subsequent processing task.

```yaml
- name: "proxy_mapping"
  type: "pathmap"
  args:
    search: "/mnt/prod/PLATES"
    replace: "/tmp/PROXIES"

- name: "convert_task"
  type: "convert"
  # Automatically uses 'src' as input and 'dst' as output from proxy_mapping
  args:
    output_format: "jpg"
    ...
```

### 2. Shot Grouping for Video
Groups multiple frames into a single sequence object for encoding.

```yaml
- name: "movie_sequence"
  type: "pathmap"
  batch: true
  args:
    search: "test-burnin"
    replace: "test-video"
    reduce: true  # Combines all frames into a single sequence object

- name: "video_file"
  type: "ffmpeg"
  # Automatically uses 'files' from movie_sequence as input
  args:
    fps: 24
```

### 3. Regex Renaming
Advanced path manipulation using regular expressions.

```yaml
- name: "version_bump"
  type: "pathmap"
  args:
    regex: true
    search: "_v(\\d+)"
    replace: "_v099" # Simple string replacement or back-references
```

# ParsePath Task

The `parsepath` task extracts metadata from file paths or strings using Regular Expressions with named capture groups. Captured values are returned as a dictionary and automatically registered in the global variable scope under the task's name.

## Implicit Data Flow

1.  **Implicit Input**: If `input_path` is not provided, the task automatically attempts to resolve a path from the current execution context (`item` or preceding task result).
2.  **Global Registration**: Captured groups are merged into the global variable pool. For example, a task named `meta` that captures `shot` will make `{{ meta.shot }}` available to all subsequent tasks.
3.  **Batch Support**: When used with `batch: true`, it typically parses the first file in a sequence to establish shot-level metadata (like Sequence, Shot ID, or Department).

## Parameters

| Name | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `pattern` | String | Yes | - | Python-style regex with named groups, e.g., `(?P<name>...)`. |
| `input_path` | String | No* | - | The string to parse. Inferred from context if not provided. |

*\*Required only if the path cannot be inferred from the preceding task.*

## Example Usage

### 1. Standard Metadata Extraction

Extracting sequence and shot information from a standard VFX directory structure.

```yaml
- name: "meta"
  type: "parsepath"
  batch: true
  args:
    # Matches /projects/show/SHOTS/seq01/s010/PLATES/...
    pattern: ".*/SHOTS/(?P<seq>[^/]+)/(?P<shot>[^/]+)/.*"

- name: "burnin"
  type: "inscribe"
  args:
    type: "burnin"
    groups:
      - anchor: "top-left"
        items:
          - type: "text"
            source: "SEQ: {{ meta.seq }} SHOT: {{ meta.shot }}"
```

### 2. Version and Frame Parsing

Capturing the version number and the original frame index from a filename.

```yaml
- name: "file_info"
  type: "parsepath"
  args:
    # Matches shot_v002.1001.exr
    pattern: ".*_v(?P<ver>\\d+)\\.(?P<orig_frame>\\d+)\\..*"

- name: "output_log"
  type: "inscribe"
  args:
    type: "burnin"
    groups:
      - anchor: "bottom-left"
        items:
          - type: "text"
            source: "v{{ file_info.ver }} (Orig: {{ file_info.orig_frame }})"
```

## Tips

- **Case Insensitivity**: Use `(?i)` at the start of your pattern for case-insensitive matching.
- **Escape Backslashes**: Remember that in YAML, backslashes often need to be escaped (e.g., `\\d` instead of `\d`).
- **Batch Processing**: Use `batch: true` if you only need to extract metadata once per shot (from the first frame) rather than repeating the logic for every single file.
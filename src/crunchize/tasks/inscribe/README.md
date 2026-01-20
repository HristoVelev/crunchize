# Inscribe Task

The `inscribe` task is a powerful layout engine designed for creating slates and burn-ins. It uses a CSS-inspired model with anchors and flexbox-like grouping to position text and images over your sequences.

## Implicit Data Flow

The `inscribe` task is fully integrated with Crunchize's implicit flow:

1.  **Implicit Input**: In `burnin` mode, it automatically resolves the source image from the preceding task.
2.  **Implicit Output**: It automatically resolves the destination path (usually from a `pathmap`).
3.  **Slate Expansion**: In `slate` mode with `batch: true`, the task generates a slate and automatically **prepends** it to the current sequence of files, passing the expanded list (Slate + Sequence) to the next task (e.g., `ffmpeg`).

## Parameters

| Name | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `type` | String | Yes | `burnin` | `burnin` (overlay on input) or `slate` (single frame generated from scratch). |
| `output_path` | String | No* | - | Target path. Inferred if not provided. |
| `groups` | List | Yes | - | List of layout groups (see below). |
| `width` | Integer | No | 1920 | Canvas width (used for `slate` or sizing calculations). |
| `height` | Integer | No | 1080 | Canvas height. |
| `font_path` | String | No | *Built-in* | Path to a TrueType font (.ttf). Defaults to a monospaced system font. |

*\*Required only if paths cannot be inferred from the preceding task.*

## Context Variables

Within text sources, you can use the following dynamic variables:

-   `{{ frame }}`: The current frame number.
-   `{{ filename }}`: The full source filename.
-   `{{ basename }}`: The "clean" filename (no frame, no extension).
-   `{{ index }}`: Position in the current batch (0-based).
-   `{{ total }}`: Total number of files in the batch.
-   Any variables from the global `vars` or preceding `parsepath` tasks (e.g., `{{ meta.shot_id }}`).

## Layout System

Groups are defined with an `anchor` (e.g., `top-left`, `mid-mid`, `bottom-right`) and a list of `items`.

### Item Types

-   **`text`**:
    -   `source`: The string to display (supports variables).
    -   `size`: Relative size (e.g., `0.05` is 5% of canvas width).
    -   `color`: Hex or common name (e.g., `white`, `#ff0000`).
-   **`image`**:
    -   `source`: Path to an image file (e.g., a studio logo).
    -   `size`: Relative width.

## Example Usage

### Sequence Burn-in (Implicit)

```yaml
- name: "burnin_mapping"
  type: "pathmap"
  args:
    search: "test-scaled"
    replace: "test-burnin"

- name: "burnin_files"
  type: "inscribe"
  args:
    type: "burnin"
    groups:
      - anchor: "top-left"
        items:
          - type: "text"
            source: "SHOT: {{ basename }}"
      - anchor: "bottom-right"
        items:
          - type: "text"
            source: "{{ frame }}"
```

### Auto-Prepended Slate (Batch)

```yaml
- name: "slate_mapping"
  type: "pathmap"
  args:
    search: "test-burnin"
    replace: "test-slate"

- name: "sequence_with_slate"
  type: "inscribe"
  batch: true
  args:
    type: "slate"
    groups:
      - anchor: "mid-mid"
        layout: "vertical"
        items:
          - type: "text"
            source: "{{ meta.seq }} / {{ meta.shot }}"
            size: 0.1
          - type: "text"
            source: "STATUS: WORK IN PROGRESS"
            size: 0.04
```

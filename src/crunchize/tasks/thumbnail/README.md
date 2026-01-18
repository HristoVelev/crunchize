# Thumbnail Task

The `thumbnail` task is designed to generate a representative still image from a sequence of files. It allows you to pick a frame based on a relative position in the sequence and resize it while maintaining its aspect ratio.

## Parameters

| Name              | Type          | Required | Default | Description                                                                                                   |
|-------------------|---------------|----------|---------|---------------------------------------------------------------------------------------------------------------|
| `output_path`     | String        | Yes      | -       | Base path for the generated thumbnail. The extension will be adjusted based on the `format` parameter.         |
| `input_files`     | List[String]  | No*      | -       | List of file paths to choose the thumbnail from.                                                              |
| `sourcelocation`  | Float         | No       | `0.5`   | Relative position in the sequence (0.0 to 1.0). `0.5` picks the middle frame, `0.0` the first, `1.0` the last. |
| `size`            | Integer       | No       | -       | Target width in pixels. The height is automatically calculated to preserve the image aspect ratio.           |
| `format`          | String        | No       | `jpg`   | Output image format (e.g., `jpg`, `png`).                                                                     |
| `existing`        | String        | No       | `replace`| How to handle existing files: `skip` (save time) or `replace`.                                                |

> **Note**: One of `input_files` or an implicit `item` (provided by the engine via `loop` or `input`) must be present.

## Features

- **Proportional Picking**: Uses a float-based coordinate to pick a frame regardless of the sequence length.
- **Smart Resizing**: Uses `oiiotool`'s proportional resizing logic (`widthx0`) to ensure thumbnails are never distorted.
- **Auto-Extension**: Automatically strips existing extensions from `output_path` and applies the one defined in `format`.

## Example Usage

### Generating a mid-point thumbnail from a sequence
```yaml
- name: "Generate Thumbnail"
  type: "thumbnail"
  input: "Find Source Plates"
  args:
    output_path: "/mnt/prod/show/shot/thumbs/shot_main"
    sourcelocation: 0.5
    size: 480
    format: "jpg"
```

### Picking the first frame
```yaml
- name: "First Frame Thumb"
  type: "thumbnail"
  args:
    input_files: ["frame.001.exr", "frame.002.exr", "frame.003.exr"]
    output_path: "/tmp/start_frame"
    sourcelocation: 0.0
    size: 100
```

## Internal Operation
The task uses OpenImageIO's `oiiotool` for the resizing operation. It calculates the frame index using `int(len(files) * sourcelocation)` and executes:
`oiiotool <picked_frame> --resize <width>x0 -o <output_path>.<format>`

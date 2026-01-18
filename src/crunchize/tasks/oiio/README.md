# OIIO Task (oiiotool)

The `oiio` task leverages OpenImageIO's `oiiotool` utility for high-performance image processing. While it currently emphasizes scaling and resizing, it is designed to support arbitrary `oiiotool` operations.

## Parameters

| Name            | Type          | Required | Default | Description                                                                 |
|-----------------|---------------|----------|---------|-----------------------------------------------------------------------------|
| `output_path`   | String        | Yes      | -       | Path where the processed image will be saved.                               |
| `input_path`    | String        | No*      | -       | Path to the source image file.                                              |
| `width`         | Integer       | No       | -       | Target width in pixels.                                                     |
| `height`        | Integer       | No       | -       | Target height in pixels.                                                    |
| `scale`         | Float/String  | No       | -       | Scale factor applied after width/height. e.g., `0.5` becomes `50%`.         |
| `extra_args`    | List/String   | No       | `[]`    | Additional raw `oiiotool` arguments (e.g., `--colorconvert`, `--ch`).        |
| `existing`      | String        | No       | `replace`| How to handle existing files: `skip` (save time) or `replace`.              |

> **Note**: One of `input_path` or an implicit `item` (provided by the engine via `loop` or `input`) must be present.

## Features

- **Flexible Resizing**: Supports pixel-based dimensions (`width`, `height`) and relative `scale`.
- **Smart Fitting**:
  - Providing both `width` and `height` uses `--fit`, which fits the image within the dimensions (letterboxing).
  - Providing only one preserves the aspect ratio.
- **Directory Creation**: Automatically creates the parent directory for the `output_path` if it does not exist.
- **Extensible**: Use `extra_args` to tap into the full power of `oiiotool` for metadata manipulation, color conversions, or channel shuffling.
- **Dry Run Support**: Logs the full command that would be executed without touching the filesystem.

## Example Usage

### Simple 50% Rescale
```yaml
- name: "Create 50% Proxies"
  type: "oiio"
  input: "Source Plates"
  args:
    output_path: "/path/to/proxy/{{ item.basename }}.jpg"
    scale: 0.5
```

### Advanced usage with extra arguments
```yaml
- name: "Convert and Add Burn-in"
  type: "oiio"
  args:
    input_path: "/path/to/render.exr"
    output_path: "/path/to/delivery.tif"
    scale: "1920x1080"
    extra_args: 
      - "--text"
      - "Shot: TS_001"
      - "--colorconvert"
      - "linear"
      - "sRGB"
```

## Internal Command
The task constructs and executes a command similar to:
`oiiotool <input_path> [--fit <width>x<height> | --resize <width>x0] [--resize <scale>] [extra_args] -o <output_path>`

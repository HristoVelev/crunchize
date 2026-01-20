# Convert Task

The `convert` task performs color space transformations on image files using OpenColorIO's `ocioconvert` tool.

## Simplified Data Model & Path Inference

Following the framework's implicit flow, the `convert` task can automatically resolve its input and output paths:

1.  **Implicit Input**: If preceded by a `pathmap` task, it automatically uses the `src` key as the input image.
2.  **Implicit Output**: It automatically uses the `dst` key from a preceding `pathmap` as the base output path.
3.  **Format Handling**: If `output_format` is provided, the task will automatically ensure the output extension matches (e.g., converting `.exr` paths to `.jpg`).

## Parameters

| Name            | Type   | Required | Default | Description                                                                 |
|-----------------|--------|----------|---------|-----------------------------------------------------------------------------|
| `input_path`    | String | No*      | -       | Path to the source image. Inferred if not provided.                         |
| `output_path`   | String | No*      | -       | Path to the destination image. Inferred if not provided.                    |
| `config_path`   | String | Yes      | -       | Path to the OCIO configuration file (`.ocio`).                              |
| `input_space`   | String | Yes      | -       | Name of the source color space.                                             |
| `output_space`  | String | Yes      | -       | Name of the target color space.                                             |
| `output_format` | String | No       | -       | Optional extension (e.g., `jpg`) to force the output format.                |
| `existing`      | String | No       | `replace`| `skip` or `replace`.                                                        |

*\*Required only if the paths cannot be inferred from the preceding task.*

## Example Usage

### Implicit Chaining (Recommended)

In this example, the `convert` task automatically picks up the source and destination paths defined in `proxy_mapping`.

```yaml
- name: "proxy_mapping"
  type: "pathmap"
  args:
    search: "PLATES"
    replace: "PROXIES"

- name: "proxy_files"
  type: "convert"
  args:
    output_format: "jpg"
    config_path: "/path/to/config.ocio"
    input_space: "ACEScg"
    output_space: "sRGB"
```

### Explicit Paths

```yaml
- name: "manual_convert"
  type: "convert"
  args:
    input_path: "/path/to/render.exr"
    output_path: "/path/to/output.jpg"
    config_path: "/path/to/config.ocio"
    input_space: "ACEScg"
    output_space: "sRGB"
```

## Internal Command

The task executes the following system command:
`ocioconvert --iconfig <config_path> <input_path> <input_space> <output_path> <output_space>`

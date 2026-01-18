# Convert Task

The `convert` task uses OpenColorIO's `ocioconvert` command-line tool to perform color space conversions on image files.

## Parameters

| Name            | Type   | Required | Default | Description                                                                 |
|-----------------|--------|----------|---------|-----------------------------------------------------------------------------|
| `input_path`    | String | Yes      | -       | Path to the source image file.                                              |
| `output_path`   | String | Yes      | -       | Path where the converted image will be saved.                               |
| `config_path`   | String | Yes      | -       | Path to the OCIO configuration file (`.ocio`).                              |
| `input_space`   | String | Yes      | -       | Name of the input color space defined in the OCIO config.                   |
| `output_space`  | String | Yes      | -       | Name of the target color space defined in the OCIO config.                  |
| `output_format` | String | No       | -       | Optional extension (e.g., `jpg`, `png`) to force the output format.         |
| `existing`      | String | No       | `replace`| How to handle existing files: `skip` (save time) or `replace`.              |

## Example Usage

```yaml
- name: "Convert EXR to sRGB"
  type: "convert"
  args:
    input_path: "/path/to/render.exr"
    output_path: "/path/to/output.jpg"
    config_path: "/path/to/aces_1.2/config.ocio"
    input_space: "ACES - ACEScg"
    output_space: "Output - sRGB"
    output_format: "jpg"
```

## Internal Command
The task constructs and executes a command similar to:
`ocioconvert --iconfig <config_path> <input_path> <input_space> <output_path> <output_space>`

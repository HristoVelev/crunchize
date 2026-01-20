# OIIOTool Task

The `oiio` task uses OpenImageIO's `oiiotool` command-line utility to perform high-quality image resizing and manipulation.

## Implicit Data Flow

Following Crunchize's simplified data model, the `oiio` task automatically resolves its input and output paths:

1.  **Implicit Input**: If preceded by a `pathmap` or transition task, it automatically uses the `src` or `dst` key as the input image.
2.  **Implicit Output**: It automatically uses the `dst` key from a preceding `pathmap` as the target output path.
3.  **Automatic Resampling**: By default, it uses high-quality Lanczos resampling for all scaling operations.

## Parameters

| Name | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `scale` | Float/String | No | - | Scaling factor. Float (e.g., `0.5` for 50%) or String (e.g., `200%`). |
| `width` | Integer | No | - | Force a specific width in pixels (height scales proportionally). |
| `height` | Integer | No | - | Force a specific height in pixels (width scales proportionally). |
| `output_path` | String | No* | - | Target path. Inferred if not provided. |
| `extra_args` | List/String | No | `[]` | Additional raw `oiiotool` flags (e.g., `--colorconvert`, `--crop`). |
| `existing` | String | No | `replace` | `skip` or `replace`. |

*\*Required only if the path cannot be inferred from the preceding task.*

## Example Usage

### 1. Scaling for Proxies (Implicit)

This is the standard way to create 50% JPG proxies. The task automatically picks up the source and destination from the previous mapping.

```yaml
- name: "scale_mapping"
  type: "pathmap"
  args:
    search: "test-proxy"
    replace: "test-scaled"

- name: "scaled_files"
  type: "oiio"
  args:
    scale: 0.5
```

### 2. Fixed Dimension Letterboxing

If both `width` and `height` are provided, the image is fitted within the dimensions and padded to the target canvas size.

```yaml
- name: "hd_render"
  type: "oiio"
  args:
    width: 1920
    height: 1080
```

### 3. Advanced Manipulation

You can pass arbitrary arguments directly to `oiiotool` using `extra_args`.

```yaml
- name: "custom_process"
  type: "oiio"
  args:
    scale: 1.0
    extra_args: ["--colorconvert", "linear", "sRGB", "--crop", "100,100,800,600"]
```

## Internal Command

The task executes the following system command:
`oiiotool <input_path> --resize <geometry> <extra_args> -o <output_path>`

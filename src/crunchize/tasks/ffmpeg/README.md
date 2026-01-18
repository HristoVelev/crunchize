# FFmpeg Task

The `ffmpeg` task provides high-level control over video encoding, supporting both single image sequence patterns and explicit file lists via the concat demuxer.

## Parameters

| Name            | Type          | Required | Default    | Description                                                                 |
|-----------------|---------------|----------|------------|-----------------------------------------------------------------------------|
| `output_path`   | String        | Yes      | -          | Path to the resulting video file.                                           |
| `input_path`    | String        | No*      | -          | FFmpeg-style input pattern (e.g., `shot.%04d.exr`).                         |
| `input_files`   | List[String]  | No*      | -          | Explicit list of file paths to concatenate into a video.                    |
| `width`         | Integer       | No       | -          | Target width in pixels.                                                     |
| `height`        | Integer       | No       | -          | Target height in pixels.                                                    |
| `fps`           | Integer/Float | No       | 24         | Frames per second for the output video. (Alias: `framerate`)                |
| `codec`         | String        | No       | `libx264`  | Video codec to use (e.g., `libx264`, `prores_ks`, `dnxhd`).                 |
| `container`     | String        | No       | -          | Optional extension override (e.g., `mov`, `mp4`, `mkv`).                    |
| `existing`      | String        | No       | `replace`  | How to handle existing files: `skip` (save time) or `replace`.              |
| `extra_args`    | List/String   | No       | `[]`       | Additional raw FFmpeg command line arguments (e.g., `["-crf", "18"]`).       |
| `start_frame`   | Integer       | No       | -          | The starting frame number for pattern-based inputs.                         |

> **Note**: One of `input_path` or `input_files` must be provided. If `input_files` is used, the task automatically generates a temporary concat list for FFmpeg.

## Features

- **Flexible Resizing**: Supports pixel-based dimensions (`width`, `height`).
- **Smart Fitting**:
  - Providing both `width` and `height` fits the image within the dimensions and applies black bars (letterboxing).
  - Providing only one preserves the aspect ratio (automatically ensuring even dimensions for codec compatibility).
- **Directory Creation**: Automatically creates the parent directory for the `output_path` if it does not exist.

## Popular VFX Codecs

When working in a VFX pipeline, the following codec names are commonly used with the `codec` parameter:

*   **H.264**: `libx264` (Standard for web/reviews)
*   **Apple ProRes**: `prores_ks` (Standard for intermediate delivery)
*   **Avid DNxHR/DNxHD**: `dnxhd` (Standard for editorial)
*   **VP9**: `libvpx-vp9` (High-efficiency open source)

## Example Usage

### Creating a review MP4 from a file list
```yaml
- name: "Create Review Movie"
  type: "ffmpeg"
  args:
    input_files: "{{ item.files }}"
    output_path: "/path/to/review/sequence"
    container: "mp4"
    fps: 23.976
    codec: "libx264"
    extra_args: ["-crf", "20", "-preset", "slow"]
```

### Creating a ProRes MOV from a pattern
```yaml
- name: "Render ProRes"
  type: "ffmpeg"
  args:
    input_path: "/path/to/frames/shot.%04d.exr"
    output_path: "/path/to/delivery/shot.mov"
    codec: "prores_ks"
    extra_args: ["-profile:v", "3"] # ProRes 422 HQ
```

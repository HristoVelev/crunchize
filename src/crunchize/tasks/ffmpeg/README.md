# FFmpeg Task

The `ffmpeg` task encodes image sequences into video files. It is designed to work seamlessly with Crunchy's simplified data model and sequence grouping logic.

## Implicit Data Flow

The `ffmpeg` task is optimized for use after a `pathmap` task with `reduce: true`. 

1.  **Implicit Input**: If the preceding task returns a sequence object (containing a `files` list), this task automatically uses those files as the source.
2.  **Implicit Output**: If the input item contains a `base_path`, it is used as the default output path (appending the specified container extension).
3.  **Automatic Concat**: When provided with a list of files, the task automatically generates a temporary FFmpeg concat file to ensure perfect frame order and timing.

## Parameters

| Name | Type | Required | Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `output_path` | String | No* | - | Target video path. Inferred from `base_path` if not provided. |
| `fps` | Integer | No | `24` | Frames per second. |
| `container` | String | No | `mp4` | Video container format (e.g., `mp4`, `mov`, `mkv`). |
| `codec` | String | No | `libx264` | Video codec. |
| `width` | Integer | No | - | Force output width (scales proportionally if height is missing). |
| `height` | Integer | No | - | Force output height. |
| `extra_args` | List | No | `[]` | Additional FFmpeg command-line flags. |
| `existing` | String | No | `replace` | `skip` or `replace`. |

*\*Required only if the path cannot be inferred from the preceding task.*

## Example Usage

### Standard Review Video (Implicit)

This is the most common pattern. The `pathmap` task groups the frames and provides the base path, which `ffmpeg` then uses to create the movie.

```yaml
- name: "movie_sequence"
  type: "pathmap"
  batch: true
  args:
    search: "test-burnin"
    replace: "test-video"
    reduce: true

- name: "video_file"
  type: "ffmpeg"
  args:
    fps: 24
    container: "mp4"
    extra_args: ["-crf", "23", "-preset", "fast"]
```

### Explicit Encoding

```yaml
- name: "manual_video"
  type: "ffmpeg"
  args:
    input_path: "/path/to/frames/shot.%04d.jpg"
    output_path: "/path/to/output/shot_review.mp4"
    fps: 30
    width: 1920
    height: 1080
```

## Internal Command

The task executes a command similar to:
`ffmpeg -y -f concat -safe 0 -r <fps> -i <file_list> -c:v <codec> -pix_fmt yuv420p <extra_args> <output_path>`

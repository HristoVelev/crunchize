# Crunchize

**Crunchize** is an Ansible-inspired batch image processing framework designed for VFX and Animation pipelines. It allows you to define complex image manipulation workflows using simple YAML playbooks, supporting variable substitution, task loops, and parallel execution.

## Features

*   **Playbook-Driven**: Define workflows in declarative YAML files.
*   **Variable Substitution**: Use Jinja2-style `{{ variables }}` for dynamic path and argument resolution.
*   **Parallel Execution**: Automatically distributes tasks across available CPU cores when looping over frame lists.
*   **Modular Architecture**: Easily extensible task system (currently supports OpenColorIO conversions).
*   **Dry Run**: Simulate execution to validate paths and logic before processing.

## Installation

Crunchize requires Python 3.8 or higher.

```bash
# Clone the repository
git clone https://github.com/yourusername/crunchize.git
cd crunchize

# Install with pip
pip install .
```

For development:
```bash
pip install -e .
```

## Usage

The primary entry point is the `crunchize` CLI.

```bash
crunchize run path/to/playbook.yml
```

### Options

*   `-v, --verbose`: Enable debug logging.
*   `--dry-run`: Simulate execution without creating files or running commands.

## Playbook Structure

A playbook consists of **variables** and a list of **tasks**.

### Example: `convert_shot.yml`

```yaml
vars:
  shot: "TS_001"
  # Define a range of frames or a specific list
  frames: ["1001", "1002", "1003", "1004"]
  
  # Paths
  root_dir: "/mnt/projects/my_movie"
  ocio_config: "{{ root_dir }}/config.ocio"
  
  # Colorspaces
  src_space: "ACES - ACEScg"
  dst_space: "Output - sRGB"

tasks:
  - name: "Convert EXR to sRGB Proxy"
    type: "ocio"
    loop: "{{ frames }}"
    args:
      # {{ item }} is the current value from the loop list
      input_path: "{{ root_dir }}/shots/{{ shot }}/exr/{{ shot }}_{{ item }}.exr"
      output_path: "{{ root_dir }}/shots/{{ shot }}/proxy/{{ shot }}_{{ item }}.jpg"
      config_path: "{{ ocio_config }}"
      input_space: "{{ src_space }}"
      output_space: "{{ dst_space }}"
```

## Available Tasks

### OCIO Convert (`type: ocio`)

Wraps the OpenColorIO `ocioconvert` tool to transform image color spaces.

**Arguments:**

*   `input_path`: Path to the source image.
*   `output_path`: Path to the destination image.
*   `config_path`: Path to the `.ocio` configuration file.
*   `input_space`: Name of the input color space.
*   `output_space`: Name of the output color space.

## Development

### Adding a New Task

1.  Create a new file in `src/crunchize/tasks/` (e.g., `ffmpeg.py`).
2.  Inherit from `BaseTask`.
3.  Implement `validate_args` and `run`.

```python
from crunchize.tasks.base import BaseTask

class FFmpegTask(BaseTask):
    def validate_args(self):
        if "input" not in self.args:
            raise ValueError("Missing input")

    def run(self):
        # Implementation here
        pass
```

The engine will automatically discover the task if the type name matches the module name (or you can register it explicitly in the engine logic).

## License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.
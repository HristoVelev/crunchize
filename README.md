# Crunchize

**Crunchize** is a high-performance, Ansible-inspired batch image processing framework built specifically for VFX and Animation pipelines. It allows you to define complex image manipulation workflows using simple YAML playbooks, featuring a simplified data model, implicit task flow, and parallel execution by default.

## Core Concepts

*   **Simplified Data Model**: Tasks pass light objects (usually a single path string or a `{src, dst}` pair) down the pipeline.
*   **Implicit Flow**: Tasks automatically receive the output of the preceding task as their input unless explicitly overridden.
*   **Task Name as Variable**: Every task's result is automatically available as a variable named after the task, making branching effortless.
*   **Parallel Execution**: Image-per-frame tasks are automatically distributed across CPU cores.
*   **Sequence Aware**: Built-in logic for handling VFX frame sequences, including smart stride filtering (`file_amount`) that preserves shot coverage.

## Installation

Crunchize requires Python 3.8 or higher and common VFX tools (`ocioconvert`, `oiiotool`, `ffmpeg`).

```bash
# Clone the repository
git clone https://github.com/crunchize/crunchize.git
cd crunchize

# Install with pip
pip install .
```

## Quick Start

Run a playbook with variable substitution:

```bash
crunchize run playbooks/examples/01_basic_conversion.yml \
  -e "input_pattern=/path/to/plates/*.exr" \
  --dry-run
```

## Playbook Structure

A playbook consists of global `config`, shared `vars`, and a sequence of `tasks`.

```yaml
config:
  file_amount: 1.0  # Process all files (use 0.1 for a quick 10% QC run)

vars:
  ocio_config: "/path/to/config.ocio"

tasks:
  - name: "source_files"
    type: "filein"
    args:
      pattern: "{{ input_pattern }}"

  - name: "proxy_mapping"
    type: "pathmap"
    # Implicitly takes 'source_files'
    args:
      search: "PLATES"
      replace: "PROXIES"

  - name: "convert_to_jpg"
    type: "convert"
    # Implicitly takes 'src' and 'dst' from 'proxy_mapping'
    args:
      output_format: "jpg"
      config_path: "{{ ocio_config }}"
      input_space: "ACEScg"
      output_space: "sRGB"
```

## CLI Options

*   `run <playbook>`: Execute the specified playbook.
*   `-v, --verbose`: Enable debug logging and internal task state.
*   `--dry-run`: Simulate execution without creating files or running commands.
*   `--file-amount <float>`: Override playbook config to process a subset of frames (0.0 - 1.0). Uses stride logic to ensure coverage of all shots.
*   `--every-nth <int>`: Process every Nth frame in a sequence.
*   `-e "key=value"`: Inject or override variables at runtime.

## Core Tasks

| Type | Description |
| :--- | :--- |
| `filein` | Gathers files using glob patterns. |
| `pathmap` | Manipulates paths for rerooting or sequence reduction. |
| `convert` | OCIO color space conversion using `ocioconvert`. |
| `oiio` | Image resizing and manipulation using `oiiotool`. |
| `inscribe` | Powerful layout engine for Slates and Burn-ins (text/images/metadata). |
| `ffmpeg` | Video encoding from image sequences. |
| `thumbnail` | Generate mid-sequence poster frames. |
| `parsepath` | Extract metadata (Seq, Shot, Ver) from paths using regex. |

## Development

### Adding a New Task

Create a new file in `src/crunchize/tasks/` (e.g., `resize.py`):

```python
from crunchize.tasks.base import BaseTask

class ResizeTask(BaseTask):
    def validate_args(self):
        # Validation logic
        pass

    def run(self):
        # Implicitly resolve paths from previous task
        input_path = self._resolve_path_from_item(self.args.get("item"), prioritize_file=True)
        # Your logic here...
        return output_path
```

## License

This project is licensed under the Apache 2.0 License.
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

try:
    from PIL import Image, ImageDraw, ImageFont

    HAS_PILLOW = True
except ImportError:
    HAS_PILLOW = False
    Image = ImageDraw = ImageFont = None

from crunchize.tasks.base import BaseTask


class InscribeTask(BaseTask):
    """
    Task to create slates and burn-ins using a CSS-inspired layout engine.
    Unified with the standard file-to-file processing pattern.
    """

    def validate_args(self) -> None:
        """Verify that all required arguments and dependencies are present."""
        if not HAS_PILLOW:
            raise RuntimeError(
                "InscribeTask requires 'Pillow' library. Please install it with 'pip install Pillow'."
            )

        task_type = self.args.get("type", "burnin")

        if "output_path" not in self.args and "item" not in self.args and "items" not in self.args:
            raise ValueError(
                "InscribeTask requires 'output_path' or implicit 'item'/'items' with mapping."
            )

        task_type = self.args.get("type", "burnin")
        if task_type not in ["slate", "burnin"]:
            raise ValueError("InscribeTask 'type' must be 'slate' or 'burnin'.")

        if (
            task_type == "burnin"
            and "input_path" not in self.args
            and "item" not in self.args
            and "items" not in self.args
        ):
            raise ValueError(
                "InscribeTask 'burnin' type requires 'input_path' or implicit 'item'."
            )

        if "groups" not in self.args:
            raise ValueError("InscribeTask requires 'groups' list.")

        existing = self.args.get("existing", "replace")
        if existing not in ["skip", "replace"]:
            raise ValueError(
                f"Invalid value for 'existing': {existing}. Must be 'skip' or 'replace'."
            )

    def run(self) -> Union[str, List[str]]:
        """
        Execute the inscribe task (process a single file or generate a slate).
        """
        # Determine task type: 'burnin' (overlay on existing) or 'slate' (new image).
        task_type = self.args.get("type", "burnin")
        item = self.args.get("item")
        items = self.args.get("items")
        output_path = self.args.get("output_path")

        # If output_path is missing, try to infer it from the framework context.
        # This supports the simplified data model where paths are mapped in previous tasks.
        if not output_path:
            source_item = (
                item
                if item
                else (items[0] if isinstance(items, list) and items else None)
            )
            output_path = self._resolve_path_from_item(
                source_item, prioritize_file=False
            )

            # For slates, we automatically force the frame number to 0000.
            if task_type == "slate" and output_path:
                output_path = re.sub(
                    r"([._])\d+(\.[a-zA-Z0-9]+)$", r"\g<1>0000\g<2>", str(output_path)
                )

        if not output_path:
            raise ValueError("InscribeTask could not determine 'output_path'.")

        existing = self.args.get("existing", "replace")

        # Ensure the output path has the correct extension for the requested format.
        output_format = self.args.get("format", "jpg").lstrip(".")
        if not output_path.lower().endswith(f".{output_format}"):
            output_path = f"{os.path.splitext(output_path)[0]}.{output_format}"

        if existing == "skip" and os.path.exists(output_path):
            self.logger.info(f"Skipping inscribe: {output_path} already exists.")
            return output_path

        if task_type == "slate":
            return self._handle_slate(output_path)
        else:
            return self._handle_burnin(output_path)

    def _get_frame_num(self, item: Any) -> int:
        """
        Robustly extract the frame number from a string path or framework context object.
        """
        path = self._resolve_path_from_item(item, prioritize_file=True)

        if not path:
            return 0

        # VFX sequences typically use .NNNN.ext or _NNNN.ext
        # We look for digits preceded by . or _ and followed by .ext
        match = re.search(r"([._])(\d+)\.[a-zA-Z0-9]+$", str(path))
        if match:
            return int(match.group(2))

        # Fallback: just look for the last set of digits before the extension
        match = re.search(r"(\d+)\.[^.]+$", str(path))
        return int(match.group(1)) if match else 0

    def _get_frame_context(self) -> Dict[str, Any]:
        """
        Build a dictionary of sequence-aware variables for use in text templates.
        This provides variables like {{ frame }}, {{ filename }}, and {{ basename }}.
        """
        item = self.args.get("item")
        items = self.args.get("items")

        # In slate mode (batch), use the first frame of the sequence for metadata context.
        if not item and isinstance(items, list) and items:
            item = items[0]

        # Determine source filename
        path = self._resolve_path_from_item(item, prioritize_file=True)
        filename = os.path.basename(path) if path else ""

        # Derive a "clean" filename (no frame, no extension) if possible
        clean_name = filename
        # Regex matches something followed by .FRAME.ext or _FRAME.ext
        match = re.search(r"^(.*?)[._]\d+\.[a-zA-Z0-9]+$", filename)
        if match:
            clean_name = match.group(1)
        else:
            clean_name = os.path.splitext(filename)[0]

        ctx = {
            "frame": self._get_frame_num(item),
            "filename": filename,
            "basename": clean_name,
            "index": self.args.get("index", 0),
            "total": self.args.get("total", 1),
        }

        # Sequence bounds injected by the engine
        if "first_item" in self.args:
            ctx["first_frame"] = self._get_frame_num(self.args["first_item"])
        if "last_item" in self.args:
            ctx["last_frame"] = self._get_frame_num(self.args["last_item"])

        return ctx

    def _handle_slate(self, output_path: str) -> Union[str, List[str]]:
        """
        Generate a standalone slate image (starting from a black canvas).
        """
        # If input_files is provided, we assume we want to prepend the slate to the sequence.
        input_files = self.args.get("input_files")
        items = self.args.get("items")

        # If input_files is missing but we have items, try to infer the list of files
        if not input_files and isinstance(items, list):
            input_files = [
                self._resolve_path_from_item(it, prioritize_file=True)
                for it in items
                if self._resolve_path_from_item(it, prioritize_file=True)
            ]

        width = self.args.get("width", 1920)
        height = self.args.get("height", 1080)

        img = Image.new("RGB", (width, height), color=(0, 0, 0))

        # Render using sequence context if available
        self._render_layout(img, self._get_frame_context())

        if not self.dry_run:
            os.makedirs(os.path.dirname(output_path), exist_ok=True)
            img.save(output_path)
            self.logger.info(f"Generated slate: {output_path}")

        # Sequence Expansion: If we have an input sequence, return a new list
        # that includes the slate at the beginning. This allows the whole
        # package to be passed to video encoders.
        if isinstance(input_files, list):
            return [output_path] + input_files

        return output_path

    def _handle_burnin(self, output_path: str) -> str:
        """
        Apply a burn-in layout (metadata overlay) over an existing source image.
        """
        item = self.args.get("item")
        input_path = self.args.get("input_path") or item
        input_path = self._resolve_path_from_item(input_path, prioritize_file=True)

        if not input_path or (not os.path.exists(str(input_path)) and not self.dry_run):
            raise ValueError(
                f"InscribeTask (burnin) could not find input file: {input_path}"
            )

        if not self.dry_run:
            try:
                img = Image.open(str(input_path)).convert("RGB")
                self._render_layout(img, self._get_frame_context())
                os.makedirs(os.path.dirname(output_path), exist_ok=True)
                img.save(output_path)
                self.logger.info(f"Applied burn-in: {output_path}")
            except Exception as e:
                self.logger.error(f"Failed to apply burn-in to {input_path}: {e}")
                raise
        else:
            self.logger.info(
                f"Dry-run: Would apply burn-in {input_path} -> {output_path}"
            )

        return output_path

    def _render_layout(self, img: Image.Image, context: Dict[str, Any]):
        """
        Executes the rendering of all layout groups onto the provided image.
        """
        draw = ImageDraw.Draw(img)
        groups = self.args.get("groups", [])

        # Resolve the font to use. Falls back to common system fonts if not specified.
        font_path = self.args.get("font_path")
        if not font_path:
            font_candidates = [
                "/usr/share/fonts/liberation-mono/LiberationMono-Regular.ttf",
                "/usr/share/fonts/dejavu-sans-mono-fonts/DejaVuSansMono.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
                "/System/Library/Fonts/Courier.dfont",
                "C:\\Windows\\Fonts\\cour.ttf",
            ]
            for cp in font_candidates:
                if os.path.exists(cp):
                    font_path = cp
                    break

        for group_def in groups:
            self._render_group(img, draw, group_def, font_path, context)

    def _render_group(
        self,
        img: Image.Image,
        draw: ImageDraw.ImageDraw,
        group_def: Dict[str, Any],
        font_path: str,
        context: Dict[str, Any],
    ):
        """
        Renders a single group of items (text/images) relative to an anchor point.
        Items within a group are laid out vertically or horizontally with alignment.
        """
        canvas_width, canvas_height = img.size
        anchor = group_def.get("anchor", "top-left")
        layout = group_def.get("layout", "vertical")
        padding_rel = group_def.get("padding", 0.02)
        alignment = group_def.get("alignment", "start")
        items_def = group_def.get("items", [])
        padding = int(canvas_width * padding_rel)

        # Merge engine variables, frame context, and current item attributes
        resolve_ctx = self.args.get("_variables", {}).copy()
        resolve_ctx.update(context)
        item_obj = self.args.get("item")
        if isinstance(item_obj, dict):
            resolve_ctx.update(item_obj)

        rendered_items = []
        for item_def in items_def:
            item_type = item_def.get("type", "text")
            size_rel = item_def.get("size", 0.03)
            size_px = int(canvas_width * size_rel)

            if item_type == "text":
                raw_source = str(item_def.get("source", ""))
                source = self._resolve_local_variables(raw_source, resolve_ctx)
                color = item_def.get("color", "white")
                try:
                    font = (
                        ImageFont.truetype(font_path, size_px)
                        if font_path
                        else ImageFont.load_default()
                    )
                except:
                    font = ImageFont.load_default()

                left, top, right, bottom = draw.textbbox((0, 0), source, font=font)
                rendered_items.append(
                    {
                        "type": "text",
                        "content": source,
                        "font": font,
                        "size": (right - left, bottom - top),
                        "color": color,
                    }
                )

            elif item_type == "image":
                path_raw = str(item_def.get("source", ""))
                path = self._resolve_local_variables(path_raw, resolve_ctx)
                if path and os.path.exists(path):
                    try:
                        item_img = Image.open(path).convert("RGBA")
                        asp = item_img.width / item_img.height
                        w = size_px
                        h = int(w / asp)
                        resample = getattr(Image, "Resampling", Image).LANCZOS
                        item_img = item_img.resize((w, h), resample)
                        rendered_items.append(
                            {"type": "image", "content": item_img, "size": (w, h)}
                        )
                    except Exception as e:
                        self.logger.warning(f"Failed to load layout image {path}: {e}")

        if not rendered_items:
            return

        # Calc layout size
        if layout == "vertical":
            group_w = max(i["size"][0] for i in rendered_items)
            group_h = sum(i["size"][1] for i in rendered_items) + (
                padding * (len(rendered_items) - 1)
            )
        else:
            group_w = sum(i["size"][0] for i in rendered_items) + (
                padding * (len(rendered_items) - 1)
            )
            group_h = max(i["size"][1] for i in rendered_items)

        # Resolve anchor origin
        gx, gy = 0, 0
        if "left" in anchor:
            gx = padding
        elif "right" in anchor:
            gx = canvas_width - group_w - padding
        else:
            gx = (canvas_width - group_w) // 2

        if "top" in anchor:
            gy = padding
        elif "bottom" in anchor:
            gy = canvas_height - group_h - padding
        else:
            gy = (canvas_height - group_h) // 2

        # Draw items
        cx, cy = gx, gy
        for item in rendered_items:
            iw, ih = item["size"]
            dx, dy = cx, cy

            if layout == "vertical":
                if alignment == "center":
                    dx = gx + (group_w - iw) // 2
                elif alignment == "end":
                    dx = gx + (group_w - iw)
                if item["type"] == "text":
                    draw.text(
                        (dx, dy), item["content"], font=item["font"], fill=item["color"]
                    )
                else:
                    img.paste(item["content"], (dx, dy), item["content"])
                cy += ih + padding
            else:
                if alignment == "center":
                    dy = gy + (group_h - ih) // 2
                elif alignment == "end":
                    dy = gy + (group_h - ih)
                if item["type"] == "text":
                    draw.text(
                        (dx, dy), item["content"], font=item["font"], fill=item["color"]
                    )
                else:
                    img.paste(item["content"], (dx, dy), item["content"])
                cx += iw + padding

    def _resolve_local_variables(self, text: str, context: Dict[str, Any]) -> str:
        """
        A local template resolver that supports variable substitution and filters.
        Used to resolve text content within the inscribe layout engine.
        """
        pattern = r"\{\{\s*([^}]+)\s*\}\}"

        def replace(match):
            expr_str = match.group(1).strip()
            if "|" in expr_str:
                parts = [x.strip() for x in expr_str.split("|")]
                var_expr = parts[0].strip()
                filters = parts[1:]
            else:
                var_expr, filters = expr_str, []

            val = None
            found = False

            # 1. Try direct lookup (supports keys with literal dots)
            if var_expr in context:
                val = context[var_expr]
                found = True

            # 2. Try nested lookup
            if not found:
                path_parts = re.findall(
                    r"([a-zA-Z0-9_]+|\[\d+\]|\[['\"][^'\"]+['\"]\])", var_expr
                )

                if path_parts and path_parts[0] in context:
                    val = context[path_parts[0]]
                    found = True
                    try:
                        for part in path_parts[1:]:
                            if part.startswith("[") and part.endswith("]"):
                                inner = part[1:-1]
                                if (inner.startswith("'") and inner.endswith("'")) or (
                                    inner.startswith('"') and inner.endswith('"')
                                ):
                                    val = val[inner[1:-1]]
                                else:
                                    val = val[int(inner)]
                            elif isinstance(val, dict):
                                val = val[part]
                            else:
                                val = getattr(val, part)
                    except:
                        found = False

            if not found:
                return match.group(0)

            for f_expr in filters:
                f = f_expr.strip()
                if f.startswith("replace"):
                    m = re.search(
                        r"replace\(\s*['\"]([^'\"]*)['\"]\s*,\s*['\"]([^'\"]*)['\"]\s*\)",
                        f,
                    )
                    if m and isinstance(val, str):
                        old, new = m.groups()
                        val = val.replace(old, new)
                elif f == "basename":
                    val = os.path.basename(str(val))
                elif f == "dirname":
                    val = os.path.dirname(str(val))
                elif f.startswith("map"):
                    m = re.search(r"attribute=['\"]([^'\"]+)['\"]", f)
                    if m and isinstance(val, list):
                        attr = m.group(1)
                        val = [
                            (
                                i.get(attr)
                                if isinstance(i, dict)
                                else getattr(i, attr, None)
                            )
                            for i in val
                        ]
                elif f == "list":
                    val = list(val)

            return str(val)

        return re.sub(pattern, replace, text)

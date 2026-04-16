#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


def _render_app(variant: str, title: str) -> str:
    if variant == "transform":
        return f'''import gradio as gr


def transform(text, mode):
    if mode == "upper":
        return text.upper()
    if mode == "reverse":
        return text[::-1]
    return text.title()


demo = gr.Interface(
    fn=transform,
    inputs=[
        gr.Textbox(label="Input"),
        gr.Radio(["upper", "reverse", "title"], value="upper", label="Mode"),
    ],
    outputs=gr.Textbox(label="Output"),
    title={title!r},
)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
'''
    return f'''import gradio as gr


def greet(name):
    name = name.strip() or "world"
    return f"Hello, {{name}}!"


demo = gr.Interface(
    fn=greet,
    inputs=gr.Textbox(label="Name"),
    outputs=gr.Textbox(label="Greeting"),
    title={title!r},
)


if __name__ == "__main__":
    demo.launch(server_name="0.0.0.0", server_port=7860)
'''


def main() -> int:
    parser = argparse.ArgumentParser(description="Materialize a minimal Gradio toy app.")
    parser.add_argument("--output-dir", required=True, help="Directory to write the toy app into.")
    parser.add_argument(
        "--variant",
        choices=["echo", "transform"],
        default="echo",
        help="Toy app variant to generate.",
    )
    parser.add_argument("--title", default="Codex Toy Demo", help="Gradio app title.")
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite an existing output directory.",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    if output_dir.exists():
        if not args.force:
            raise SystemExit(f"Output directory already exists: {output_dir}. Pass --force to overwrite it.")
        shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "app.py").write_text(_render_app(args.variant, args.title), encoding="utf-8")
    (output_dir / "requirements.txt").write_text("gradio>=6.0,<7.0\n", encoding="utf-8")

    print(
        json.dumps(
            {
                "output_dir": str(output_dir),
                "variant": args.variant,
                "title": args.title,
                "files": ["app.py", "requirements.txt"],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

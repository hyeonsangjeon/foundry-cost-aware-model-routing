"""Reader-facing naming guarantees.

The synthetic experiment-07 arm is a generic ``single-call`` projection. Only
real product arms may be called "Model Router", and the product name must never
share a reader-visible block with the synthetic 52% coverage figure.

These tests exercise the semantic block splitter directly so the guarantee is
enforced at the paragraph / card / table-row level rather than per line.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
_MODULE_PATH = REPO_ROOT / "scripts" / "check_naming_surfaces.py"

_spec = importlib.util.spec_from_file_location("check_naming_surfaces", _MODULE_PATH)
assert _spec and _spec.loader
naming = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = naming
_spec.loader.exec_module(naming)


def test_repository_has_no_product_name_tied_to_synthetic_figure():
    violations = naming.find_violations()
    assert violations == [], "\n".join(
        f"{block.path}:{block.line} [{block.kind}] {block.text[:200]}" for block in violations
    )


def test_checker_scans_a_meaningful_number_of_surfaces():
    blocks = naming.collect_blocks()
    assert len(blocks) > 500
    paths = {block.path for block in blocks}
    assert "README.md" in paths
    assert "docs/ko/index.md" in paths
    assert "docs/ko/lab-notebook/07-model-router.md" in paths
    assert "src/router/dashboard.py" in paths
    assert "experiments/single-call.yaml" in paths


def test_detects_association_across_wrapped_lines(tmp_path):
    """A same-line grep would miss this; the block splitter must not."""
    doc = "The built-in Model Router picks one model,\nand it holds only 52% coverage.\n"
    blocks = naming._iter_markdown_blocks("wrapped.md", doc)
    assert naming.find_violations(blocks)


def test_detects_association_inside_one_table_row():
    doc = "| 07 | Model Router? | 52% vs 100% |\n"
    blocks = naming._iter_markdown_blocks("table.md", doc)
    violations = naming.find_violations(blocks)
    assert [block.kind for block in violations] == ["table-row"]


def test_detects_association_inside_one_admonition_card():
    doc = '!!! info "title"\n    Model Router is the product.\n\n    Coverage lands at 52%.\n'
    blocks = naming._iter_markdown_blocks("card.md", doc)
    violations = naming.find_violations(blocks)
    assert [block.kind for block in violations] == ["card"]


def test_detects_association_inside_figure_alt_text():
    doc = "![Model Router gauge stalling at 52% coverage](../assets/gif/model-router.gif)\n"
    blocks = naming._iter_markdown_blocks("figure.md", doc)
    assert any(block.kind == "figure-alt" for block in naming.find_violations(blocks))


def test_separate_blocks_are_not_flagged():
    doc = "The built-in Model Router picks one model.\n\nThe single-call arm holds 52% coverage.\n"
    blocks = naming._iter_markdown_blocks("split.md", doc)
    assert naming.find_violations(blocks) == []


def test_preserved_slugs_and_deployment_names_are_not_flagged():
    """URLs, asset filenames and the real deployment id must survive untouched."""
    doc = (
        "See [experiment 07](07-model-router.md) and ![gauge](../assets/gif/model-router.gif).\n"
        "\n"
        "The single-call arm holds 52% coverage.\n"
        "\n"
        "```bash\n"
        "az cognitiveservices account deployment create --deployment-name model-router\n"
        "# Model Router picked the backend; coverage 52%\n"
        "```\n"
    )
    blocks = naming._iter_markdown_blocks("slugs.md", doc)
    assert naming.find_violations(blocks) == []


def test_real_product_experiments_are_not_flagged():
    """Experiments 09/10 measure the real product and carry no synthetic figure."""
    for name in ("09-live-routing-proof.md", "10-measured-ledger.md"):
        path = REPO_ROOT / "docs" / "ko" / "lab-notebook" / name
        blocks = naming._iter_markdown_blocks(name, path.read_text(encoding="utf-8"))
        assert naming.find_violations(blocks) == []

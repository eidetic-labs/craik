from pathlib import Path


def test_instruction_runtime_does_not_log_statement_or_excerpt_values() -> None:
    root = Path(__file__).resolve().parents[1] / "src" / "craik" / "runtime"
    offenders: list[str] = []
    for path in sorted(root.glob("instruction*.py")) + sorted(
        (root / "projects").glob("instruction*.py")
    ):
        for index, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if "logger." not in line:
                continue
            if "statement" in line or "excerpt" in line:
                offenders.append(f"{path.relative_to(root.parents[2])}:{index}")

    assert offenders == []

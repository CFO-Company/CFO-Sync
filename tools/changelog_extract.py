from __future__ import annotations

import argparse
import re
from pathlib import Path


HEADER_PATTERN = re.compile(r"^##\s+\[(?P<version>[^\]]+)\](?:\s+-\s+.+)?\s*$")


def extract_section(changelog_path: Path, version: str) -> str:
    text = changelog_path.read_text(encoding="utf-8-sig")
    lines = text.splitlines()

    start = _find_header_line(lines, version)
    if start is None:
        raise ValueError(f"Versao {version} nao encontrada em {changelog_path}")

    end = len(lines)
    for index in range(start + 1, len(lines)):
        if HEADER_PATTERN.match(lines[index]):
            end = index
            break

    section_lines = lines[start:end]
    section = "\n".join(section_lines).strip()
    if not section:
        raise ValueError(f"Secao da versao {version} vazia em {changelog_path}")
    return section + "\n"


def _find_header_line(lines: list[str], version: str) -> int | None:
    target = version.strip().lower().removeprefix("v")
    for index, line in enumerate(lines):
        match = HEADER_PATTERN.match(line)
        if not match:
            continue
        found = match.group("version").strip().lower().removeprefix("v")
        if found == target:
            return index
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Extrai secao de uma versao do CHANGELOG.md")
    parser.add_argument("--version", required=True, help="Versao alvo, ex: 1.0.0 ou v1.0.0")
    parser.add_argument(
        "--changelog",
        default="CHANGELOG.md",
        help="Caminho do arquivo changelog (default: CHANGELOG.md)",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Arquivo de saida. Se omitido, imprime em stdout.",
    )
    args = parser.parse_args()

    section = extract_section(Path(args.changelog), args.version)
    if args.output:
        Path(args.output).write_text(section, encoding="utf-8")
    else:
        print(section, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Command-line interface: ``python -m subgrant verify|report``.

Exit codes (pinned for ``verify``):
  * 0 — loaded and no findings
  * 1 — loaded with one or more findings
  * 2 — input error (schema / parse); an error message, never a finding
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from . import __version__
from .checks import load_policy_pack, run_checks
from .graph import GraphError, load_graph
from .normalizers import normalize as normalize_doc
from .report import build_pack, to_markdown
from .sarif import build_sarif

EXIT_OK = 0
EXIT_FINDINGS = 1
EXIT_INPUT_ERROR = 2


def _read_input(path: str) -> tuple[bytes, Any]:
    """Read bytes from ``path`` (or stdin when ``path == '-'``) and parse JSON."""
    if path == "-":
        raw = sys.stdin.buffer.read()
    else:
        with open(path, "rb") as fh:
            raw = fh.read()
    try:
        doc = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as exc:
        raise GraphError(f"document: not valid JSON: {exc}")
    return raw, doc


def _load(path: str, pack_path: str | None):
    raw, doc = _read_input(path)
    graph = load_graph(doc)
    pack = load_policy_pack(pack_path)
    return raw, graph, pack


def cmd_verify(args: argparse.Namespace) -> int:
    try:
        _raw, graph, pack = _load(args.graph, args.pack)
    except GraphError as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    findings = run_checks(graph, pack)
    if args.sarif:
        uri = args.graph
        print(json.dumps(build_sarif(findings, uri), indent=2))
    elif args.json:
        print(json.dumps([f.as_dict() for f in findings], indent=2))
    else:
        if not findings:
            print("OK: no findings")
        else:
            for f in findings:
                print(f"{f.cls}\t{f.edge}")
    return EXIT_FINDINGS if findings else EXIT_OK


def cmd_normalize(args: argparse.Namespace) -> int:
    try:
        _raw, doc = _read_input(args.file)
        out = normalize_doc(args.format, doc)
    except GraphError as exc:  # NormalizeError is a GraphError subclass
        print(f"schema error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    print(json.dumps(out, indent=2))
    return EXIT_OK


def cmd_report(args: argparse.Namespace) -> int:
    try:
        raw, graph, pack = _load(args.graph, args.pack)
    except GraphError as exc:
        print(f"schema error: {exc}", file=sys.stderr)
        return EXIT_INPUT_ERROR
    findings = run_checks(graph, pack)
    source = None if args.graph == "-" else args.graph
    evidence = build_pack(raw, findings, pack, source=source)
    if args.format == "md":
        print(to_markdown(evidence))
    else:
        print(json.dumps(evidence, indent=2))
    return EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="subgrant", description="Verifier for agent delegation chains.")
    parser.add_argument("--version", action="version", version=f"subgrant {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    pv = sub.add_parser("verify", help="check a dgraph/1 document and exit 0/1/2")
    pv.add_argument("graph", help="path to a dgraph/1 JSON document ('-' for stdin)")
    pv.add_argument("--pack", default=None, help="path to a policy pack (default: delegation-policy-v1)")
    pv.add_argument("--json", action="store_true", help="emit findings as JSON")
    pv.add_argument("--sarif", action="store_true", help="emit findings as SARIF 2.1.0")
    pv.set_defaults(func=cmd_verify)

    pn = sub.add_parser("normalize", help="normalize a source format to a dgraph/1 document")
    pn.add_argument("format", choices=("ucan", "rfc8693", "attenu", "descriptor"), help="source format")
    pn.add_argument("file", help="path to the source JSON document ('-' for stdin)")
    pn.set_defaults(func=cmd_normalize)

    pr = sub.add_parser("report", help="emit a hash-chained evidence pack")
    pr.add_argument("graph", help="path to a dgraph/1 JSON document ('-' for stdin)")
    pr.add_argument("--pack", default=None, help="path to a policy pack (default: delegation-policy-v1)")
    pr.add_argument("--format", choices=("json", "md"), default="json", help="output format")
    pr.set_defaults(func=cmd_report)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())

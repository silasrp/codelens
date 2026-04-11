"""
AST-based code parser using tree-sitter.

Supports Python, TypeScript, and JavaScript. Extracts structured
representations of functions, classes, and modules without relying
on regex or line-count heuristics.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

try:
    import tree_sitter_python as tspython
    import tree_sitter_typescript as tstypescript
    import tree_sitter_javascript as tsjavascript
    from tree_sitter import Language, Parser, Node
    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False


Language_ = Literal["python", "typescript", "javascript"]

EXTENSION_MAP: dict[str, Language_] = {
    ".py":  "python",
    ".ts":  "typescript",
    ".tsx": "typescript",
    ".js":  "javascript",
    ".jsx": "javascript",
}


@dataclass
class CodeSymbol:
    name: str
    kind: Literal["function", "class", "method", "module"]
    language: Language_
    source: str
    start_line: int
    end_line: int
    file_path: str
    parent_name: str | None = None
    docstring: str | None = None
    imports: list[str] = field(default_factory=list)

    @property
    def chunk_id(self) -> str:
        key = f"{self.file_path}::{self.name}::{self.start_line}"
        return hashlib.sha256(key.encode()).hexdigest()[:16]

    @property
    def line_count(self) -> int:
        return self.end_line - self.start_line + 1


@dataclass
class ParsedFile:
    file_path: str
    language: Language_
    symbols: list[CodeSymbol]
    module_imports: list[str]
    raw_source: str

    @property
    def module_name(self) -> str:
        return Path(self.file_path).stem

    @property
    def symbol_count(self) -> int:
        return len(self.symbols)


class ASTParser:
    def __init__(self) -> None:
        self._parsers: dict[Language_, "Parser"] = {}
        if TREE_SITTER_AVAILABLE:
            self._init_parsers()

    def _init_parsers(self) -> None:
        lang_map = {
            "python":     tspython.language(),
            "typescript": tstypescript.language_typescript(),
            "javascript": tsjavascript.language(),
        }
        for name, lang_func in lang_map.items():
            try:
                language = Language(lang_func)
                parser = Parser(language)
                self._parsers[name] = parser
            except Exception:
                pass

    def can_parse(self, file_path: str) -> bool:
        return Path(file_path).suffix.lower() in EXTENSION_MAP

    def parse_file(self, file_path: str, source: str) -> ParsedFile | None:
        ext = Path(file_path).suffix.lower()
        language = EXTENSION_MAP.get(ext)
        if not language:
            return None
        if not TREE_SITTER_AVAILABLE or language not in self._parsers:
            return self._fallback_parse(file_path, language, source)

        parser = self._parsers[language]
        tree = parser.parse(source.encode())
        symbols = self._extract_symbols(tree.root_node, source, file_path, language)
        imports = self._extract_imports(tree.root_node, source, language)
        return ParsedFile(file_path=file_path, language=language,
                          symbols=symbols, module_imports=imports, raw_source=source)

    def _extract_symbols(self, root: "Node", source: str, file_path: str,
                         language: Language_) -> list[CodeSymbol]:
        symbols: list[CodeSymbol] = []
        lines = source.splitlines()

        def walk(node: "Node", parent_class: str | None = None) -> None:
            if language == "python":
                self._walk_python(node, lines, file_path, language, symbols, parent_class)
            else:
                self._walk_ts(node, lines, file_path, language, symbols, parent_class)
            new_parent = parent_class
            if node.type == "class_definition" and language == "python":
                name_node = node.child_by_field_name("name")
                if name_node:
                    txt = name_node.text
                    new_parent = txt.decode() if isinstance(txt, bytes) else str(txt)
            for child in node.children:
                walk(child, new_parent)

        walk(root)
        return symbols

    def _walk_python(self, node: "Node", lines: list[str], file_path: str,
                     language: Language_, out: list[CodeSymbol],
                     parent_class: str | None) -> None:
        if node.type == "function_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            # Use name_node.text directly — never read from raw lines
            name_txt = name_node.text
            name = name_txt.decode() if isinstance(name_txt, bytes) else str(name_txt)
            src_bytes = node.text
            src = src_bytes.decode(errors="replace") if isinstance(src_bytes, bytes) else str(src_bytes)
            kind: Literal["function", "method"] = "method" if parent_class else "function"
            out.append(CodeSymbol(
                name=name, kind=kind, language=language, source=src,
                start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                file_path=file_path, parent_name=parent_class,
                docstring=self._python_docstring(node),
            ))
        elif node.type == "class_definition":
            name_node = node.child_by_field_name("name")
            if not name_node:
                return
            name_txt = name_node.text
            name = name_txt.decode() if isinstance(name_txt, bytes) else str(name_txt)
            src_bytes = node.text
            src = src_bytes.decode(errors="replace") if isinstance(src_bytes, bytes) else str(src_bytes)
            out.append(CodeSymbol(
                name=name, kind="class", language=language,
                source=self._class_header(src),
                start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                file_path=file_path,
            ))

    def _walk_ts(self, node: "Node", lines: list[str], file_path: str,
                 language: Language_, out: list[CodeSymbol],
                 parent_class: str | None) -> None:
        if node.type in {"function_declaration", "arrow_function",
                         "method_definition", "function_expression"}:
            name = self._ts_name(node)
            src_bytes = node.text
            src = src_bytes.decode(errors="replace") if isinstance(src_bytes, bytes) else str(src_bytes)
            kind_: Literal["function", "method"] = "method" if parent_class else "function"
            out.append(CodeSymbol(
                name=name or "<anonymous>", kind=kind_, language=language, source=src,
                start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                file_path=file_path, parent_name=parent_class,
            ))
        elif node.type == "class_declaration":
            name_node = node.child_by_field_name("name")
            txt = name_node.text if name_node else b"UnknownClass"
            name = txt.decode() if isinstance(txt, bytes) else str(txt)
            src_bytes = node.text
            src = src_bytes.decode(errors="replace") if isinstance(src_bytes, bytes) else str(src_bytes)
            out.append(CodeSymbol(
                name=name, kind="class", language=language,
                source=self._class_header(src),
                start_line=node.start_point[0] + 1, end_line=node.end_point[0] + 1,
                file_path=file_path,
            ))

    def _ts_name(self, node: "Node") -> str | None:
        name_node = node.child_by_field_name("name")
        if name_node:
            txt = name_node.text
            return txt.decode() if isinstance(txt, bytes) else str(txt)
        if node.parent and node.parent.type in ("variable_declarator", "assignment_expression"):
            nn = node.parent.child_by_field_name("name")
            if nn:
                txt = nn.text
                return txt.decode() if isinstance(txt, bytes) else str(txt)
        return None

    def _extract_imports(self, root: "Node", source: str, language: Language_) -> list[str]:
        imports: list[str] = []
        targets = {
            "python":     {"import_statement", "import_from_statement"},
            "typescript": {"import_statement", "import_declaration"},
            "javascript": {"import_statement", "import_declaration"},
        }.get(language, set())

        def walk(node: "Node") -> None:
            if node.type in targets:
                txt = node.text
                imports.append(txt.decode(errors="replace") if isinstance(txt, bytes) else str(txt))
            for child in node.children:
                walk(child)
        walk(root)
        return imports

    def _python_docstring(self, func_node: "Node") -> str | None:
        body = func_node.child_by_field_name("body")
        if not body:
            return None
        for child in body.children:
            if child.type == "expression_statement":
                for gc in child.children:
                    if gc.type in ("string", "concatenated_string"):
                        txt = gc.text
                        raw = txt.decode(errors="replace") if isinstance(txt, bytes) else str(txt)
                        return raw.strip('"""').strip("'''").strip('"\'').strip()
        return None

    def _class_header(self, src: str) -> str:
        lines = src.splitlines()
        header: list[str] = []
        for i, line in enumerate(lines):
            if i == 0:
                header.append(line)
                continue
            if line.strip().startswith(("def ", "async def ", "constructor")):
                break
            header.append(line)
        return "\n".join(header)

    def _fallback_parse(self, file_path: str, language: Language_, source: str) -> ParsedFile:
        import re
        symbols: list[CodeSymbol] = []
        if language == "python":
            for m in re.finditer(r"^(class|def|async def)\s+(\w+)", source, re.MULTILINE):
                line_num = source[:m.start()].count("\n") + 1
                kind_: Literal["function", "class"] = "class" if "class" in m.group(1) else "function"
                symbols.append(CodeSymbol(
                    name=m.group(2), kind=kind_, language=language,
                    source=m.group(0), start_line=line_num, end_line=line_num,
                    file_path=file_path,
                ))
        imports = [l.strip() for l in source.splitlines()
                   if l.strip().startswith(("import ", "from "))]
        return ParsedFile(file_path=file_path, language=language,
                          symbols=symbols, module_imports=imports, raw_source=source)

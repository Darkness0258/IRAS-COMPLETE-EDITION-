from __future__ import annotations

import ast
from dataclasses import dataclass, asdict
import json
from pathlib import Path
import re
from typing import Any


@dataclass
class GraphNode:
    node_id: str
    kind: str
    name: str
    path: str
    line: int = 0
    metadata: dict[str, Any] | None = None


@dataclass
class GraphEdge:
    source: str
    target: str
    relation: str


class ProjectKnowledgeGraph:
    """Static project map for code, dependencies, routes, tests, DB and deploy files."""

    ROUTE_DECORATORS = {"get", "post", "put", "patch", "delete", "websocket"}

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.nodes: dict[str, GraphNode] = {}
        self.edges: list[GraphEdge] = []

    def _add_node(self, node: GraphNode):
        self.nodes[node.node_id] = node

    def build(self, *, max_files: int = 3000) -> dict[str, Any]:
        self.nodes.clear(); self.edges.clear()
        py_files = [p for p in self.root.rglob("*.py") if ".git" not in p.parts and "__pycache__" not in p.parts][:max_files]
        for path in py_files:
            self._scan_python(path)
        self._scan_dependencies()
        self._scan_sql(max_files=max_files)
        self._scan_deployment()
        test_modules = [n for n in self.nodes.values() if n.kind == "module" and (n.path.startswith("tests/") or Path(n.path).name.startswith("test_"))]
        return {
            "root": str(self.root), "nodes": len(self.nodes), "edges": len(self.edges),
            "test_modules": len(test_modules),
            "routes": sum(1 for n in self.nodes.values() if n.kind == "api_route"),
            "database_tables": sum(1 for n in self.nodes.values() if n.kind == "database_table"),
            "dependencies": sum(1 for n in self.nodes.values() if n.kind == "dependency"),
        }

    def _scan_python(self, path: Path) -> None:
        rel = path.relative_to(self.root).as_posix()
        mod = rel[:-3].replace("/", ".")
        if mod.endswith(".__init__"):
            mod = mod[:-9]
        node_id = "module:" + mod
        self._add_node(GraphNode(node_id, "module", mod, rel))
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
        except Exception:
            return
        for item in ast.walk(tree):
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                kind = "class" if isinstance(item, ast.ClassDef) else "function"
                cid = f"{kind}:{mod}:{item.name}:{getattr(item,'lineno',0)}"
                self._add_node(GraphNode(cid, kind, item.name, rel, getattr(item, "lineno", 0)))
                self.edges.append(GraphEdge(node_id, cid, "contains"))
                if not isinstance(item, ast.ClassDef):
                    for deco in item.decorator_list:
                        if isinstance(deco, ast.Call) and isinstance(deco.func, ast.Attribute) and deco.func.attr in self.ROUTE_DECORATORS:
                            route = ""
                            if deco.args and isinstance(deco.args[0], ast.Constant):
                                route = str(deco.args[0].value)
                            rid = f"route:{deco.func.attr}:{route}:{rel}:{getattr(item,'lineno',0)}"
                            self._add_node(GraphNode(rid, "api_route", f"{deco.func.attr.upper()} {route}", rel, getattr(item, "lineno", 0), {"handler": item.name}))
                            self.edges.append(GraphEdge(cid, rid, "exposes"))
            elif isinstance(item, ast.Import):
                for alias in item.names:
                    self.edges.append(GraphEdge(node_id, "module:" + alias.name, "imports"))
            elif isinstance(item, ast.ImportFrom) and item.module:
                self.edges.append(GraphEdge(node_id, "module:" + item.module, "imports"))

    def _scan_dependencies(self) -> None:
        pyproject = self.root / "pyproject.toml"
        if pyproject.exists():
            text = pyproject.read_text(encoding="utf-8", errors="replace")
            try:
                import tomllib
                data = tomllib.loads(text)
                deps = data.get("project", {}).get("dependencies", [])
                for dep in deps:
                    name = re.split(r"[<>=!~\[ ]", str(dep), 1)[0]
                    did = "dependency:python:" + name.lower()
                    self._add_node(GraphNode(did, "dependency", name, "pyproject.toml", metadata={"ecosystem": "python", "spec": dep}))
            except Exception:
                pass
        package = self.root / "package.json"
        if package.exists():
            try:
                data = json.loads(package.read_text(encoding="utf-8"))
                for section in ("dependencies", "devDependencies"):
                    for name, spec in (data.get(section) or {}).items():
                        did = "dependency:npm:" + name.lower()
                        self._add_node(GraphNode(did, "dependency", name, "package.json", metadata={"ecosystem": "npm", "spec": spec, "section": section}))
            except Exception:
                pass

    def _scan_sql(self, *, max_files: int) -> None:
        pattern = re.compile(r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[\[\"`']?([A-Za-z0-9_.-]+)", re.I)
        files = [p for p in self.root.rglob("*.sql") if ".git" not in p.parts][:max_files]
        # Also inspect Python strings containing schema DDL.
        files += [p for p in self.root.rglob("*.py") if ".git" not in p.parts][:max_files]
        seen = set()
        for path in files:
            try: text = path.read_text(encoding="utf-8", errors="replace")
            except Exception: continue
            for match in pattern.finditer(text):
                table = match.group(1)
                key = table.lower()
                if key in seen: continue
                seen.add(key)
                rel = path.relative_to(self.root).as_posix()
                self._add_node(GraphNode("table:" + key, "database_table", table, rel))

    def _scan_deployment(self) -> None:
        for name in ("Dockerfile", "render.yaml", "render.yml", "docker-compose.yml", "docker-compose.yaml", ".github/workflows/ci.yml"):
            path = self.root / name
            if path.exists():
                self._add_node(GraphNode("deploy:" + name, "deployment", name, name))

    def neighbors(self, node_id: str, *, relation: str | None = None) -> list[dict[str, Any]]:
        return [asdict(e) for e in self.edges if e.source == node_id and (relation is None or e.relation == relation)]

    def search(self, query: str, limit: int = 20) -> list[dict[str, Any]]:
        q = query.lower()
        rows = [asdict(n) for n in self.nodes.values() if q in n.name.lower() or q in n.path.lower() or q in n.kind.lower()]
        return rows[:limit]

    def export(self, path: str | Path) -> str:
        path = Path(path)
        data = {"root": str(self.root), "nodes": [asdict(n) for n in self.nodes.values()], "edges": [asdict(e) for e in self.edges]}
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        return str(path)

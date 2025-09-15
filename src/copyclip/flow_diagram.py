# graph TD;
import ast
import hashlib
import re
from functools import lru_cache
from typing import Dict, List, Union, Tuple, Optional
# Brief: Node
# Brief: Node

# Brief: Node
class Node:
    def __init__(self, name: str, node_type: str, children: List['Node'] = None):
        self.name = name
        self.node_type = node_type
        self.children = children or []

    def to_mermaid(self, parent_id: str = None, node_id: int = 0, nodes=None, edges=None,
                   max_depth: int = None, current_depth: int = 0, collapse_threshold: int = 10):
        if nodes is None:
            nodes = []
        if edges is None:
            edges = []

        # Usar un ID predecible basado en el nombre y un contador para unicidad
        safe_name = re.sub(r'[^a-zA-Z0-9_]', '', self.name)
        current_id = f"{safe_name}_{node_id}"
        label = f"{self.node_type}: {self.name}"
        nodes.append(f'{current_id}["{label}"]')
        
        if parent_id is not None:
            edges.append(f"{parent_id} --> {current_id}")

        next_id = node_id + 1
        
        # Lógica de colapso
        if collapse_threshold is not None and len(self.children) >= collapse_threshold:
            collapsed_label = f"{len(self.children)} children collapsed"
            collapsed_id = f"collapsed_{next_id}"
            nodes.append(f'{collapsed_id}["{collapsed_label}"]')
            edges.append(f"{current_id} --> {collapsed_id}")
            return next_id + 1

        if max_depth is None or current_depth < max_depth:
            for child in self.children:
                next_id = child.to_mermaid(current_id, next_id, nodes, edges,
                                           max_depth=max_depth, current_depth=current_depth + 1,
                                           collapse_threshold=collapse_threshold)
        return next_id

    def render_mermaid(self, collapse_threshold: int = 10) -> str:
        nodes = []
        edges = []
        self.to_mermaid(None, 0, nodes, edges, collapse_threshold=collapse_threshold)
        diagram = "graph TD\n"
        for node in nodes:
            diagram += f"    {node}\n"
        for edge in edges:
            diagram += f"    {edge}\n"
        return diagram

# Brief: FlowDiagramExtractor

# Brief: FlowDiagramExtractor
class FlowDiagramExtractor(ast.NodeVisitor):
    def __init__(self):
        self.root_nodes: List[Node] = []
        self.current_class: Union[Node, None] = None

    def visit_FunctionDef(self, node: ast.FunctionDef):
        func_node = Node(name=node.name, node_type="function")
        if self.current_class:
            self.current_class.children.append(func_node)
        else:
            self.root_nodes.append(func_node)
        # Avoid visiting function body to improve performance
        # self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef):
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef):
        class_node = Node(name=node.name, node_type="class")
        if self.current_class:
            self.current_class.children.append(class_node)
        else:
            self.root_nodes.append(class_node)
        parent_class = self.current_class
        self.current_class = class_node
        self.generic_visit(node)
        self.current_class = parent_class
# Brief: compute_hash

# Brief: compute_hash
def compute_hash(content: str) -> str:
    """
    Compute SHA256 hash of the given content string.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    return hashlib.sha256(content.encode('utf-8')).hexdigest()

# Brief: parse_source_to_nodes
@lru_cache(maxsize=128)
# Brief: parse_source_to_nodes
def parse_source_to_nodes(source_code: str) -> Tuple[Node, str]:
    """
    
        Parse source code into a root Node tree and return with content hash.
        Cached by source_code string.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    tree = ast.parse(source_code)
    extractor = FlowDiagramExtractor()
    extractor.visit(tree)
    root = Node(name="root", node_type="root", children=extractor.root_nodes)
    content_hash = compute_hash(source_code)
    return root, content_hash
# Brief: FlowDiagramCache

# Brief: FlowDiagramCache
class FlowDiagramCache:
    """
    Cache parsed Node trees keyed by file path and content hash.
    Supports incremental parsing by checking file changes.
    """
    def __init__(self):
        self.cache: Dict[str, Tuple[Node, str]] = {}

    def get(self, filepath: str, content: str) -> Node:
        content_hash = compute_hash(content)
        cached = self.cache.get(filepath)
        if cached and cached[1] == content_hash:
            return cached[0]
        # Parse and cache
        root, _ = parse_source_to_nodes(content)
        self.cache[filepath] = (root, content_hash)
        return root
# Brief: generate_combined_mermaid

# Brief: generate_combined_mermaid
def generate_combined_mermaid(diagrams: List[Tuple[str, Node]]) -> str:
    """
    
        Generate a combined Mermaid diagram from multiple (filename, Node) tuples.
        Groups nodes by filename for clarity.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    nodes = []
    edges = []
    node_id = 0
    file_node_ids = {}

    for filename, root_node in diagrams:
        file_node_label = f"file: {filename}"
        file_node_id = f"file_{node_id}"
        nodes.append(f'{file_node_id}["{file_node_label}"]')
        file_node_ids[filename] = file_node_id
        node_id += 1

        def add_nodes(node: Node, parent_id: str):
            nonlocal node_id
            current_id = f"{node_id}"
            label = f"{node.node_type}: {node.name}"
            nodes.append(f'{current_id}["{label}"]')
            edges.append(f"{parent_id} --> {current_id}")
            node_id += 1
            for child in node.children:
                add_nodes(child, current_id)

        for child in root_node.children:
            add_nodes(child, file_node_id)

    diagram = "graph TD\n"
    for node in nodes:
        diagram += f"    {node}\n"
    for edge in edges:
        diagram += f"    {edge}\n"
# Brief: extract_flow_diagram
    return diagram
# Brief: extract_flow_diagram
def extract_flow_diagram(source_code: str) -> str:
    """
    
        Extract a Mermaid flow diagram from Python source code.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    root_node, _ = parse_source_to_nodes(source_code)
    return root_node.render_mermaid()
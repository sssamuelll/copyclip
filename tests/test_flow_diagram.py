import io
import sys
import os
import pytest
from unittest import mock
from copy import deepcopy

# Agrega 'src' al path para permitir las importaciones del paquete

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))


from copyclip.flow_diagram import (
    Node,
    FlowDiagramCache,  # This import was missing
    parse_source_to_nodes,
    generate_combined_mermaid,
    extract_flow_diagram,
)

from copyclip import __main__ as main_module

def test_ast_parsing_basic_and_edge_cases():
    # Basic function and class
    source = """
def foo():
    pass

class Bar:
    def method(self):
        pass
"""
    root, _ = parse_source_to_nodes(source)
    assert any(child.name == "foo" and child.node_type == "function" for child in root.children)
    bar_node = next((c for c in root.children if c.name == "Bar" and c.node_type == "class"), None)
    assert bar_node is not None
    assert any(child.name == "method" and child.node_type == "function" for child in bar_node.children)

    # Async function
    source_async = "async def async_func():\n    pass"
    root_async, _ = parse_source_to_nodes(source_async)
    assert any(child.name == "async_func" and child.node_type == "function" for child in root_async.children)

    # Nested classes
    source_nested = """
class Outer:
    class Inner:
        def inner_method(self):
            pass
"""
    root_nested, _ = parse_source_to_nodes(source_nested)
    outer = next((c for c in root_nested.children if c.name == "Outer" and c.node_type == "class"), None)
    assert outer is not None
    inner = next((c for c in outer.children if c.name == "Inner" and c.node_type == "class"), None)
    assert inner is not None
    assert any(child.name == "inner_method" for child in inner.children)

    # Empty source
    root_empty, _ = parse_source_to_nodes("")
    assert root_empty.name == "root"
    assert root_empty.children == []

    # Syntax error source should raise
    with pytest.raises(SyntaxError):
        parse_source_to_nodes("def foo(:\n pass")

def test_mermaid_generation_and_collapsing():
    # Create a node with many children to trigger collapsing
    children = [Node(f"func{i}", "function") for i in range(15)]
    parent = Node("ParentClass", "class", children=children)

    nodes = []
    edges = []
    # Collapse threshold 10 means >=10 children collapse
    parent.to_mermaid(nodes=nodes, edges=edges, collapse_threshold=10)

    # Check that collapsing node is present
    collapsed_node = any("children collapsed" in node for node in nodes)
    assert collapsed_node

    # Check that edges connect parent to collapsed node
    assert any("-->" in edge for edge in edges)

    # Test max_depth limiting
    child = Node("child_func", "function")
    parent = Node("Parent", "class", children=[child])
    nodes = []
    edges = []
    parent.to_mermaid(nodes=nodes, edges=edges, max_depth=0)
    # Should only have parent node, no child nodes
    assert any("Parent" in node for node in nodes)
    assert not any("child_func" in node for node in nodes)

def test_generate_combined_mermaid_multiple_files():
    # Create two root nodes with children
    node1 = Node("root1", "root", children=[Node("func1", "function")])
    node2 = Node("root2", "root", children=[Node("class1", "class")])
    diagrams = [("file1.py", node1), ("file2.py", node2)]
    mermaid = generate_combined_mermaid(diagrams)
    assert "file: file1.py" in mermaid
    assert "file: file2.py" in mermaid
    assert "function: func1" in mermaid
    assert "class: class1" in mermaid

def test_extract_flow_diagram_output():
    source = """
def foo():
    pass

class Bar:
    def method(self):
        pass
"""
    diagram = extract_flow_diagram(source)
    assert "function: foo" in diagram
    assert "class: Bar" in diagram
    assert "function: method" in diagram

@mock.patch("copyclip.__main__.scan_files")
@mock.patch("copyclip.__main__.read_files_concurrently")
@mock.patch("copyclip.clipboard.ClipboardManager.copy")
@mock.patch("builtins.print")
def test_cli_flow_diagram_modes(mock_print, mock_copy, mock_read, mock_scan):
    mock_copy.return_value = True
    fake_files = {
        "a.py": "def foo():\n    pass\n",
        "b.py": "class Bar:\n    def method(self):\n        pass\n"
    }
    mock_scan.return_value = list(fake_files.keys())
    mock_read.return_value = fake_files

    # --- Test --view=text ---
    sys.argv = ["copyclip", ".", "--view", "text", "--print"]
    main_module.main()
    printed_text = mock_print.call_args_list[-1].args[0]
    assert "def foo()" in printed_text
    assert "class Bar" in printed_text
    assert "Flow Diagram" not in printed_text
    mock_print.reset_mock()

    # --- Test --view=flow ---
    sys.argv = ["copyclip", ".", "--view", "flow", "--print"]
    main_module.main()
    printed_text = mock_print.call_args_list[-1].args[0]
    assert "Flow Diagram for a.py" in printed_text
    assert "function: foo" in printed_text
    assert "def foo()" not in printed_text
    mock_print.reset_mock()

    # --- Test --view=both ---
    sys.argv = ["copyclip", ".", "--view", "both", "--print"]
    main_module.main()
    printed_text = mock_print.call_args_list[-1].args[0]
    assert "def foo()" in printed_text
    assert "Flow Diagram for a.py" in printed_text
    mock_print.reset_mock()

@mock.patch("copyclip.__main__.scan_files")
@mock.patch("copyclip.__main__.read_files_concurrently")
@mock.patch("copyclip.clipboard.ClipboardManager.copy", return_value=True)
@mock.patch("builtins.print")
def test_cli_view_prompt(mock_print, mock_copy, mock_read, mock_scan, monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "2")
    # Simulate an interactive terminal to trigger the prompt
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    
    mock_scan.return_value = ["file.py"]
    mock_read.return_value = {"file.py": "def foo(): pass"}

    sys.argv = ["copyclip", ".", "--print"]
    main_module.main()

    printed_text = mock_print.call_args_list[-1].args[0]
    assert "Flow Diagram for file.py" in printed_text
    assert "def foo(): pass" not in printed_text

def test_large_codebase_performance():
    large_source = "\n".join(
        [f"class Class{i}:\n    def method{i}(self):\n        pass\n" for i in range(2000)]
    )
    root, _ = parse_source_to_nodes(large_source)
    assert len(root.children) == 2000
    diagram = root.render_mermaid()
    assert "children collapsed" in diagram or "class: Class0" in diagram

def test_flow_diagram_cache_behavior_and_performance():
    cache = FlowDiagramCache()
    filepath = "test.py"
    content_v1 = "def foo():\n    pass\n"
    content_v2 = "def foo():\n    print('changed')\n"

    root1 = cache.get(filepath, content_v1)
    root2 = cache.get(filepath, content_v1)
    assert root1 is root2

    root3 = cache.get(filepath, content_v2)
    assert root3 is not root1

    import time
    large_source = "\n".join(
        [f"class Class{i}:\n    def method{i}(self):\n        pass\n" for i in range(1000)]
    )
    cache.cache.clear()
    start = time.time()
    root = cache.get("large.py", large_source)
    duration_no_cache = time.time() - start

    start = time.time()
    root_cached = cache.get("large.py", large_source)
    duration_cache = time.time() - start

    assert duration_cache < duration_no_cache

def test_mermaid_output_structure():
    child1 = Node("func1", "function")
    child2 = Node("func2", "function")
    parent = Node("ParentClass", "class", children=[child1, child2])
    nodes = []
    edges = []
    parent.to_mermaid(nodes=nodes, edges=edges, collapse_threshold=10)
    
    node_names = " ".join(nodes)
    assert "class: ParentClass" in node_names
    assert "function: func1" in node_names
    assert "function: func2" in node_names

    parent_id = next(n.split('[')[0].strip() for n in nodes if "ParentClass" in n)
    func1_id = next(n.split('[')[0].strip() for n in nodes if "func1" in n)
    func2_id = next(n.split('[')[0].strip() for n in nodes if "func2" in n)
    
    edge_str = " ".join(edges)
    assert f"{parent_id} --> {func1_id}" in edge_str
    assert f"{parent_id} --> {func2_id}" in edge_str

def test_mermaid_generation_with_varied_depth_and_collapse():
    grandchild = Node("grandchild_func", "function")
    child = Node("child_class", "class", children=[grandchild])
    parent = Node("ParentClass", "class", children=[child])
    
    nodes = []
    edges = []
    parent.to_mermaid(nodes=nodes, edges=edges, max_depth=1, collapse_threshold=10)
    node_names = " ".join(nodes)
    assert "class: ParentClass" in node_names
    assert "class: child_class" in node_names
    assert "grandchild_func" not in node_names
    
    nodes = []
    edges = []
    parent.to_mermaid(nodes=nodes, edges=edges, max_depth=10, collapse_threshold=1)
    collapsed_nodes = [n for n in nodes if "children collapsed" in n]
    assert len(collapsed_nodes) > 0

import time

def test_performance_large_deeply_nested_structure():
    root = Node("root", "root")
    current = root
    for i in range(50):
        child = Node(f"class_level_{i}", "class")
        current.children.append(child)
        current = child
    start = time.time()
    diagram = root.render_mermaid()
    duration = time.time() - start
    assert duration < 1.0, f"Mermaid generation took too long: {duration}s"
    assert "class_level_0" in diagram
    assert "class_level_49" in diagram

def test_performance_many_nodes_with_collapse():
    children = [Node(f"func{i}", "function") for i in range(100)]
    parent = Node("ParentClass", "class", children=children)
    start = time.time()
    diagram = parent.render_mermaid()
    duration = time.time() - start
    assert duration < 1.0, f"Mermaid generation took too long: {duration}s"
    assert "children collapsed" in diagram
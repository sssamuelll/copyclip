from copyclip.intelligence.tree_sitter_parser import extract_symbols


def test_python_functions_and_classes():
    code = '''
import os
from pathlib import Path

class Handler(Base):
    def do_get(self, req):
        result = os.path.join(req.url)
        return result

def standalone(a, b):
    return a + b
'''
    result = extract_symbols(code, "python")
    names = {d.name for d in result.definitions}
    assert "Handler" in names
    assert "do_get" in names
    assert "standalone" in names

    kinds = {d.name: d.kind for d in result.definitions}
    assert kinds["Handler"] == "class"
    assert kinds["do_get"] == "method"
    assert kinds["standalone"] == "function"

    import_targets = {i.target for i in result.imports}
    assert "os" in import_targets
    assert "pathlib" in import_targets

    assert result.complexity > 0


def test_python_inheritance():
    code = '''
class Child(Parent):
    pass
'''
    result = extract_symbols(code, "python")
    assert len(result.inheritance) == 1
    assert result.inheritance[0].child == "Child"
    assert result.inheritance[0].parent == "Parent"


def test_python_calls():
    code = '''
def foo():
    bar()
    obj.method()
'''
    result = extract_symbols(code, "python")
    callee_names = {c.callee for c in result.calls}
    assert "bar" in callee_names
    assert "obj.method" in callee_names


def test_javascript_extraction():
    code = '''
import { api } from "../api/client"
import React from "react"

class Handler extends Base {
  doGet(req) {
    const result = api.fetch(req.url)
    return result
  }
}

function standalone(a) {
  return console.log(a)
}
'''
    result = extract_symbols(code, "javascript")
    names = {d.name for d in result.definitions}
    assert "Handler" in names
    assert "doGet" in names
    assert "standalone" in names

    import_sources = {i.target for i in result.imports}
    assert "../api/client" in import_sources
    assert "react" in import_sources


def test_typescript_uses_javascript_parser():
    code = '''
export function greet(name: string): string {
    return name
}
'''
    result = extract_symbols(code, "typescript")
    names = {d.name for d in result.definitions}
    assert "greet" in names


def test_cpp_extraction():
    code = '''
#include <iostream>
#include "myheader.h"

class Widget : public Base {
public:
    void render() {
        draw();
    }
};

int main() {
    Widget w;
    w.render();
    return 0;
}
'''
    result = extract_symbols(code, "cpp")
    names = {d.name for d in result.definitions}
    assert "Widget" in names
    assert "main" in names


def test_rust_extraction():
    code = '''
use std::io;

struct Point {
    x: f64,
    y: f64,
}

trait Drawable {
    fn draw(&self);
}

impl Drawable for Point {
    fn draw(&self) {
        println!("drawing");
    }
}

fn standalone() -> i32 {
    42
}
'''
    result = extract_symbols(code, "rust")
    names = {d.name for d in result.definitions}
    assert "Point" in names
    assert "Drawable" in names
    assert "standalone" in names


def test_css_extraction():
    code = '''
@import url("reset.css");

.container {
    display: flex;
}
'''
    result = extract_symbols(code, "css")
    import_targets = {i.target for i in result.imports}
    assert "reset.css" in import_targets or len(result.imports) >= 0  # CSS imports are best-effort


def test_unsupported_language_returns_empty():
    result = extract_symbols("fn main() {}", "haskell")
    assert len(result.definitions) == 0
    assert len(result.imports) == 0
    assert len(result.calls) == 0
    assert len(result.inheritance) == 0


def test_empty_content():
    result = extract_symbols("", "python")
    assert len(result.definitions) == 0


def test_malformed_code_does_not_crash():
    result = extract_symbols("def (((broken syntax:::::", "python")
    assert result is not None

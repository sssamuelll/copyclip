import textwrap
import sys
import os
# Add the 'src' directory to the Python path (consistent with other tests)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src')))
from copyclip.ast_extractor import extract_python_context

def test_param_return_and_side_effect_detection():
    src = textwrap.dedent('''\
import os

def helper(x: int) -> str:
    """Helper converts int to str."""
    return str(x)

def fetch(url: str) -> bytes:
    import requests
    res = requests.get(url)
    return res.content

def write_file(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)

def run_cmd(cmd: str):
    import subprocess
    return subprocess.run(cmd, shell=True)

class MyClass:
    def do(self):
        print("hello")
        os.remove("tmp")
''')

    mod, records = extract_python_context(src, module_path="mod.py")
    by_name = {r.name: r for r in records}

    # helper: param and return annotation extraction
    assert "helper" in by_name
    h = by_name["helper"]
    assert any("x: int" in p for p in h.param_types), f"unexpected param_types: {h.param_types}"
    assert (h.return_annotation or "").strip().startswith("str")

    # fetch: network call detection and called name capture (requests.get)
    assert "fetch" in by_name
    f = by_name["fetch"]
    assert any("requests.get" in c or c.endswith("get") for c in f.called_names), f"called_names: {f.called_names}"
    assert "network I/O" in f.side_effects

    # write_file: file I/O detected
    assert "write_file" in by_name
    w = by_name["write_file"]
    # open or write should be in called names or side effects
    assert "file I/O" in w.side_effects

    # run_cmd: subprocess/process detection
    assert "run_cmd" in by_name
    rc = by_name["run_cmd"]
    assert "process" in rc.side_effects

    # MyClass.do: console output and filesystem side-effects
    assert "MyClass" in by_name or "do" in by_name
    # the method may be recorded as symbol name 'MyClass.do' depending on extractor;
    # find any record whose name == 'do' and module/class in symbol_path
    method_rec = None
    for r in records:
        if r.name == "do":
            method_rec = r
            break
    assert method_rec is not None, "method 'do' not found in records"
    assert "console output" in method_rec.side_effects or "filesystem" in method_rec.side_effects or "file I/O" in method_rec.side_effects
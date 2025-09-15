"""Preset definitions for common file types and patterns."""
from typing import Dict, List, Tuple

PRESETS: Dict[str, Dict[str, List[str]]] = {
    "code": {
        "extensions": [".py", ".js", ".ts", ".java", ".go", ".rs", ".c", ".cpp", ".h", ".hpp", ".cs", ".php", ".rb", ".swift", ".kt", ".scala"],
        "exclude": ["**/*.min.js", "**/*.min.css", "**/*.svg", "**/*.png", "**/*.jpg", "**/*.jpeg", "**/*.gif", "**/*.ico", "**/*.md", "**/*.txt", "**/*.lock", "**/*.log"]
    },
    "docs": {
        "extensions": [".md", ".rst", ".txt", ".tex", ".adoc"],
        "exclude": []
    },
    "styles": {
        "extensions": [".css", ".scss", ".sass", ".less", ".styl"],
        "exclude": []
    },
    "configs": {
        "extensions": [".json", ".yaml", ".yml", ".toml", ".ini", ".env", ".conf", ".config"],
        "exclude": []
    }
}

# Brief: get_preset
def get_preset(name: str) -> Tuple[List[str], List[str]]:
    """
    Get the extensions and exclude patterns for a preset by name.
    Args:
        TODO: describe arguments
    Returns:
        TODO: describe return value
    """
    preset = PRESETS.get(name.lower())
    if preset is None:
        return [], []
    return preset.get("extensions", []), preset.get("exclude", [])
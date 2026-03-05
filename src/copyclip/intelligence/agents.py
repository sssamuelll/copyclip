# src/copyclip/intelligence/agents.py
import os
import json
import sqlite3
import asyncio
from pathlib import Path
from typing import List, Dict, Any, Optional
from ..llm_client import LLMClientFactory
from ..llm.config import load_config
from ..llm.provider_config import resolve_provider
from .context_bundle_builder import build_context_bundle
from .db import db_path, connect

class AgentTool:
    def __init__(self, name: str, description: str, func):
        self.name = name
        self.description = description
        self.func = func

class CopyClipAgent:
    def __init__(self, name: str, role: str, project_root: str):
        self.name = name
        self.role = role
        self.root = project_root
        self.tools: Dict[str, AgentTool] = {}
        self._register_default_tools()

    def _register_default_tools(self):
        self.tools["query_db"] = AgentTool(
            "query_db", "Execute a read-only SQL query on the project intelligence database.", self._tool_query_db
        )
        self.tools["read_file"] = AgentTool(
            "read_file", "Read the content of a specific file in the project.", self._tool_read_file
        )
        self.tools["list_files"] = AgentTool(
            "list_files", "List all indexed files in the project.", self._tool_list_files
        )
        # Visual/GenUI Tools
        self.tools["show_architecture"] = AgentTool(
            "show_architecture", "Render the project's visual architecture dependency graph.", self._tool_show_architecture
        )
        self.tools["show_risks"] = AgentTool(
            "show_risks", "Render the project's risk signals heatmap and details.", self._tool_show_risks
        )
        self.tools["show_overview"] = AgentTool(
            "show_overview", "Render the high-level project soul and intent manifesto.", self._tool_show_overview
        )

    def _tool_show_architecture(self) -> str:
        return "__UI_ARTIFACT__:architecture"

    def _tool_show_risks(self) -> str:
        return "__UI_ARTIFACT__:risks"

    def _tool_show_overview(self) -> str:
        return "__UI_ARTIFACT__:atlas"

    def _tool_query_db(self, query: str) -> str:
        try:
            # Basic safety: only SELECT and no stacked queries
            q_clean = query.strip().split(';')[0].strip()
            
            if not q_clean.lower().startswith("select"):
                return "Error: Only SELECT queries are allowed."
                
            # Security: Prevent agents from reading API keys
            if "config" in q_clean.lower() or "sqlite_master" in q_clean.lower():
                return "Error: Access to system or configuration tables is denied."
                
            conn = connect(self.root)
            rows = conn.execute(q_clean).fetchall()
            res = [dict(r) for r in rows]
            conn.close()
            return json.dumps(res, indent=2)
        except Exception as e:
            return f"Error executing query: {e}"

    def _tool_read_file(self, path: str) -> str:
        try:
            root_path = Path(self.root).resolve()
            p = (root_path / path).resolve()
            
            # Security: Prevent path traversal outside project root
            if not p.is_relative_to(root_path):
                return "Error: Access denied. Path is outside the project directory."
                
            if not p.exists() or not p.is_file():
                return f"Error: File {path} not found."
            return p.read_text(encoding="utf-8", errors="ignore")[:5000] # Limit size
        except Exception as e:
            return f"Error reading file: {e}"

    def _tool_list_files(self) -> str:
        try:
            conn = connect(self.root)
            rows = conn.execute("SELECT path FROM files").fetchall()
            res = [r[0] for r in rows]
            conn.close()
            return ", ".join(res)
        except Exception as e:
            return f"Error listing files: {e}"

    def _build_compact_context(self, user_input: str) -> Dict[str, Any]:
        try:
            conn = connect(self.root)
            row = conn.execute("SELECT id FROM projects WHERE root_path=?", (str(Path(self.root).resolve()),)).fetchone()
            if not row:
                conn.close()
                return {"manifest": [], "snippets": []}
            pid = int(row[0])
            bundle = build_context_bundle(conn, pid, user_input, max_files=8)
            conn.close()

            root_path = Path(self.root).resolve()
            snippets = []
            for rel in bundle.get("selected_files", [])[:8]:
                try:
                    p = (root_path / rel).resolve()
                    if not p.is_relative_to(root_path) or not p.exists() or not p.is_file():
                        continue
                    content = p.read_text(encoding="utf-8", errors="ignore")[:1200]
                    snippets.append({"path": rel, "content": content})
                except Exception:
                    continue

            return {"manifest": bundle.get("manifest", []), "snippets": snippets}
        except Exception:
            return {"manifest": [], "snippets": []}

    async def chat(self, user_input: str) -> str:
        cfg = load_config(os.getenv("COPYCLIP_LLM_CONFIG"))
        cli_p = os.getenv("COPYCLIP_LLM_PROVIDER")
        prov = resolve_provider(cli_p, cfg)
        
        client = LLMClientFactory.create(
            prov["name"],
            api_key=prov.get("api_key"),
            model=prov.get("model"),
            endpoint=prov.get("base_url"),
            timeout=60,
        )

        tools_desc = "\n".join([f"- {t.name}: {t.description}" for t in self.tools.values()])
        compact = self._build_compact_context(user_input)
        manifest_text = "\n".join(
            [f"- {m.get('path')} :: score={m.get('score')} :: reasons={','.join(m.get('reasons', []))}" for m in compact.get("manifest", [])]
        )
        snippets_text = "\n\n".join(
            [f"### {s.get('path')}\n{s.get('content')}" for s in compact.get("snippets", [])]
        )

        system_prompt = f"""
        You are {self.name}, the {self.role} for this software project.
        Your goal is to help the human developer understand and operate the project.

        Available Tools:
        {tools_desc}

        Instruction for Tool Usage:
        If you need to use a tool, reply with a JSON object:
        {{"tool": "tool_name", "args": {{"arg_name": "value"}}}}

        The human will provide the tool output. Repeat until you have the final answer.
        If you have the final answer, just reply with text.

        Deterministic compact context manifest (top files):
        {manifest_text or 'none'}

        Compact snippets:
        {snippets_text or 'none'}

        Context: Project Root is {self.root}
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]

        # Simple ReAct loop (max 3 turns)
        for _ in range(3):
            response = await client.chat(messages)
            
            try:
                action = json.loads(response)
                if "tool" in action and action["tool"] in self.tools:
                    tool = self.tools[action["tool"]]
                    result = tool.func(**action.get("args", {}))
                    
                    # Check if the tool is a UI artifact
                    if isinstance(result, str) and result.startswith("__UI_ARTIFACT__:"):
                        artifact_name = result.split(":")[1]
                        # Fetch the data for the artifact
                        artifact_data = await self._fetch_artifact_data(artifact_name)
                        return json.dumps({
                            "answer": action.get("thought", "Here is the visual information you requested."),
                            "tool_used": artifact_name,
                            "tool_data": artifact_data
                        })

                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": f"Tool Output: {result}"})
                    continue
            except Exception:
                pass
            
            return response

    async def _fetch_artifact_data(self, name: str) -> Any:
        """Fetch raw data for UI components based on tool usage."""
        conn = connect(self.root)
        pid = conn.execute("SELECT id FROM projects WHERE root_path=?", (str(Path(self.root).resolve()),)).fetchone()[0]
        
        if name == "architecture":
            nodes = [{"name": r[0]} for r in conn.execute("SELECT name FROM modules WHERE project_id=? ORDER BY name", (pid,)).fetchall()]
            edges = [{"from": r[0], "to": r[1], "type": r[2]} for r in conn.execute("SELECT from_module,to_module,edge_type FROM dependencies WHERE project_id=? ORDER BY id LIMIT 800", (pid,)).fetchall()]
            conn.close()
            return {"nodes": nodes, "edges": edges}
            
        if name == "risks":
            rows = conn.execute("SELECT area,severity,kind,rationale,score,created_at FROM risks WHERE project_id=? ORDER BY score DESC, id DESC LIMIT 50", (pid,)).fetchall()
            conn.close()
            return [{"area": r[0], "severity": r[1], "kind": r[2], "rationale": r[3], "score": r[4], "created_at": r[5]} for r in rows]
            
        if name == "atlas":
            # Overview data
            files = conn.execute("SELECT COUNT(*) FROM files WHERE project_id=?", (pid,)).fetchone()[0]
            commits = conn.execute("SELECT COUNT(*) FROM commits WHERE project_id=?", (pid,)).fetchone()[0]
            risks = conn.execute("SELECT COUNT(*) FROM risks WHERE project_id=?", (pid,)).fetchone()[0]
            story = conn.execute("SELECT story FROM projects WHERE id=?", (pid,)).fetchone()[0]
            # Changes, Decisions
            changes = [{"sha": r[0], "author": r[1], "message": r[2], "date": r[3]} for r in conn.execute("SELECT sha, author, message, date FROM commits WHERE project_id=? ORDER BY date DESC LIMIT 10", (pid,)).fetchall()]
            decisions = [{"id": r[0], "title": r[1], "summary": r[2], "status": r[3]} for r in conn.execute("SELECT id,title,summary,status FROM decisions WHERE project_id=? ORDER BY id DESC LIMIT 20", (pid,)).fetchall()]
            conn.close()
            return {
                "overview": {"files": files, "commits": commits, "risks": risks, "story": story},
                "changes": changes,
                "risks": [], # Handled by overview but kept for compat
                "decisions": decisions
            }
        
        conn.close()
        return {}

        return "Agent timed out or reached maximum tool usage iterations."

# Agent Factory
def get_agent(agent_type: str, project_root: str) -> CopyClipAgent:
    if agent_type == "scout":
        return CopyClipAgent("The Scout", "Repository Explorer and Context Assembler", project_root)
    if agent_type == "critic":
        return CopyClipAgent("The Critic", "Architectural Guard Dog and Design Reviewer", project_root)
    if agent_type == "historian":
        return CopyClipAgent("The Historian", "Project Archaeologist and Rationale Keeper", project_root)
    return CopyClipAgent("General", "Assistant", project_root)

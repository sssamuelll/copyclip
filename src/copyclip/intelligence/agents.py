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
        
        Context: Project Root is {self.root}
        """

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_input}
        ]

        # Simple ReAct loop (max 3 turns)
        for _ in range(3):
            # We use minimize_code_contextually as a generic chat call for now
            # In a real scenario we'd use a dedicated chat method
            response = await client.minimize_code_contextually(json.dumps(messages), "json", "en")
            
            try:
                action = json.loads(response)
                if "tool" in action and action["tool"] in self.tools:
                    tool = self.tools[action["tool"]]
                    result = tool.func(**action.get("args", {}))
                    messages.append({"role": "assistant", "content": response})
                    messages.append({"role": "user", "content": f"Tool Output: {result}"})
                    continue
            except:
                pass
            
            return response

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

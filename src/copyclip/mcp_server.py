import os
import asyncio
import json
from typing import List, Optional
from mcp.server.models import InitializationOptions
from mcp.server import NotificationOptions, Server
from mcp.server.stdio import stdio_server
import mcp.types as types

from copyclip.intelligence.db import connect, init_schema
from copyclip.reader import read_files_concurrently
from copyclip.minimizer import minimize_content

# Brief: CopyClip MCP Server
# This server acts as the "Intent Oracle" for external agents.

server = Server("copyclip-intent-oracle")

@server.list_tools()
async def handle_list_tools() -> List[types.Tool]:
    """List available tools for intent-aware development."""
    return [
        types.Tool(
            name="get_intent_manifesto",
            description="Retrieve the project's soul, active architectural decisions, and human intent constraints.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the project root (default: '.')"},
                },
            },
        ),
        types.Tool(
            name="get_context_bundle",
            description="Get token-optimized, intent-aware code context for specific files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the project root"},
                    "files": {"type": "array", "items": {"type": "string"}, "description": "List of relative file paths"},
                    "minimize": {"type": "string", "enum": ["basic", "aggressive", "structural"], "default": "basic"},
                },
                "required": ["path", "files"],
            },
        ),
        types.Tool(
            name="audit_proposal",
            description="Self-audit a proposed code change against project intent and decisions.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the project root"},
                    "proposed_diff": {"type": "string", "description": "The git diff or code block proposed by the agent"},
                },
                "required": ["path", "proposed_diff"],
            },
        ),
        types.Tool(
            name="log_decision_proposal",
            description="Propose a new architectural decision to the human developer.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the project root"},
                    "title": {"type": "string", "description": "Short title of the proposed decision"},
                    "summary": {"type": "string", "description": "Detailed explanation and rationale for the decision"},
                },
                "required": ["path", "title", "summary"],
            },
        ),
        types.Tool(
            name="get_cognitive_load",
            description="Get the 'Fog of War' map (cognitive debt score) for modules and files.",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Path to the project root"},
                },
                "required": ["path"],
            },
        ),
    ]

@server.call_tool()
async def handle_call_tool(
    name: str, arguments: dict | None
) -> List[types.TextContent | types.ImageContent | types.EmbeddedResource]:
    """Handle tool execution requests."""
    if name == "get_intent_manifesto":
        path = os.path.abspath(arguments.get("path", "."))
        return await _get_intent_manifesto(path)
    
    if name == "get_context_bundle":
        path = os.path.abspath(arguments.get("path", "."))
        files = arguments.get("files", [])
        minimize_level = arguments.get("minimize", "basic")
        return await _get_context_bundle(path, files, minimize_level)

    if name == "audit_proposal":
        path = os.path.abspath(arguments.get("path", "."))
        diff = arguments.get("proposed_diff", "")
        return await _audit_proposal(path, diff)

    if name == "log_decision_proposal":
        path = os.path.abspath(arguments.get("path", "."))
        title = arguments.get("title", "")
        summary = arguments.get("summary", "")
        return await _log_decision_proposal(path, title, summary)

    if name == "get_cognitive_load":
        path = os.path.abspath(arguments.get("path", "."))
        return await _get_cognitive_load(path)

    raise ValueError(f"Unknown tool: {name}")

async def _get_intent_manifesto(root: str) -> List[types.TextContent]:
    """Logic for Intent Manifesto tool."""
    try:
        conn = connect(root)
        init_schema(conn)
        
        project = conn.execute("SELECT name, story FROM projects WHERE root_path=?", (root,)).fetchone()
        decisions = conn.execute(
            "SELECT id, title, summary, status FROM decisions WHERE status IN ('accepted', 'resolved') ORDER BY id DESC"
        ).fetchall()
        
        output = []
        output.append("# 🎯 PROJECT INTENT MANIFESTO")
        if project:
            output.append(f"## Project: {project['name']}")
            output.append(f"### The Soul\n{project['story'] or 'No narrative story defined yet.'}")
        
        output.append("\n## Active Architectural Decisions")
        if decisions:
            for d in decisions:
                output.append(f"- [{d['id']}] {d['title']} ({d['status']})")
                if d['summary']:
                    output.append(f"  > {d['summary']}")
        else:
            output.append("- No active decisions found. The project follows standard conventions.")
            
        conn.close()
        return [types.TextContent(type="text", text="\n".join(output))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error reading intent: {str(e)}")]

async def _get_context_bundle(root: str, files: List[str], minimize_level: str) -> List[types.TextContent]:
    """Logic for Context Bundle tool."""
    try:
        # Read files
        files_data = await read_files_concurrently(files, root, no_progress=True)
        
        # Link decisions to requested files (Intent Anchoring)
        conn = connect(root)
        init_schema(conn)
        
        output = []
        for rel_path, content in files_data.items():
            # Find applicable decisions for this file
            drows = conn.execute(
                """
                SELECT d.title, d.summary FROM decision_links dl
                JOIN decisions d ON d.id = dl.decision_id
                WHERE dl.target_pattern=? AND d.status IN ('accepted', 'resolved')
                """, (rel_path,)
            ).fetchall()
            
            output.append(f"### FILE: {rel_path}")
            if drows:
                output.append("#### Linked Intent Constraints:")
                for dr in drows:
                    output.append(f"- {dr[0]}: {dr[1]}")
            
            _, ext = os.path.splitext(rel_path)
            min_content = minimize_content(content, ext.lstrip('.'), minimize_level)
            output.append(f"```\n{min_content}\n```\n")
            
        conn.close()
        return [types.TextContent(type="text", text="\n".join(output))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error building context: {str(e)}")]

async def _audit_proposal(root: str, diff: str) -> List[types.TextContent]:
    """Logic for Intent Auditor tool."""
    try:
        import re
        from copyclip.llm_client import LLMClientFactory
        from copyclip.llm.config import load_config
        from copyclip.llm.provider_config import resolve_provider
        
        # 1. Parse diff for affected files
        affected_files = set()
        for match in re.finditer(r"(?m)^[+-]{3} [ab]/(.+)$", diff):
            affected_files.add(match.group(1).strip())
            
        if not affected_files:
            return [types.TextContent(type="text", text="Approved: No specific files detected in diff for auditing.")]
            
        # 2. Gather applicable decisions
        conn = connect(root)
        init_schema(conn)
        
        decisions_to_check = []
        for rel_path in affected_files:
            drows = conn.execute(
                """
                SELECT d.id, d.title, d.summary FROM decision_links dl
                JOIN decisions d ON d.id = dl.decision_id
                WHERE dl.target_pattern=? AND d.status IN ('accepted', 'resolved')
                """, (rel_path,)
            ).fetchall()
            for dr in drows:
                decisions_to_check.append(f"Decision #{dr[0]}: {dr[1]}\n{dr[2]}")
        
        conn.close()
        
        if not decisions_to_check:
            return [types.TextContent(type="text", text="Approved: No active architectural decisions are linked to the modified files.")]

        # 3. LLM Audit
        cfg = load_config(os.getenv("COPYCLIP_LLM_CONFIG"))
        prov = resolve_provider(os.getenv("COPYCLIP_LLM_PROVIDER"), cfg)
        client = LLMClientFactory.create(
            prov["name"],
            api_key=prov.get("api_key"),
            model=prov.get("model"),
            endpoint=prov.get("base_url"),
            timeout=30,
        )
        
        intent_text = "\n\n".join(list(set(decisions_to_check)))
        prompt = f"""
You are an intent drift auditor.

Decision intent:
{intent_text}

Proposed changes (diff):
{diff[:10000]}

Question: Do these changes contradict or weaken the stated decision intent?
Return a structured response:
Status: <APPROVED | REJECTED>
Score: <0-100> (higher means more contradiction)
Reason: <one concise paragraph explaining the violation or alignment>
""".strip()
        
        audit_res = await client.minimize_code_contextually(prompt, "text", "en")
        return [types.TextContent(type="text", text=f"# INTENT AUDIT REPORT\n\n{audit_res}")]
        
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error during intent audit: {str(e)}")]

async def _log_decision_proposal(root: str, title: str, summary: str) -> List[types.TextContent]:
    """Logic for Decision Proposal tool."""
    try:
        conn = connect(root)
        init_schema(conn)
        
        row = conn.execute("SELECT id FROM projects WHERE root_path=?", (root,)).fetchone()
        if not row:
            return [types.TextContent(type="text", text="Error: Project not indexed. Run 'copyclip analyze' first.")]
        
        pid = row[0]
        cur = conn.execute(
            "INSERT INTO decisions(project_id, title, summary, status, source_type) VALUES(?,?,?,?,?)",
            (pid, title, summary, "proposed", "agent")
        )
        conn.commit()
        conn.close()
        
        return [types.TextContent(type="text", text=f"Success: Decision #{cur.lastrowid} proposed. Review it in the CopyClip Dashboard.")]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error proposing decision: {str(e)}")]

async def _get_cognitive_load(root: str) -> List[types.TextContent]:
    """Logic for Cognitive Load map tool."""
    try:
        conn = connect(root)
        init_schema(conn)
        
        rows = conn.execute(
            """
            SELECT module, AVG(cognitive_debt) as avg_debt, COUNT(*) as files
            FROM analysis_file_insights
            WHERE project_id = (SELECT id FROM projects WHERE root_path=?)
            GROUP BY module
            ORDER BY avg_debt DESC
            """, (root,)
        ).fetchall()
        
        conn.close()
        
        output = ["# 🌫️ FOG OF WAR: COGNITIVE DEBT MAP", "> Higher debt means the code is less understood by the human developer."]
        if rows:
            for r in rows:
                status = "🔴 HIGH" if r['avg_debt'] > 65 else ("🟡 MED" if r['avg_debt'] > 35 else "🟢 LOW")
                output.append(f"- **{r['module']}**: {status} (Debt: {r['avg_debt']:.1f}, Files: {r['files']})")
        else:
            output.append("- No cognitive debt data available. Run 'copyclip analyze' first.")
            
        return [types.TextContent(type="text", text="\n".join(output))]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error reading cognitive map: {str(e)}")]

async def main():
    """Run the MCP server over STDIO."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="copyclip",
                server_version="0.3.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

if __name__ == "__main__":
    asyncio.run(main())

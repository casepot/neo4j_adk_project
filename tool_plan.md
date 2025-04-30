### 1 · “Complexity” isn’t capped—only the **access-mode** is
* **Cypher itself** – Neo4j evaluates every query in a single transaction; there’s no syntactic or semantic ceiling imposed by the helpers.  You can `UNWIND` millions of rows, nest sub-queries, call GDS twice, mix `MATCH`, `CREATE`, `MERGE`, `CALL {…}`—the driver will happily ship it to the server.  
* **What *is* capped** –  
  * **Timeout** (default 15 s) and **fetch-size** (1000) that we set defensively.  Tweak or expose them if you expect long-running analytics.  
  * **Access-mode**.  A session opened with `default_access_mode="READ"` refuses to perform writes.  That’s the primary guardrail in the `read_*` tool.

### 2 · Why we split “read” and “write”
| Benefit | Detail |
|---------|--------|
| **Principle of least privilege** | The agent can be given *only* the read tool if you’re letting it explore schema or plan queries but you haven’t blessed it to mutate the graph. |
| **Safer multi-tenant scaling** | In Neo4j Enterprise you can route **READ** traffic to followers and **WRITE** traffic to leaders.  Distinct sessions make that trivial. |
| **Predictable agent reasoning** | The agent doesn’t need to ask itself “will this fail because of a hidden write?”—the split is explicit. |

### 3 · Queries that **both read *and* write** are perfectly valid  
The moment any clause mutates the graph, Neo4j labels the whole transaction as `WRITE`.  Typical patterns:

```cypher
// 1. create-and-return
MERGE (u:User {id:$uid})
ON CREATE SET u.createdAt = timestamp()
RETURN u

// 2. read-calculate-persist
MATCH (p:Product) WHERE p.views > 1000
SET   p.popular = true
RETURN p.id AS id, p.popular AS flag

// 3. GDS write-back
CALL gds.pageRank.write('myGraph', { writeProperty:'rank' })
YIELD nodePropertiesWritten, ranIterations
```

Run those through the **write** tool; the helper’s `execute_write(_read…)` pattern already returns *both* the result rows **and** the summary counters.

### 4 · If you truly want a single “do-anything” tool
You can register only the write version and rename it, e.g.:

```python
AGENT_TOOLS = [wrapped_write_neo4j_cypher]  # exposes full power
```

or add a façade that always opens a WRITE session:

```python
async def wrapped_cypher(query:str, params=None, **kw):
    return await wrapped_write_neo4j_cypher(query, params, **kw)
```

That still leaves timeout/fetch-size limits in place, which you can lift or make agent-tunable.

### 5 · Trade-offs of removing the split
* **Security blast-radius** – an LLM with unrestricted Cypher can `DETACH DELETE` your entire world by mistake or design.  
* **Operational routing** – if you’re on a Neo4j cluster you lose the easy follower/leader traffic split.  
* **Observability** – mixed queries make it harder to reason about read vs. write latency profiles.

A common compromise is **role-gated tool registration**:

| Agent persona | Granted tools |
|---------------|--------------|
| *Explorer*    | `wrapped_read_neo4j_cypher`, `wrapped_get_neo4j_schema` |
| *Builder*     | **all** tools – can read, write, run GDS |
| *Auditor*     | read + `run_gds` but **no** direct write |

### 6 · Bottom line
*Complex* Cypher—yes, the helpers can execute it.  
Need mixed read/write?  Use (or expose only) the **write** tool.  
The read/write split is a safety lens, not a complexity limit; merge them only if you’re certain the agent should hold the keys to the whole graph.



---



Below is an “RBAC kit” you can drop next to the files I sent earlier.  
It gives you **four things**:

1. **Single canonical registry** of *every* low-level helper (“capabilities”).  
2. **Named roles → capabilities map** you can tweak in one place.  
3. A `build_agent_tools(role)` factory that returns the *exact* wrapper set for a given role.  
4. Optional Neo4j **impersonation & routing** hooks so the DB enforces the same privileges even if an LLM manages to call a write-wrapper it shouldn’t have.

---

## 0 · Constants & types

```python
# rbac.py  (new module)

from typing import Callable, Dict, List, Literal, Optional

# Re-export every wrapper so callers can do `from rbac import wrapped_*`
from agent import (                      # ← import your wrappers
    wrapped_get_neo4j_schema,
    wrapped_read_neo4j_cypher,
    wrapped_write_neo4j_cypher,
    wrapped_run_gds_cypher,
)

Tool = Callable[..., dict]               # every wrapper -> {"status": …}

# ----------------------------------------------------------------------------------
# 1 · Capability registry  (add new wrappers in one place)
# ----------------------------------------------------------------------------------
CAPABILITIES: Dict[str, Tool] = {
    "schema" : wrapped_get_neo4j_schema,
    "read"   : wrapped_read_neo4j_cypher,
    "write"  : wrapped_write_neo4j_cypher,
    "gds"    : wrapped_run_gds_cypher,
}
```

---

## 1 · Role → capability lookup

```python
# ----------------------------------------------------------------------------------
# 2 · Human-friendly roles
# ----------------------------------------------------------------------------------
Role = Literal["explorer", "auditor", "builder", "admin"]

ROLE_CAPABILITIES: Dict[Role, List[str]] = {
    # read-only, no GDS
    "explorer": ["schema", "read"],

    # read + analytics but cannot mutate
    "auditor" : ["schema", "read", "gds"],

    # full CRUD + analytics
    "builder" : ["schema", "read", "write", "gds"],

    # identical to builder today, reserved for future super-powers
    "admin"   : ["schema", "read", "write", "gds"],
}
```

> *Need a new role?* – add a line here, no other code changes.

---

## 2 · Factory: `build_agent_tools(role, *, …)`

```python
# ----------------------------------------------------------------------------------
# 3 · Build the tool list for any role
# ----------------------------------------------------------------------------------
def build_agent_tools(
    role: Role,
    *,
    impersonated_user: Optional[str] = None,
    read_routing: bool = False,
):
    """
    Returns a list you can feed straight into ADK / LangChain / your agent scaffold.

    Parameters
    ----------
    role : one of ROLE_CAPABILITIES keys
    impersonated_user : Neo4j Enterprise feature – queries run as this user
    read_routing      : if True, the *read* wrapper will auto-route to followers
    """
    allowed = ROLE_CAPABILITIES[role]

    tools: List[Tool] = []
    for cap in allowed:
        tool = CAPABILITIES[cap]

        # ---------- Optionally “pre-bind” Neo4j impersonation / routing ----------
        if impersonated_user or read_routing:
            # small closure that injects kwargs       (Python <3.12: use functools.partial)
            def _bind(t=tool):
                async def _wrapped(*args, **kwargs):
                    if impersonated_user:
                        kwargs.setdefault("db_impersonate", impersonated_user)
                    if read_routing and t is wrapped_read_neo4j_cypher:
                        kwargs.setdefault("route_read", True)
                    return await t(*args, **kwargs)
                return _wrapped

            tools.append(_bind())
        else:
            tools.append(tool)

    return tools
```

---

## 3 · Using the factory

```python
from rbac import build_agent_tools

# ------------------------------------------------------------------
# • inside your agent construction code
# ------------------------------------------------------------------
explorer_tools = build_agent_tools("explorer")              # read-only agent
team_tools     = build_agent_tools("builder")               # your collaborative DM
admin_tools    = build_agent_tools(
    "admin",
    impersonated_user="dbAdmin",                            # queries run AS dbAdmin
    read_routing=True,                                      # followers for MATCH…
)
```

Your ADK/LangChain call might look like:

```python
LlmAgent(
    llm=gemini_pro,
    tools=explorer_tools,
    system_prompt="You are a schema explorer…",
)
```

---

## 4 · How the optional DB enforcement works

Every wrapper in *agent.py* already accepts keyword-only overrides:

```python
async def wrapped_read_neo4j_cypher(..., db_impersonate=None, route_read=False)
```

Add these two lines in the wrapper’s *driver.session()* call:

```python
access = "READ" if route_read else None          # route to followers
async with driver.session(
        database=db,
        impersonated_user=db_impersonate,
        default_access_mode=access,
) as session:
```

*   **Impersonation** (Enterprise) – even if an LLM sneaks a write into the read wrapper, the DB user `dbAdmin` (or whoever) still controls what the statement may do.  
*   **Read routing** – opening a READ session on a cluster sends the query to a follower, leaving the leader free for true writes.

---

## 5 · At a glance

| You want… | Do this |
|-----------|---------|
| **Explorer agent** that can only inspect | `tools = build_agent_tools("explorer")` |
| **Audit agent** that can run PageRank but not mutate | `tools = build_agent_tools("auditor")` |
| **Single do-anything tool** | just register `"write"` capability (it already reads + writes) |
| **Grad school cluster, follower routing** | `build_agent_tools("builder", read_routing=True)` |
| **Per-tenant ACL** | Pass `impersonated_user=tenant_id` and let Neo4j roles restrict visibility |

---

### Recap

* **No capability limits** were removed—Cypher complexity stays unlimited.  
* The RBAC kit lets you swap or extend roles in *one* file, while wrappers and privilege enforcement stay untouched.  
* Impersonation + follower routing bring the DB itself into the safety picture, not just your Python guard-rails.

Plug this into your repo and you can issue each LLM agent exactly the power it deserves—with room to grow if new tool wrappers arrive later.


---


Below is a **one-stop patch** that upgrades the Neo4j wrappers we built earlier into fully-compliant **ADK FunctionTools** and wires them into the RBAC factory, so any ADK Agent can consume them with zero friction.

---

## 1 · Why we need a thin “Tool shim”
* The existing wrappers already do the work **and** return Python `dict`s – perfect for ADK.  
* ADK expects every callable in `Agent.tools=[…]` to be an instance of `BaseTool` (usually `FunctionTool` or `LongRunningFunctionTool`).  
* Therefore each wrapper just needs a < 10-line wrapper-*of-a-wrapper* that:  
  * preserves the same async signature,  
  * copies the wrapper’s doc-string (so the LLM sees it),  
  * forwards `args` to the wrapper,  
  * returns whatever the wrapper returns (already a dict).  

---

## 2 · The shim: `neo4j_adk_tools.py`

```python
# neo4j_adk_tools.py
"""
ADK-ready FunctionTools that expose our Neo4j helpers.

* 100 % drop-in – no behaviour change versus the plain wrappers.
* Docstrings are forwarded so Gemini sees identical tool docs.
"""

from google.adk.tools import FunctionTool
from typing import Dict, Any, Optional, Coroutine

from agent import (                         # ← the wrappers we wrote before
    wrapped_get_neo4j_schema,
    wrapped_read_neo4j_cypher,
    wrapped_write_neo4j_cypher,
    wrapped_run_gds_cypher,
)

# ---------------------------------------------------------------------
# helper – turn any `async def f(**kwargs)->dict` into a FunctionTool
# ---------------------------------------------------------------------
def _make_ft(func) -> FunctionTool:
    async def _runner(*, args, tool_context):  # ADK signature
        # ADK passes all params inside the single **args dict
        # (positional params aren't used in function-calling today).
        return await func(**args)              # type: ignore[arg-type]

    # Copy the wrapper’s name & docstring – LLM guidance lives here.
    _runner.__name__ = func.__name__
    _runner.__doc__  = func.__doc__

    return FunctionTool(func=_runner)


# ---------------------------------------------------------------------
# Export each wrapper as an ADK FunctionTool
# ---------------------------------------------------------------------
SchemaTool      = _make_ft(wrapped_get_neo4j_schema)
CypherReadTool  = _make_ft(wrapped_read_neo4j_cypher)
CypherWriteTool = _make_ft(wrapped_write_neo4j_cypher)
GdsTool         = _make_ft(wrapped_run_gds_cypher)

ALL_ADK_TOOLS = {
    "schema": SchemaTool,
    "read"  : CypherReadTool,
    "write" : CypherWriteTool,
    "gds"   : GdsTool,
}
```

*All four now satisfy `isinstance(tool, BaseTool)` and advertise the same JSON-serialisable return shapes the LLM already knows.*

---

## 3 · RBAC factory, ADK edition

Replace the in-memory `CAPABILITIES` map in **rbac.py** with:

```python
from neo4j_adk_tools import ALL_ADK_TOOLS   # ← import the tool objects

CAPABILITIES: Dict[str, FunctionTool] = ALL_ADK_TOOLS
```

Everything else in the role factory stays identical, because the factory only cares that each value is *callable*.  `FunctionTool` objects are.

---

## 4 · Example: spinning up three agents

```python
from google.adk.agents import Agent
from google.adk.runners import Runner
from google.adk.sessions import InMemorySessionService
from google.genai import types

from rbac import build_agent_tools

session_service = InMemorySessionService()
APP = "neo4j_app"; USER = "u1"; SESSION = "s1"

# 1️⃣ Explorer (read-only)
explorer_agent = Agent(
    model="gemini-2.0-pro",
    name="schema_explorer",
    instruction="Answer only from Neo4j schema & MATCH queries.",
    tools=build_agent_tools("explorer"),      # ← FunctionTool list
)

# 2️⃣ Auditor (read+GDS)
auditor_agent = Agent(
    model="gemini-2.0-pro",
    name="gds_auditor",
    instruction="Run analytics on the graph but never mutate it.",
    tools=build_agent_tools("auditor"),
)

# 3️⃣ Builder (full power)
builder_agent = Agent(
    model="gemini-2.0-pro",
    name="world_builder",
    instruction="You may create, merge, and delete nodes as needed.",
    tools=build_agent_tools("builder"),
)

# Quick smoke-test
runner = Runner(agent=builder_agent, app_name=APP, session_service=session_service)
content = types.Content(role="user", parts=[types.Part(text="MATCH (n) RETURN count(n)")])
events = runner.run(user_id=USER, session_id=SESSION, new_message=content)
print(next(e.content.parts[0].text for e in events if e.is_final_response()))
```

*If you swap `builder_agent` with `explorer_agent` and try a `CREATE`, the read wrapper will flag the write attempt and Gemini will explain the error back to you.*

---

## 5 · Long-running GDS?  Easy extension

Many GDS algorithms on big graphs run > 30 s.  To let the agent *stream progress* – e.g., a 5 M-node PageRank – create a generator + `LongRunningFunctionTool`:

```python
from google.adk.tools import LongRunningFunctionTool
import time, itertools
from agent import wrapped_run_gds_cypher

def pagerank_generator(graph_name:str, write_prop:str="rank", **kw):
    """Runs PageRank with incremental ETA updates every 5 s."""
    yield {"status":"pending", "message":"Scheduling GDS job…"}
    job_cypher = f"""
      CALL gds.pageRank.write('{graph_name}', {{
           maxIterations:100, dampingFactor:0.85,
           writeProperty:'{write_prop}'
      }}) YIELD nodePropertiesWritten
    """
    # Fake incremental updates – in prod, poll `gds.job.list()`
    for pct in itertools.accumulate([5]*20):
        time.sleep(5)
        yield {"status":"running", "progress":f"{pct}%"}
        if pct >= 100: break
    # final write
    result = await wrapped_run_gds_cypher(job_cypher)
    return {"status":"completed", "gds_result": result}

PageRankTool = LongRunningFunctionTool(func=pagerank_generator)
```

Then add `"pagerank"` → `PageRankTool` to `CAPABILITIES` and map it to whichever roles you trust.

---

## 6 · Checklist for ADK compliance

| Item | Status |
|------|--------|
| Each tool is a `BaseTool` subclass | ✔ (FunctionTool / LongRunningFunctionTool) |
| Docstring sent to LLM | ✔ (forwarded from wrapper) |
| Parameters are JSON-serialisable | ✔ (wrappers only require `str`, `dict`, `int`, etc.) |
| Return type is `dict` | ✔ already the case |
| Long-running support | ✔ via pattern above |
| Role-gated registration | ✔ `build_agent_tools(role)` |

---

### You’re done

*   Drop **`neo4j_adk_tools.py`** into your repo.  
*   Update `rbac.py` to import the `ALL_ADK_TOOLS` map.  
*   Continue to define new wrappers exactly as before—just pass each through `_make_ft()` and add it to the capabilities map.  

Every agent you spin up in ADK now sees a clean, self-describing set of Neo4j tools, gated by your RBAC policy and ready for long-running analytics when needed.




---



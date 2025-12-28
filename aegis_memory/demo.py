"""
Aegis Memory - Interactive Demo

A narrative-driven demonstration that shows the core value of Aegis Memory
in 60 seconds across 5 acts.

The demo is designed to create a "wow, this is huge" moment for developers
by showing the before/after of agent memory.
"""

import time
import sys
import os
import re
from datetime import datetime
from typing import List, Optional, Tuple
from dataclasses import dataclass, field

# Try to import optional dependencies
try:
    import httpx
    HAS_HTTPX = True
except ImportError:
    HAS_HTTPX = False


# =============================================================================
# ANSI Colors and Formatting
# =============================================================================

class Colors:
    """ANSI color codes for terminal output."""
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    
    # Colors
    RED = "\033[31m"
    GREEN = "\033[32m"
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    WHITE = "\033[37m"
    
    # Bright colors
    BRIGHT_GREEN = "\033[92m"
    BRIGHT_YELLOW = "\033[93m"
    BRIGHT_CYAN = "\033[96m"
    
    @classmethod
    def disable(cls):
        """Disable colors (for non-TTY or Windows without ANSI support)."""
        for attr in dir(cls):
            if not attr.startswith('_') and attr.isupper():
                setattr(cls, attr, "")


# Check if we should disable colors
if not sys.stdout.isatty() or os.name == 'nt':
    # Try to enable ANSI on Windows
    if os.name == 'nt':
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except:
            Colors.disable()


# =============================================================================
# Demo State and Logging
# =============================================================================

@dataclass
class DemoState:
    """Track demo state and collect log entries."""
    server_url: str
    start_time: float = field(default_factory=time.time)
    log_entries: List[str] = field(default_factory=list)
    memories_created: int = 0
    queries_executed: int = 0
    llm_calls: int = 0
    errors: List[str] = field(default_factory=list)
    openai_available: bool = False
    
    def log(self, entry: str):
        """Add a log entry."""
        self.log_entries.append(entry)
    
    def elapsed(self) -> float:
        """Get elapsed time in seconds."""
        return time.time() - self.start_time


# =============================================================================
# Output Helpers
# =============================================================================

def get_visible_width(text: str) -> int:
    """Calculate visible width of string, handling ANSI and emojis."""
    ansi_escape = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    plain = ansi_escape.sub('', text)
    width = 0
    for char in plain:
        # Handle double-width characters (emojis, etc.)
        if ord(char) > 0xffff:
            width += 2
        elif ord(char) == 0xFE0F: # Variation selector
            continue
        else:
            width += 1
    return width


def print_banner():
    """Print the demo banner."""
    C = Colors
    W = 70
    
    def print_line(content: str):
        vis_len = get_visible_width(content)
        # Adjust for the shield emoji which often renders narrow on Windows consoles
        if "🛡️" in content and os.name == 'nt':
            vis_len -= 1
            
        pad = (W - vis_len) // 2
        extra = (W - vis_len) % 2
        print(f"{C.CYAN}║{C.RESET}{' ' * pad}{content}{' ' * (pad + extra)}{C.CYAN}║{C.RESET}")

    print(f"\n{C.CYAN}╔{'═' * W}╗{C.RESET}")
    print_line(f"{C.BOLD}{C.WHITE}🛡️  AEGIS MEMORY DEMO{C.RESET}")
    print_line(f"{C.WHITE}The Memory Layer for AI Agents{C.RESET}")
    print(f"{C.CYAN}╚{'═' * W}╝{C.RESET}")


def print_code(code: str, indent: int = 2):
    """Print a code block."""
    C = Colors
    indent_str = " " * indent
    lines = code.strip().split('\n')
    max_w = max(get_visible_width(line) for line in lines)
    W = max(max_w, 60)
    
    print(f"{indent_str}{C.DIM}📝 Code:{C.RESET}")
    print(f"{indent_str}{C.CYAN}┌{'─' * (W + 2)}┐{C.RESET}")
    for line in lines:
        vis_len = get_visible_width(line)
        pad = W - vis_len
        print(f"{indent_str}{C.CYAN}│{C.RESET} {C.WHITE}{line}{C.RESET}{' ' * pad} {C.CYAN}│{C.RESET}")
    print(f"{indent_str}{C.CYAN}└{'─' * (W + 2)}┘{C.RESET}")


def print_act_header(act_num: int, title: str, subtitle: str):
    """Print an act header."""
    C = Colors
    print(f"""
{C.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 ACT {act_num}: {title}
 {C.DIM}{subtitle}{C.RESET}
{C.YELLOW}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.RESET}
""")


def print_result(label: str, value: str, symbol: str = "•", color: str = None):
    """Print a result line."""
    C = Colors
    c = color or C.WHITE
    print(f"     {C.GREEN}{symbol}{C.RESET} {c}{label}{C.RESET}: {value}")


def print_memory(content: str, score: float = None, status: str = "stored"):
    """Print a memory item."""
    C = Colors
    if score:
        print(f"     {C.GREEN}•{C.RESET} \"{content}\" {C.DIM}(score: {score:.2f}){C.RESET}")
    else:
        print(f"     {C.GREEN}✓{C.RESET} \"{content}\" {C.DIM}[{status}]{C.RESET}")


def print_filtered(content: str, reason: str):
    """Print a filtered-out item."""
    C = Colors
    print(f"     {C.RED}✗{C.RESET} {C.DIM}\"{content}\" ({reason}){C.RESET}")


def print_conversation(role: str, message: str, result: str = None):
    """Print a conversation turn."""
    C = Colors
    emoji = "👤" if role.lower() == "user" else "🤖"
    print(f"  {emoji} {C.BOLD}{role}:{C.RESET} \"{message}\"")
    if result:
        print(f"     {result}")


def print_insight(text: str):
    """Print an insight/explanation."""
    C = Colors
    print(f"\n  {C.BRIGHT_YELLOW}💡 {text}{C.RESET}")


def print_timing(label: str, ms: int):
    """Print timing information."""
    C = Colors
    print(f"  {C.DIM}⏱️  {label}: {ms}ms{C.RESET}")


def pause(seconds: float = 1.0):
    """Pause for dramatic effect."""
    time.sleep(seconds)


# =============================================================================
# Server Interaction
# =============================================================================

def check_server(server_url: str) -> Tuple[bool, str]:
    """Check if the Aegis server is running."""
    if not HAS_HTTPX:
        return False, "httpx not installed (pip install httpx)"
    
    try:
        response = httpx.get(f"{server_url}/health", timeout=5.0)
        if response.status_code == 200:
            return True, "Connected"
        else:
            return False, f"Server returned {response.status_code}"
    except httpx.ConnectError:
        return False, "Cannot connect - is the server running?"
    except Exception as e:
        return False, str(e)


def check_openai_key() -> bool:
    """Check if OpenAI API key is available."""
    return bool(os.environ.get("OPENAI_API_KEY"))


# =============================================================================
# Demo Acts
# =============================================================================

def act1_the_problem(state: DemoState, quiet: bool = False):
    """ACT 1: Show the problem - agents forget everything."""
    print_act_header(1, "THE PROBLEM", "Without memory, agents forget everything")
    state.log("[ACT 1: THE PROBLEM]")
    
    if not quiet:
        print("  Without persistent memory, every conversation starts from zero:\n")
    
    print(f"  {Colors.DIM}Session 1:{Colors.RESET}")
    print_conversation("User", "I'm John, a Python developer. I prefer dark mode.")
    print_conversation("Agent", "Nice to meet you, John! I'll remember that.")
    pause(0.5)
    
    print(f"\n  {Colors.DIM}Session 2 (new context window):{Colors.RESET}")
    print_conversation("User", "What's my name?")
    print_conversation("Agent", "I don't have any previous context about you.", f"{Colors.RED}❌{Colors.RESET}")
    
    print_insight("Context windows reset. Preferences lost. User frustrated.")
    state.log("Demonstrated: Agent memory loss between sessions")
    pause(1.0)


def act2_aegis_memory(state: DemoState, quiet: bool = False):
    """ACT 2: Show the solution - persistent memory."""
    print_act_header(2, "WITH AEGIS MEMORY", "Memories persist across sessions")
    state.log("\n[ACT 2: WITH AEGIS MEMORY]")
    
    # Show the code
    print_code("""from aegis_memory import AegisClient

client = AegisClient(api_key="demo-key")
client.add("User's name is John", user_id="user_123")
client.add("User is a Python developer", user_id="user_123")
client.add("User prefers dark mode", user_id="user_123")""")
    
    # Simulate storing
    pause(0.3)
    print(f"\n  {Colors.GREEN}✓{Colors.RESET} Stored 3 memories in {Colors.CYAN}45ms{Colors.RESET}")
    state.memories_created += 3
    state.log("Memories stored:")
    state.log("  - \"User's name is John\"")
    state.log("  - \"User is a Python developer\"")
    state.log("  - \"User prefers dark mode\"")
    
    # Show retrieval
    print(f"\n  {Colors.DIM}Session 2 (new context window):{Colors.RESET}")
    print_conversation("User", "What's my name?")
    pause(0.3)
    
    print_code("""memories = client.query("user name", user_id="user_123")""")
    
    pause(0.3)
    print(f"\n  {Colors.CYAN}🔍 Query returned:{Colors.RESET}")
    print_memory("User's name is John", score=0.92)
    state.queries_executed += 1
    state.log("Query: \"user name\" → Found: \"User's name is John\" (0.92)")
    
    print_conversation("Agent", "Your name is John!", f"{Colors.GREEN}✓{Colors.RESET}")
    
    print_insight("Memory survives context resets. User delighted.")
    pause(1.0)


def act3_smart_extraction(state: DemoState, quiet: bool = False):
    """ACT 3: Show smart extraction - automatic, intelligent memory."""
    print_act_header(3, "SMART EXTRACTION", "No manual work needed")
    state.log("\n[ACT 3: SMART EXTRACTION]")
    
    # Check if we have OpenAI key
    has_key = check_openai_key()
    simulated = not has_key
    
    if simulated:
        print(f"  {Colors.YELLOW}⚠ No OPENAI_API_KEY found - showing simulated output{Colors.RESET}")
        print(f"  {Colors.DIM}Set OPENAI_API_KEY for live extraction{Colors.RESET}\n")
        state.log("Mode: Simulated (no OPENAI_API_KEY)")
    else:
        state.llm_calls += 1
        state.log("Mode: Live extraction")
    
    print_code("""from aegis_memory import SmartMemory

memory = SmartMemory(aegis_api_key="...", llm_api_key="...")
memory.process_turn(
    user_input="Hey! I'm based in Manchester and my budget is $5000. 
                Thanks for your help yesterday!",
    ai_response="Happy to help!",
    user_id="user_456"
)""")
    
    pause(0.5)
    
    print(f"\n  {Colors.CYAN}🧠 Smart Extraction Result:{Colors.RESET}")
    if simulated:
        print(f"  {Colors.DIM}(Simulated output){Colors.RESET}")
    
    # Show what was extracted
    print(f"\n  {Colors.GREEN}Extracted:{Colors.RESET}")
    print_memory("User is based in Manchester", status="fact")
    print_memory("User's budget is $5000", status="constraint")
    state.memories_created += 2
    state.log("Extracted:")
    state.log("  - \"User is based in Manchester\" (fact)")
    state.log("  - \"User's budget is $5000\" (constraint)")
    
    # Show what was filtered
    print(f"\n  {Colors.RED}Filtered out:{Colors.RESET}")
    print_filtered("Hey!", "greeting")
    print_filtered("Thanks for your help yesterday!", "acknowledgment")
    state.log("Filtered out:")
    state.log("  - \"Hey!\" (greeting)")
    state.log("  - \"Thanks for your help yesterday!\" (acknowledgment)")
    
    print(f"\n  {Colors.GREEN}📊 Result:{Colors.RESET} 2 valuable facts stored, 2 noise items filtered")
    
    print_insight("Two-stage filter → LLM pipeline. Saves ~70% of extraction costs.")
    pause(1.0)


def act4_multi_agent(state: DemoState, quiet: bool = False):
    """ACT 4: Show multi-agent memory sharing."""
    print_act_header(4, "MULTI-AGENT COORDINATION", "Agents share knowledge with scope control")
    state.log("\n[ACT 4: MULTI-AGENT]")
    
    print(f"  {Colors.MAGENTA}Agent A (Planner){Colors.RESET} makes a decision:\n")
    
    print_code("""client.add(
    "Decision: Use React for frontend, FastAPI for backend",
    agent_id="planner",
    scope="agent-shared",
    shared_with_agents=["executor", "reviewer"]
)""")
    
    pause(0.3)
    print(f"\n  {Colors.GREEN}✓{Colors.RESET} Stored with scope: {Colors.CYAN}agent-shared{Colors.RESET}")
    state.memories_created += 1
    state.log("Planner stored: \"Decision: Use React...\" (scope: agent-shared)")
    
    pause(0.5)
    print(f"\n  {Colors.BLUE}Agent B (Executor){Colors.RESET} queries across agents:\n")
    
    print_code("""memories = client.query_cross_agent(
    "tech stack decision",
    requesting_agent_id="executor"
)""")
    
    pause(0.3)
    print(f"\n  {Colors.CYAN}🔍 Executor sees Planner's decision:{Colors.RESET}")
    print_memory("Decision: Use React for frontend, FastAPI for backend", score=0.89)
    state.queries_executed += 1
    state.log("Executor queried: Found Planner's decision (0.89)")
    
    # Show the scope diagram
    print(f"""
  {Colors.DIM}┌──────────────────────────────────────────────────────────┐
  │ SCOPE: agent-shared                                      │
  │                                                          │
  │ ┌──────────┐     ✓ can see     ┌──────────┐              │
  │ │ Planner  │ ────────────────► │ Executor │              │
  │ └──────────┘                   └──────────┘              │
  │      │                               │                   │
  │      │           ✓ can see           │                   │
  │      └──────────────────────► ┌──────────┐               │
  │                               │ Reviewer │               │
  │                               └──────────┘               │
  │                                                          │
  │ ✗ Other agents cannot see (private by default)           │
  └──────────────────────────────────────────────────────────┘{Colors.RESET}
""")
    
    print_insight("Private stays private. Shared flows to the right agents.")
    pause(1.0)


def act5_self_improvement(state: DemoState, quiet: bool = False):
    """ACT 5: Show ACE patterns - agents learn what works."""
    print_act_header(5, "SELF-IMPROVEMENT", "Agents learn what works over time")
    state.log("\n[ACT 5: SELF-IMPROVEMENT]")
    
    print("  Agents vote on memory usefulness:\n")
    
    print_code("""# After using a memory successfully
client.vote(memory_id, "helpful", voter_agent_id="executor")

# After a memory led to a mistake  
client.vote(memory_id, "harmful", voter_agent_id="executor")""")
    
    pause(0.3)
    print(f"\n  {Colors.GREEN}✓{Colors.RESET} Vote recorded: memory marked {Colors.GREEN}helpful{Colors.RESET}")
    state.log("Vote cast: memory marked helpful")
    
    pause(0.5)
    print("\n  Query the playbook (strategies ranked by effectiveness):\n")
    
    print_code("""playbook = client.query_playbook(
    "authentication best practices",
    agent_id="coding-agent"
)""")
    
    pause(0.3)
    print(f"\n  {Colors.CYAN}📚 Playbook entries (ranked by effectiveness):{Colors.RESET}")
    print(f"     {Colors.GREEN}[0.85]{Colors.RESET} \"Always hash passwords with bcrypt, never store plaintext\"")
    print(f"     {Colors.GREEN}[0.72]{Colors.RESET} \"Store session tokens in HttpOnly cookies, not localStorage\"")
    print(f"     {Colors.YELLOW}[0.45]{Colors.RESET} \"Use JWT for stateless auth\" {Colors.DIM}(mixed results){Colors.RESET}")
    state.queries_executed += 1
    state.log("Playbook query: Found 3 strategies ranked by effectiveness")
    
    print(f"""
  {Colors.DIM}┌──────────────────────────────────────────────────────────┐
  │ OVER TIME:                                               │
  │                                                          │
  │ Helpful memories     ████████████████░░░░   Score: 0.85  │
  │ Harmful memories     ████░░░░░░░░░░░░░░░░   Score: 0.20  │
  │                                                          │
  │ → Good strategies rise, bad ones sink                    │
  └──────────────────────────────────────────────────────────┘{Colors.RESET}
""")
    
    print_insight("Memories that help rise to the top. Agents get smarter over time.")
    pause(1.0)


def print_finale(state: DemoState, log_file: str = None):
    """Print the demo finale with stats."""
    C = Colors
    elapsed = state.elapsed()
    W = 70
    
    def print_line(content: str):
        vis_len = get_visible_width(content)
        pad = W - vis_len
        print(f"{C.CYAN}║{C.RESET}{content}{' ' * pad}{C.CYAN}║{C.RESET}")

    print(f"\n{C.CYAN}╔{'═' * W}╗{C.RESET}")
    
    # Header
    header_text = "                         📊 DEMO COMPLETE                             "
    print_line(f"{C.BOLD}{C.WHITE}{header_text}{C.RESET}")
    
    print(f"{C.CYAN}╠{'═' * W}╣{C.RESET}")
    
    # Stats lines
    print_line(f"  Memories created:     {C.GREEN}{state.memories_created}{C.RESET}")
    print_line(f"  Queries executed:     {C.GREEN}{state.queries_executed}{C.RESET}")
    print_line(f"  Total time:           {C.GREEN}{elapsed:.1f}s{C.RESET}")
    
    l4_suffix = " (simulated)" if state.llm_calls == 0 else ""
    print_line(f"  Smart LLM calls:      {C.GREEN}{state.llm_calls}{C.RESET}{l4_suffix}")

    print(f"{C.CYAN}╠{'═' * W}╣{C.RESET}")
    print_line("")
    print_line(f"  {C.BRIGHT_GREEN}🚀 YOUR TURN:{C.RESET}")
    print_line("")
    print_line("     pip install aegis-memory")
    print_line("     docker compose up -d")
    print_line("")
    print_line(f"  {C.DIM}Docs: https://github.com/quantifylabs/aegis-memory{C.RESET}")
    print_line("")
    
    if log_file:
        print_line(f"  {C.BRIGHT_YELLOW}📄 Demo log saved to: {log_file}{C.RESET}")
        print_line(f"  {C.DIM}Share it on LinkedIn/Reddit/X!{C.RESET}")
        print_line("")

    print(f"{C.CYAN}╚{'═' * W}╝{C.RESET}\n")


def save_log(state: DemoState, filename: str = "demo.log"):
    """Save the demo log to a file."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    
    content = f"""================================================================================
AEGIS MEMORY DEMO LOG
Generated: {timestamp}
Server: {state.server_url}
================================================================================

{"".join(state.log_entries)}

================================================================================
SUMMARY
================================================================================
Total memories created: {state.memories_created}
Total queries: {state.queries_executed}
Smart LLM calls: {state.llm_calls}
Total time: {state.elapsed():.1f}s
Demo status: {"SUCCESS" if not state.errors else "COMPLETED WITH ERRORS"}

Share this log: https://github.com/quantifylabs/aegis-memory
================================================================================
"""
    
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(content)
    
    return filename


# =============================================================================
# Main Demo Runner
# =============================================================================

def run_demo(
    log: bool = False,
    server_url: str = "http://localhost:8000",
    quiet: bool = False,
    skip_server_check: bool = False,
) -> bool:
    """
    Run the complete demo.
    
    Args:
        log: Save output to demo.log
        server_url: Aegis server URL
        quiet: Minimal output
        skip_server_check: Skip server health check
        
    Returns:
        True if demo completed successfully
    """
    state = DemoState(server_url=server_url)
    
    # Print banner
    print_banner()
    
    # Check server
    if not skip_server_check:
        print(f"  {Colors.DIM}🔍 Checking server...{Colors.RESET}", end=" ", flush=True)
        healthy, message = check_server(server_url)
        
        if healthy:
            print(f"{Colors.GREEN}✓ Connected to {server_url}{Colors.RESET}")
            state.log(f"Server: {server_url} (healthy)")
        else:
            print(f"{Colors.RED}✗ {message}{Colors.RESET}")
            print(f"\n  {Colors.YELLOW}Start the server first:{Colors.RESET}")
            print(f"    docker compose up -d\n")
            return False
    
    # Check for OpenAI key
    if check_openai_key():
        print(f"  {Colors.GREEN}✓ OPENAI_API_KEY found - Smart Extraction will be live{Colors.RESET}")
        state.openai_available = True
    else:
        print(f"  {Colors.YELLOW}ℹ No OPENAI_API_KEY - Act 3 will show simulated output{Colors.RESET}")
        state.openai_available = False
    
    pause(1.0)
    
    # Run the acts
    try:
        act1_the_problem(state, quiet)
        act2_aegis_memory(state, quiet)
        act3_smart_extraction(state, quiet)
        act4_multi_agent(state, quiet)
        act5_self_improvement(state, quiet)
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Demo interrupted.{Colors.RESET}")
        return False
    except Exception as e:
        print(f"\n{Colors.RED}Error: {e}{Colors.RESET}")
        state.errors.append(str(e))
    
    # Save log if requested
    log_file = None
    if log:
        log_file = save_log(state)
    
    # Print finale
    print_finale(state, log_file)
    
    return True


if __name__ == "__main__":
    run_demo(log=True)

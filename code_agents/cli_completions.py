"""CLI completions and help command — extracted from cli.py."""

from __future__ import annotations

import os
import sys

from .cli_helpers import _colors


def _get_commands() -> dict:
    """Lazy import COMMANDS to avoid circular import."""
    from .cli import COMMANDS
    return COMMANDS

_AGENT_NAMES_FOR_COMPLETION = [
    "agent-router", "argocd-verify", "auto-pilot", "code-reasoning",
    "code-reviewer", "code-tester", "code-writer", "git-ops",
    "jenkins-cicd", "pipeline-orchestrator",
    "qa-regression", "redash-query", "test-coverage",
]

# Subcommands for commands that take them
_SUBCOMMANDS = {
    "rules":    ["list", "create", "edit", "delete"],
    "pipeline": ["start", "status", "advance", "rollback"],
    "start":    ["--fg", "--foreground"],
    "rules create": ["--global", "--agent"],
    "rules list": ["--agent"],
    "chat":     _AGENT_NAMES_FOR_COMPLETION,
}


def _generate_zsh_completion() -> str:
    """Generate zsh completion script for code-agents."""
    cmds = sorted(_get_commands().keys())
    cmd_list = " ".join(cmds) + " help"
    agents = " ".join(_AGENT_NAMES_FOR_COMPLETION)

    # Build agent list as individual zsh array entries
    agents_zsh = " ".join(f"'{a}'" for a in _AGENT_NAMES_FOR_COMPLETION)

    return f'''#compdef code-agents
# Zsh completion for code-agents CLI
# Install: code-agents completions --zsh >> ~/.zshrc

_code_agents() {{
    local -a commands
    commands=(
        'init:Initialize code-agents in current repo'
        'migrate:Migrate legacy .env to centralized config'
        'rules:Manage agent rules (list/create/edit/delete)'
        'start:Start the server'
        'restart:Restart the server'
        'chat:Interactive chat with agents'
        'shutdown:Shutdown the server'
        'status:Check server health and config'
        'agents:List all available agents'
        'config:Show current configuration'
        'doctor:Diagnose common issues'
        'logs:Tail the log file'
        'diff:Show git diff between branches'
        'branches:List git branches'
        'test:Run tests on the target repo'
        'review:Review code changes with AI'
        'pipeline:Manage CI/CD pipeline'
        'setup:Full interactive setup wizard'
        'curls:Show API curl commands'
        'version:Show version info'
        'help:Show help'
        'completions:Generate shell completion script'
    )

    local -a rules_subcmds
    rules_subcmds=('list:List active rules' 'create:Create a new rule' 'edit:Edit a rule file' 'delete:Delete a rule file')

    local -a pipeline_subcmds
    pipeline_subcmds=('start:Start pipeline' 'status:Show pipeline status' 'advance:Advance pipeline step' 'rollback:Rollback deployment')

    if (( CURRENT == 2 )); then
        _describe 'command' commands
    elif (( CURRENT == 3 )); then
        case $words[2] in
            init)
                compadd -- '--backend' '--server' '--jenkins' '--argocd' '--redash' '--elastic' '--atlassian' '--testing'
                ;;
            rules)
                _describe 'subcommand' rules_subcmds
                ;;
            pipeline)
                _describe 'subcommand' pipeline_subcmds
                ;;
            chat)
                compadd -- {agents_zsh}
                ;;
            start)
                compadd -- '--fg' '--foreground'
                ;;
        esac
    elif (( CURRENT == 4 )); then
        case "$words[2] $words[3]" in
            "rules create"|"rules list")
                compadd -- '--global' '--agent'
                ;;
        esac
    elif (( CURRENT >= 4 )); then
        # After --agent anywhere in the line, complete agent names
        if [[ "${{words[CURRENT-1]}}" == "--agent" ]]; then
            compadd -- {agents_zsh}
        fi
    fi
}}

compdef _code_agents code-agents
'''


def _generate_bash_completion() -> str:
    """Generate bash completion script for code-agents."""
    cmds = sorted(_get_commands().keys())
    cmd_list = " ".join(cmds) + " help completions"

    return f'''# Bash completion for code-agents CLI
# Install: code-agents completions --bash >> ~/.bashrc

_code_agents_completions() {{
    local cur prev commands
    COMPREPLY=()
    cur="${{COMP_WORDS[COMP_CWORD]}}"
    prev="${{COMP_WORDS[COMP_CWORD-1]}}"

    commands="{cmd_list}"

    if [[ $COMP_CWORD -eq 1 ]]; then
        COMPREPLY=( $(compgen -W "$commands" -- "$cur") )
    elif [[ $COMP_CWORD -eq 2 ]]; then
        case "$prev" in
            init)
                COMPREPLY=( $(compgen -W "--backend --server --jenkins --argocd --redash --elastic --atlassian --testing" -- "$cur") )
                ;;
            rules)
                COMPREPLY=( $(compgen -W "list create edit delete" -- "$cur") )
                ;;
            pipeline)
                COMPREPLY=( $(compgen -W "start status advance rollback" -- "$cur") )
                ;;
            chat)
                COMPREPLY=( $(compgen -W "agent-router argocd-verify code-reasoning code-reviewer code-tester code-writer git-ops jenkins-build jenkins-deploy pipeline-orchestrator redash-query test-coverage" -- "$cur") )
                ;;
            start)
                COMPREPLY=( $(compgen -W "--fg --foreground" -- "$cur") )
                ;;
        esac
    elif [[ $COMP_CWORD -eq 3 ]]; then
        case "${{COMP_WORDS[1]}} ${{COMP_WORDS[2]}}" in
            "rules create"|"rules list")
                COMPREPLY=( $(compgen -W "--global --agent" -- "$cur") )
                ;;
        esac
    elif [[ $COMP_CWORD -eq 4 ]] && [[ "$prev" == "--agent" ]]; then
        COMPREPLY=( $(compgen -W "agent-router argocd-verify code-reasoning code-reviewer code-tester code-writer git-ops jenkins-build jenkins-deploy pipeline-orchestrator redash-query test-coverage" -- "$cur") )
    fi
}}

complete -F _code_agents_completions code-agents
'''


def cmd_completions(rest: list[str] | None = None):
    """Generate shell completion script."""
    rest = rest or []
    bold, green, yellow, red, cyan, dim = _colors()

    if "--zsh" in rest:
        print(_generate_zsh_completion())
    elif "--bash" in rest:
        print(_generate_bash_completion())
    elif "--install" in rest:
        # Auto-detect shell and install
        shell_rc = None
        if os.path.exists(os.path.expanduser("~/.zshrc")):
            shell_rc = os.path.expanduser("~/.zshrc")
            script = _generate_zsh_completion()
            marker = "# code-agents completion"
        elif os.path.exists(os.path.expanduser("~/.bashrc")):
            shell_rc = os.path.expanduser("~/.bashrc")
            script = _generate_bash_completion()
            marker = "# code-agents completion"
        else:
            print(red("  Could not detect shell config (~/.zshrc or ~/.bashrc)"))
            return

        # Check if already installed
        with open(shell_rc) as f:
            if marker in f.read():
                print(green(f"  ✓ Completions already installed in {shell_rc}"))
                return

        with open(shell_rc, "a") as f:
            f.write(f"\n{marker}\n")
            f.write(script)
            f.write(f"\n")

        print(green(f"  ✓ Completions installed in {shell_rc}"))
        print(dim(f"    Restart your terminal or run: source {shell_rc}"))
    else:
        print()
        print(bold("  Generate shell completion for code-agents"))
        print()
        print(f"    {cyan('code-agents completions --install')}    {dim('Auto-install to ~/.zshrc or ~/.bashrc')}")
        print(f"    {cyan('code-agents completions --zsh')}        {dim('Print zsh completion script')}")
        print(f"    {cyan('code-agents completions --bash')}       {dim('Print bash completion script')}")
        print()


def cmd_help():
    """Show comprehensive help with all commands, args, and examples."""
    bold, green, yellow, red, cyan, dim = _colors()
    p = print  # shorthand

    p()
    p(bold("  code-agents — AI-powered code agent platform"))
    p(bold("  " + "─" * 50))
    p()
    p(bold("  USAGE:"))
    p(f"    code-agents {cyan('<command>')} [args] [options]")
    p()

    # ── Getting Started ──
    p(bold("  GETTING STARTED"))
    p()
    p(f"    {cyan('init')}")
    p(f"      Initialize code-agents in the current repo directory.")
    p(f"      Run with no flags for full wizard, or specify a section to update:")
    p(f"        {dim('--backend')}    API keys (Cursor/Claude)")
    p(f"        {dim('--server')}     Host and port")
    p(f"        {dim('--jenkins')}    Jenkins CI/CD build and deploy")
    p(f"        {dim('--argocd')}     ArgoCD deployment verification")
    p(f"        {dim('--redash')}     Redash database queries")
    p(f"        {dim('--elastic')}    Elasticsearch integration")
    p(f"        {dim('--atlassian')}  Atlassian OAuth")
    p(f"        {dim('--testing')}    Test command and coverage threshold")
    p(f"      {dim('$ code-agents init')}")
    p(f"      {dim('$ code-agents init --jenkins')}")
    p(f"      {dim('$ code-agents init --jenkins --argocd')}")
    p()
    p(f"    {cyan('migrate')}")
    p(f"      Migrate a legacy .env file to centralized config.")
    p(f"      Splits variables: API keys → global, Jenkins/ArgoCD → per-repo.")
    p(f"      Backs up the original .env file.")
    p(f"      {dim('$ code-agents migrate')}")
    p()
    p(f"    {cyan('rules')} {dim('[list|create|edit|delete]')}")
    p(f"      Manage agent rules — persistent instructions injected into prompts.")
    p(f"      Rules auto-refresh: edit a file mid-chat and the next message picks it up.")
    p(f"        {dim('list')}                 List active rules (default)")
    p(f"        {dim('list --agent X')}       List rules for a specific agent")
    p(f"        {dim('create')}               Create project rule for all agents")
    p(f"        {dim('create --agent X')}     Create project rule for specific agent")
    p(f"        {dim('create --global')}      Create global rule for all agents")
    p(f"        {dim('edit <path>')}          Edit a rule file in $EDITOR")
    p(f"        {dim('delete <path>')}        Delete a rule file")
    p(f"      {dim('$ code-agents rules')}")
    p(f"      {dim('$ code-agents rules create --agent code-writer')}")
    p()
    p(f"    {cyan('start')} {dim('[--fg]')}")
    p(f"      Start the server in background. Loads global + per-repo config.")
    p(f"      Shows URLs, PID, and curl commands when started.")
    p(f"        {dim('--fg')}    Run in foreground (shows logs, Ctrl+C to stop)")
    p(f"      {dim('$ code-agents start')}")
    p(f"      {dim('$ code-agents start --fg')}")
    p()
    p(f"    {cyan('restart')}")
    p(f"      Restart the server (shutdown + start).")
    p(f"      Stops the running server, then starts a new one.")
    p(f"      {dim('$ code-agents restart')}")
    p()
    p(f"    {cyan('chat')} {dim('[agent-name]')}")
    p(f"      Open interactive chat REPL. If no agent specified, shows a")
    p(f"      numbered menu to pick from all 12 agents. Each agent stays")
    p(f"      in its role (writer writes code, tester writes tests, etc.).")
    p(f"      Supports multi-turn sessions, streaming, agent switching, and auto-saved history.")
    p(f"        {dim('<agent-name>')}  Skip menu, start directly with this agent")
    p(f"        {dim('--resume <id>')}      Resume a saved chat session by UUID")
    p(f"      {dim('$ code-agents chat                  # pick from menu')}")
    p(f"      {dim('$ code-agents chat code-reasoning   # start with reasoning')}")
    p(f"      {dim('$ code-agents chat code-writer      # start with writer')}")
    p(f"      {dim('$ code-agents chat code-tester      # start with tester')}")
    p(f"      {dim('$ code-agents chat --resume <uuid>  # resume a saved session')}")
    p()
    p(f"      {bold('Chat slash commands (inside the chat):')}")
    p(f"        {cyan('/help'):<18} Show all chat commands")
    p(f"        {cyan('/quit'):<18} Exit the chat (also: /exit, /q, or Ctrl+C)")
    p(f"        {cyan('/agent <name>'):<18} Switch to another agent (clears session)")
    p(f"                           Examples: /agent code-writer, /agent code-tester")
    p(f"        {cyan('/agents'):<18} List all 12 agents with roles, mark current")
    p(f"        {cyan('/rules'):<18} Show active rules for the current agent")
    p(f"        {cyan('/run <cmd>'):<18} Run a shell command in the repo directory")
    p(f"        {cyan('/session'):<18} Show current session ID (for multi-turn context)")
    p(f"        {cyan('/clear'):<18} Clear session — next message starts fresh")
    p(f"        {cyan('/history'):<18} List saved chat sessions with UUIDs")
    p(f"        {cyan('/resume <id>'):<18} Resume a saved chat by session UUID")
    p(f"        {cyan('/delete-chat <id>'):<18} Delete a saved chat by session UUID")
    p(f"        {cyan('/<agent> <prompt>'):<18} Delegate a one-shot prompt to another agent")
    p()
    p(f"      {bold('Agent Rules (persistent instructions):')}")
    p(f"        Rules are markdown files injected into agent system prompts.")
    p(f"        Global: ~/.code-agents/rules/  |  Project: .code-agents/rules/")
    p(f"        _global.md → all agents  |  code-writer.md → specific agent")
    p(f"        Auto-refresh: edit mid-chat, next message picks it up.")
    p(f"        {dim('$ code-agents rules                      # list active rules')}")
    p(f"        {dim('$ code-agents rules create --agent X     # create for specific agent')}")
    p(f"        {dim('$ code-agents rules create --global      # create global rule')}")
    p()
    p(f"      {bold('Available agents for chat:')}")
    p(f"        code-reasoning       {dim('Explain architecture, trace flows (read-only)')}")
    p(f"        code-writer          {dim('Write/modify code, refactor, implement features')}")
    p(f"        code-reviewer        {dim('Review for bugs, security, style violations')}")
    p(f"        code-tester          {dim('Write tests, debug, optimize code quality')}")
    p(f"        redash-query         {dim('SQL queries, explore database schemas')}")
    p(f"        git-ops              {dim('Git branches, diffs, logs, push')}")
    p(f"        test-coverage        {dim('Run tests, coverage reports, find gaps')}")
    p(f"        jenkins-build        {dim('Trigger/monitor Jenkins CI builds')}")
    p(f"        jenkins-deploy       {dim('Trigger/monitor Jenkins deployments')}")
    p(f"        argocd-verify        {dim('Check pods, scan logs, rollback deployments')}")
    p(f"        pipeline-orchestrator {dim('Guide full CI/CD pipeline end-to-end')}")
    p(f"        agent-router         {dim('Help pick the right specialist agent')}")
    p()
    p(f"    {cyan('setup')}")
    p(f"      Full interactive setup wizard (7 steps). Same as code-agents-setup.")
    p(f"      Checks Python, installs deps, prompts for all keys, writes .env.")
    p(f"      {dim('$ code-agents setup')}")
    p()

    p(f"    {cyan('sessions')} {dim('[--all | delete <id> | clear]')}")
    p(f"      List and manage saved chat sessions.")
    p(f"      Sessions are auto-saved during chat and stored in ~/.code-agents/chat_history/.")
    p(f"        {dim('--all')}           Show sessions from all repos (default: current repo)")
    p(f"        {dim('delete <id>')}     Delete a session by UUID")
    p(f"        {dim('clear')}           Delete all saved sessions")
    p(f"      {dim('$ code-agents sessions')}")
    p(f"      {dim('$ code-agents sessions delete <uuid>')}")
    p()

    # ── Server ──
    p(bold("  SERVER MANAGEMENT"))
    p()
    p(f"    {cyan('shutdown')}")
    p(f"      Stop the running server. Finds and kills the process on the")
    p(f"      configured PORT (default 8000). Uses SIGTERM then SIGKILL.")
    p(f"      {dim('$ code-agents shutdown')}")
    p()
    p(f"    {cyan('status')}")
    p(f"      Check if the server is running. Shows health, version, agent count,")
    p(f"      integration status (Jenkins/ArgoCD/Elasticsearch), and curl commands.")
    p(f"      {dim('$ code-agents status')}")
    p()
    p(f"    {cyan('logs')} {dim('[lines]')}")
    p(f"      Tail the log file in real-time (Ctrl+C to stop).")
    p(f"      Log file: logs/code-agents.log (hourly rotation, 7-day retention).")
    p(f"        {dim('<lines>')}  Number of lines to show (default: 50)")
    p(f"      {dim('$ code-agents logs           # last 50 lines, live')}")
    p(f"      {dim('$ code-agents logs 200       # last 200 lines, live')}")
    p()
    p(f"    {cyan('config')}")
    p(f"      Show current .env configuration from the current directory.")
    p(f"      Groups by category (Core, Server, Jenkins, ArgoCD, etc.).")
    p(f"      Secrets are masked (shows first/last 4 chars only).")
    p(f"      {dim('$ code-agents config')}")
    p()
    p(f"    {cyan('doctor')}")
    p(f"      Diagnose common issues. Checks: Python version, .env file,")
    p(f"      API keys, cursor-agent-sdk, server running, Jenkins/ArgoCD config,")
    p(f"      git repo, log directory. Reports issues with fix suggestions.")
    p(f"      {dim('$ code-agents doctor')}")
    p()

    # ── Git ──
    p(bold("  GIT OPERATIONS"))
    p()
    p(f"    {cyan('branches')}")
    p(f"      List all git branches. Highlights the current branch.")
    p(f"      Works with or without the server running (falls back to git).")
    p(f"      {dim('$ code-agents branches')}")
    p()
    p(f"    {cyan('diff')} {dim('[base] [head]')}")
    p(f"      Show diff between two branches with file-level stats.")
    p(f"        {dim('<base>')}  Base branch (default: main)")
    p(f"        {dim('<head>')}  Head branch (default: HEAD)")
    p(f"      {dim('$ code-agents diff                    # main vs HEAD')}")
    p(f"      {dim('$ code-agents diff main feature-123   # main vs feature-123')}")
    p(f"      {dim('$ code-agents diff develop HEAD       # develop vs HEAD')}")
    p()

    # ── CI/CD ──
    p(bold("  CI/CD & TESTING"))
    p()
    p(f"    {cyan('test')} {dim('[branch]')}")
    p(f"      Run tests on the target repository. Auto-detects test framework")
    p(f"      (pytest, jest, maven, gradle, go). Shows pass/fail/error counts.")
    p(f"        {dim('<branch>')}  Checkout this branch before running (optional)")
    p(f"      {dim('$ code-agents test                    # test current branch')}")
    p(f"      {dim('$ code-agents test feature-123        # test specific branch')}")
    p()
    p(f"    {cyan('review')} {dim('[base] [head]')}")
    p(f"      AI-powered code review. Gets the diff between branches and sends")
    p(f"      it to the code-reviewer agent for bug/security/style analysis.")
    p(f"        {dim('<base>')}  Base branch (default: main)")
    p(f"        {dim('<head>')}  Head branch (default: HEAD)")
    p(f"      {dim('$ code-agents review                  # review HEAD vs main')}")
    p(f"      {dim('$ code-agents review main feature-123 # review specific range')}")
    p()
    p(f"    {cyan('pipeline')} {dim('<subcommand> [args]')}")
    p(f"      Manage the 6-step CI/CD pipeline:")
    p(f"      connect → review/test → build → deploy → verify → rollback")
    p()
    p(f"      {cyan('pipeline start')} {dim('[branch]')}")
    p(f"        Start a new pipeline run. Uses current branch if not specified.")
    p(f"        {dim('$ code-agents pipeline start')}")
    p(f"        {dim('$ code-agents pipeline start feature-123')}")
    p()
    p(f"      {cyan('pipeline status')} {dim('[run_id]')}")
    p(f"        Show pipeline status. Without run_id, lists all runs.")
    p(f"        {dim('$ code-agents pipeline status')}")
    p(f"        {dim('$ code-agents pipeline status abc123')}")
    p()
    p(f"      {cyan('pipeline advance')} {dim('<run_id>')}")
    p(f"        Mark current step as done and advance to the next step.")
    p(f"        {dim('$ code-agents pipeline advance abc123')}")
    p()
    p(f"      {cyan('pipeline rollback')} {dim('<run_id>')}")
    p(f"        Trigger rollback. Skips remaining steps, jumps to step 6.")
    p(f"        {dim('$ code-agents pipeline rollback abc123')}")
    p()

    # ── Other ──
    p(bold("  INFORMATION"))
    p()
    p(f"    {cyan('agents')}")
    p(f"      List all 12 available agents with backend, model, and permissions.")
    p(f"      Works with or without the server running.")
    p(f"      {dim('$ code-agents agents')}")
    p()
    p(f"    {cyan('curls')} {dim('[category | agent-name]')}")
    p(f"      Show copy-pasteable curl commands for all API endpoints.")
    p(f"      Without args: shows category index + agent list.")
    p(f"      With category: shows curls for that category only.")
    p(f"      With agent name: shows agent-specific curls + example prompts.")
    p(f"        Categories: health, agents, git, testing, jenkins, argocd,")
    p(f"                    pipeline, redash, elasticsearch")
    p(f"      {dim('$ code-agents curls                   # show index')}")
    p(f"      {dim('$ code-agents curls jenkins           # jenkins curls only')}")
    p(f"      {dim('$ code-agents curls argocd            # argocd curls only')}")
    p(f"      {dim('$ code-agents curls code-reviewer     # curls for code-reviewer')}")
    p(f"      {dim('$ code-agents curls pipeline          # pipeline curls only')}")
    p()
    p(f"    {cyan('update')}")
    p(f"      Update code-agents to latest version from git.")
    p(f"      Pulls latest code, reinstalls dependencies, shows changelog.")
    p(f"      {dim('$ code-agents update')}")
    p()
    p(f"    {cyan('version')}")
    p(f"      Show version, Python version, and install location.")
    p(f"      {dim('$ code-agents version')}")
    p()
    p(f"    {cyan('help')}")
    p(f"      Show this help message with all commands and arguments.")
    p(f"      {dim('$ code-agents help')}")
    p()

    # ── Install ──
    p(bold("  INSTALLATION"))
    p()
    p(f"    {dim('# One-command install (from anywhere):')}")
    p(f"    curl -fsSL https://raw.githubusercontent.com/shivanshu1gupta-paytmpayments/code-agents/main/install.sh | bash")
    p()
    p(f"    {dim('# Then initialize in any project:')}")
    p(f"    cd /path/to/your-project")
    p(f"    code-agents init")
    p(f"    code-agents start")
    p(f"    code-agents chat")
    p()


def main():
    """CLI entry point — dispatches to subcommands."""
    args = sys.argv[1:]

    if not args:
        cmd_start()
        return

    command = args[0].lower()
    rest = args[1:]

    try:
        if command in ("--help", "-h", "help"):
            cmd_help()
        elif command == "update":
            cmd_update()
        elif command in ("--version", "-v", "version"):
            cmd_version()
        elif command == "init":
            cmd_init()
        elif command == "start":
            cmd_start()
        elif command == "restart":
            cmd_restart()
        elif command == "chat":
            from .chat import chat_main
            chat_main(rest)
        elif command == "sessions":
            cmd_sessions(rest)
        elif command == "shutdown":
            cmd_shutdown()
        elif command == "status":
            cmd_status()
        elif command == "agents":
            cmd_agents()
        elif command == "config":
            cmd_config()
        elif command == "doctor":
            cmd_doctor()
        elif command == "logs":
            cmd_logs(rest)
        elif command == "diff":
            cmd_diff(rest)
        elif command == "branches":
            cmd_branches()
        elif command == "test":
            cmd_test(rest)
        elif command == "review":
            cmd_review(rest)
        elif command == "pipeline":
            cmd_pipeline(rest)
        elif command == "curls":
            cmd_curls(rest)
        elif command == "setup":
            from .setup import main as setup_main
            setup_main()
        elif command == "migrate":
            cmd_migrate()
        elif command == "rules":
            cmd_rules(rest)
        elif command == "completions":
            cmd_completions(rest)
        else:
            print(f"  Unknown command: {command}")
            print(f"  Run 'code-agents help' for usage.")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n  Cancelled.")
    except EOFError:
        print("\n  Cancelled.")


if __name__ == "__main__":
    main()


"""Shell auto-completion script generators for mcp-mesh CLI (Bash, Zsh, PowerShell).
Pure Python standard library. Zero external dependencies.
"""

from __future__ import annotations


BASH_TEMPLATE = """# Bash completion script for mcp-mesh
# Usage:
#   source <(mcp-mesh completion bash)
# Or install permanently:
#   mcp-mesh completion bash > ~/.local/share/bash-completion/completions/mcp-mesh

_mcp_mesh_completion() {
    local cur prev words cword
    if type _init_completion &>/dev/null; then
        _init_completion -n : 2>/dev/null || return
    else
        cur="${COMP_WORDS[COMP_CWORD]}"
        prev="${COMP_WORDS[COMP_CWORD-1]}"
        words=("${COMP_WORDS[@]}")
        cword=$COMP_CWORD
    fi

    local commands="run stats search inspect doctor sse monitor demo completion"
    local global_flags="--help -h --version -v --demo -d"

    if [[ $cword -eq 1 ]]; then
        COMPREPLY=($(compgen -W "$commands $global_flags" -- "$cur"))
        return 0
    fi

    local cmd="${words[1]}"
    case "$cmd" in
        run)
            COMPREPLY=($(compgen -W "--config -c --mode -m --federate -f --serial-discovery --help -h" -- "$cur"))
            ;;
        stats)
            COMPREPLY=($(compgen -W "--config -c --federate -f --db --sql --help -h" -- "$cur"))
            ;;
        search)
            COMPREPLY=($(compgen -W "--limit -l --federate -f --help -h" -- "$cur"))
            ;;
        inspect)
            COMPREPLY=($(compgen -W "--help -h" -- "$cur"))
            ;;
        doctor)
            COMPREPLY=($(compgen -W "--config -c --help -h" -- "$cur"))
            ;;
        sse)
            COMPREPLY=($(compgen -W "--config -c --host -H --port -p --mode -m --token -t --cors-origin --insecure-no-auth --help -h" -- "$cur"))
            ;;
        monitor)
            COMPREPLY=($(compgen -W "--demo -d --iterations -n --interval -i --help -h" -- "$cur"))
            ;;
        demo)
            COMPREPLY=($(compgen -W "--help -h" -- "$cur"))
            ;;
        completion)
            COMPREPLY=($(compgen -W "bash zsh powershell pwsh --help -h" -- "$cur"))
            ;;
        *)
            COMPREPLY=($(compgen -W "$commands" -- "$cur"))
            ;;
    esac
    return 0
}

complete -F _mcp_mesh_completion mcp-mesh
"""

ZSH_TEMPLATE = """#compdef mcp-mesh
# Zsh completion script for mcp-mesh
# Usage:
#   eval "$(mcp-mesh completion zsh)"
# Or install in your fpath (~/.zfunc/_mcp-mesh):
#   mcp-mesh completion zsh > ~/.zfunc/_mcp-mesh

_mcp_mesh() {
    local -a commands
    commands=(
        'run:Start MCP stdio proxy gateway for Claude/Cursor/Antigravity'
        'stats:Display token savings metrics and server summary'
        'search:Test natural language tool discovery in terminal'
        'inspect:Inspect full JSON schema for an indexed tool'
        'doctor:Run comprehensive diagnostic health check on MCP environment'
        'sse:Start HTTP/SSE streaming gateway daemon for remote agents'
        'monitor:Start real-time ANSI terminal telemetry dashboard'
        'demo:Run interactive zero-config demonstration and benchmark'
        'completion:Generate shell auto-completion scripts'
    )

    _arguments -C \\
        '(-v --version)'{-v,--version}'[Display version number]' \\
        '(-d --demo)'{-d,--demo}'[Run interactive zero-config demonstration]' \\
        '(-h --help)'{-h,--help}'[Show help message]' \\
        '1: :->command' \\
        '*:: :->args'

    case $state in
        command)
            _describe -t commands 'mcp-mesh subcommands' commands
            ;;
        args)
            case $words[1] in
                run)
                    _arguments \\
                        '(-c --config)'{-c,--config}'[Path to MCP configuration file]:config file:_files' \\
                        '(-m --mode)'{-m,--mode}'[Proxy mode]:mode:(lazy passthrough)' \\
                        '(-f --federate)'{-f,--federate}'[Auto-discover system MCP servers]' \\
                        '--serial-discovery[Run tool discovery sequentially]'
                    ;;
                stats)
                    _arguments \\
                        '(-c --config)'{-c,--config}'[Path to MCP configuration file]:config file:_files' \\
                        '(-f --federate)'{-f,--federate}'[Include federated system MCP servers]' \\
                        '--db[Display lifetime SQLite telemetry metrics]' \\
                        '--sql[Execute custom read-only SQL query]:query:'
                    ;;
                search)
                    _arguments \\
                        '(-l --limit)'{-l,--limit}'[Max candidates to return]:limit:' \\
                        '(-f --federate)'{-f,--federate}'[Search across federated tools]' \\
                        '1:query:'
                    ;;
                inspect)
                    _arguments '1:tool_key:'
                    ;;
                doctor)
                    _arguments '(-c --config)'{-c,--config}'[Path to configuration file]:config file:_files'
                    ;;
                sse)
                    _arguments \\
                        '(-c --config)'{-c,--config}'[Path to MCP configuration file]:config file:_files' \\
                        '(-H --host)'{-H,--host}'[Host interface to bind]:host:' \\
                        '(-p --port)'{-p,--port}'[Port to listen on]:port:' \\
                        '(-m --mode)'{-m,--mode}'[Proxy mode]:mode:(lazy passthrough)' \\
                        '(-t --token)'{-t,--token}'[Bearer token]:token:' \\
                        '--cors-origin[Allowed CORS origins]:origin:' \\
                        '--insecure-no-auth[Allow binding to non-loopback without auth]'
                    ;;
                monitor)
                    _arguments \\
                        '(-d --demo)'{-d,--demo}'[Simulated multi-turn agent telemetry]' \\
                        '(-n --iterations)'{-n,--iterations}'[Number of ticks]:count:' \\
                        '(-i --interval)'{-i,--interval}'[Refresh interval in seconds]:seconds:'
                    ;;
                completion)
                    _arguments '1:shell:(bash zsh powershell pwsh)'
                    ;;
            esac
            ;;
    esac
}

_mcp_mesh "$@"
"""

POWERSHELL_TEMPLATE = """# PowerShell / pwsh completion script for mcp-mesh
# Usage:
#   Invoke-Expression (& mcp-mesh completion powershell)
# Or add to your PowerShell $PROFILE:
#   if (Get-Command mcp-mesh -ErrorAction SilentlyContinue) {
#       mcp-mesh completion powershell | Out-String | Invoke-Expression
#   }

Register-ArgumentCompleter -Native -CommandName mcp-mesh -ScriptBlock {
    param($wordToComplete, $commandAst, $cursorPosition)

    $commandElements = $commandAst.CommandElements
    $commands = @('run', 'stats', 'search', 'inspect', 'doctor', 'sse', 'monitor', 'demo', 'completion')
    $globalFlags = @('--help', '-h', '--version', '-v', '--demo', '-d')

    if ($commandElements.Count -le 2) {
        $subcommand = $commands | Where-Object { $_ -like "$wordToComplete*" }
        $flags = $globalFlags | Where-Object { $_ -like "$wordToComplete*" }
        $results = @($subcommand) + @($flags)
        $results | ForEach-Object {
            [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
        }
        return
    }

    $subcommand = $commandElements[1].Extent.Text
    $subcommandFlags = switch ($subcommand) {
        'run' { @('--config', '-c', '--mode', '-m', '--federate', '-f', '--serial-discovery', '--help', '-h') }
        'stats' { @('--config', '-c', '--federate', '-f', '--db', '--sql', '--help', '-h') }
        'search' { @('--limit', '-l', '--federate', '-f', '--help', '-h') }
        'inspect' { @('--help', '-h') }
        'doctor' { @('--config', '-c', '--help', '-h') }
        'sse' { @('--config', '-c', '--host', '-H', '--port', '-p', '--mode', '-m', '--token', '-t', '--cors-origin', '--insecure-no-auth', '--help', '-h') }
        'monitor' { @('--demo', '-d', '--iterations', '-n', '--interval', '-i', '--help', '-h') }
        'demo' { @('--help', '-h') }
        'completion' { @('bash', 'zsh', 'powershell', 'pwsh', '--help', '-h') }
        Default { @() }
    }

    $subcommandFlags | Where-Object { $_ -like "$wordToComplete*" } | ForEach-Object {
        [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_)
    }
}
"""


def generate_completion_script(shell: str) -> str:
    """Returns shell auto-completion script for the requested shell.

    Supported shells: 'bash', 'zsh', 'powershell', 'pwsh'.
    """
    normalized = shell.strip().lower()
    if normalized == "bash":
        return BASH_TEMPLATE
    elif normalized == "zsh":
        return ZSH_TEMPLATE
    elif normalized in ("powershell", "pwsh"):
        return POWERSHELL_TEMPLATE
    else:
        raise ValueError(
            f"Unsupported shell: {shell!r}. Supported shells are: 'bash', 'zsh', 'powershell', 'pwsh'."
        )

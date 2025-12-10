# Bash completion for update.py
# Install: source this file from ~/.bashrc or copy to /etc/bash_completion.d/

_update_py_completions() {
    local cur prev opts
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # All available options
    opts="--yes -y --no-backup --dry-run --skip-pull --preview -p --diff -d --changelog -c --help -h"

    # Handle --changelog argument (can take a number or version)
    if [[ "${prev}" == "--changelog" || "${prev}" == "-c" ]]; then
        # Suggest common values: numbers and recent version format
        COMPREPLY=( $(compgen -W "5 10 15 20 v0." -- "${cur}") )
        return 0
    fi

    # Complete options
    if [[ "${cur}" == -* ]]; then
        COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
        return 0
    fi

    # Default: suggest options
    COMPREPLY=( $(compgen -W "${opts}" -- "${cur}") )
    return 0
}

# Register completions for various ways the script might be called
complete -F _update_py_completions update.py
complete -F _update_py_completions ./update.py
complete -F _update_py_completions python3\ update.py

# Also support "python3 update.py" pattern
_python3_update_completions() {
    local cur prev words
    COMPREPLY=()
    cur="${COMP_WORDS[COMP_CWORD]}"
    prev="${COMP_WORDS[COMP_CWORD-1]}"

    # Check if we're completing after "python3 update.py"
    if [[ "${COMP_WORDS[1]}" == "update.py" ]]; then
        _update_py_completions
        return 0
    fi

    # Otherwise, use default python3 completion
    return 0
}

"""
Interactive terminal UI components.

Provides keyboard-navigable menus for CLI.
Uses arrow keys, W/S, or J/K for navigation.
"""

import sys
import subprocess
from typing import Any, Callable


# ANSI escape codes
CLEAR_LINE = "\033[2K"
MOVE_UP = "\033[A"
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
BOLD = "\033[1m"
RESET = "\033[0m"
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
DIM = "\033[2m"
REVERSE = "\033[7m"


def get_key() -> str:
    """Read a single keypress from terminal."""
    import termios
    import tty
    
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    
    try:
        tty.setraw(fd)
        ch = sys.stdin.read(1)
        
        # Handle escape sequences (arrow keys)
        if ch == '\x1b':
            ch2 = sys.stdin.read(1)
            if ch2 == '[':
                ch3 = sys.stdin.read(1)
                if ch3 == 'A':
                    return 'up'
                elif ch3 == 'B':
                    return 'down'
                elif ch3 == 'C':
                    return 'right'
                elif ch3 == 'D':
                    return 'left'
            return 'escape'
        
        # Handle common keys
        if ch == '\r' or ch == '\n':
            return 'enter'
        elif ch == ' ':
            return 'space'
        elif ch == '\x03':  # Ctrl+C
            return 'ctrl+c'
        elif ch == '\x04':  # Ctrl+D
            return 'ctrl+d'
        elif ch == 'q' or ch == 'Q':
            return 'quit'
        elif ch in ('w', 'W', 'k', 'K'):
            return 'up'
        elif ch in ('s', 'S', 'j', 'J'):
            return 'down'
        elif ch.isdigit():
            return ch
        else:
            return ch
            
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def clear_lines(n: int) -> None:
    """Clear n lines above cursor."""
    for _ in range(n):
        sys.stdout.write(MOVE_UP + CLEAR_LINE)
    sys.stdout.flush()


class InteractiveMenu:
    """
    Interactive menu with keyboard navigation.
    
    Controls:
        ↑/↓ or W/S or K/J: Navigate
        Enter or Space: Select
        Q or Escape: Cancel
        1-9: Quick select by number
    """
    
    def __init__(
        self,
        title: str,
        items: list[dict[str, Any]],
        show_details: bool = True,
    ):
        self.title = title
        self.items = items
        self.selected = 0
        self.show_details = show_details
    
    def render(self) -> int:
        """Render menu and return number of lines."""
        lines = []
        
        # Title
        lines.append(f"\n{BOLD}{self.title}{RESET}\n")
        lines.append(f"{DIM}{'─' * 60}{RESET}")
        lines.append(f"{DIM}  ↑/↓ navegar  •  Enter selecionar  •  Q cancelar{RESET}\n")
        
        # Items
        for i, item in enumerate(self.items):
            is_selected = i == self.selected
            
            # Selection indicator
            if is_selected:
                prefix = f"{GREEN}▸{RESET}"
                name_style = f"{BOLD}{GREEN}"
            else:
                prefix = " "
                name_style = f"{DIM}"
            
            # Number shortcut
            num = f"{DIM}[{i + 1}]{RESET}" if i < 9 else "   "
            
            # Item name
            name = item.get('name', item.get('value', ''))
            lines.append(f"  {prefix} {num} {name_style}{name}{RESET}")
            
            # Description (only for selected)
            if is_selected and self.show_details:
                desc = item.get('description', '')
                if desc:
                    lines.append(f"      {CYAN}{desc}{RESET}")
                
                features = item.get('features', [])
                if features:
                    for feat in features[:4]:
                        lines.append(f"      {DIM}• {feat}{RESET}")
                
                recommended = item.get('recommended_for', '')
                if recommended:
                    lines.append(f"      {YELLOW}Best for: {recommended}{RESET}")
        
        lines.append("")
        
        # Print all lines
        output = "\n".join(lines)
        print(output)
        
        return len(lines)
    
    def run(self) -> dict[str, Any] | None:
        """Run interactive menu and return selected item."""
        print(HIDE_CURSOR, end="")
        
        try:
            lines_rendered = self.render()
            
            while True:
                key = get_key()
                
                if key == 'up':
                    self.selected = (self.selected - 1) % len(self.items)
                elif key == 'down':
                    self.selected = (self.selected + 1) % len(self.items)
                elif key in ('enter', 'space'):
                    print(SHOW_CURSOR, end="")
                    return self.items[self.selected]
                elif key in ('quit', 'escape', 'ctrl+c', 'ctrl+d'):
                    print(SHOW_CURSOR, end="")
                    print()
                    return None
                elif key.isdigit() and 1 <= int(key) <= len(self.items):
                    self.selected = int(key) - 1
                    print(SHOW_CURSOR, end="")
                    return self.items[self.selected]
                else:
                    continue
                
                # Re-render
                clear_lines(lines_rendered)
                lines_rendered = self.render()
                
        except Exception:
            print(SHOW_CURSOR, end="")
            raise


class InteractiveInput:
    """Interactive input with suggestions."""
    
    def __init__(
        self,
        prompt: str,
        suggestions: list[str] | None = None,
        default: str = "",
        validator: Callable | None = None,
    ):
        self.prompt = prompt
        self.suggestions = suggestions or []
        self.default = default
        self.validator = validator
        self.selected_suggestion = 0
    
    def run(self) -> str | None:
        """Run input and return value."""
        if self.suggestions:
            return self._run_with_suggestions()
        else:
            return self._run_simple()
    
    def _run_simple(self) -> str | None:
        """Simple input without suggestions."""
        try:
            default_hint = f" [{self.default}]" if self.default else ""
            value = input(f"{CYAN}{self.prompt}{default_hint}: {RESET}").strip()
            return value or self.default
        except (KeyboardInterrupt, EOFError):
            print()
            return None
    
    def _run_with_suggestions(self) -> str | None:
        """Input with navigable suggestions."""
        print(HIDE_CURSOR, end="")
        
        try:
            lines = self._render_suggestions()
            
            while True:
                key = get_key()
                
                if key == 'up':
                    self.selected_suggestion = (self.selected_suggestion - 1) % len(self.suggestions)
                elif key == 'down':
                    self.selected_suggestion = (self.selected_suggestion + 1) % len(self.suggestions)
                elif key in ('enter', 'space'):
                    print(SHOW_CURSOR, end="")
                    return self.suggestions[self.selected_suggestion]
                elif key in ('quit', 'escape'):
                    print(SHOW_CURSOR, end="")
                    print()
                    return None
                elif key == 'ctrl+c' or key == 'ctrl+d':
                    print(SHOW_CURSOR, end="")
                    print()
                    return None
                elif key.isdigit() and 1 <= int(key) <= len(self.suggestions):
                    print(SHOW_CURSOR, end="")
                    return self.suggestions[int(key) - 1]
                elif key == 'c' or key == 'C':
                    # Custom input
                    print(SHOW_CURSOR, end="")
                    clear_lines(lines)
                    try:
                        custom = input(f"{CYAN}Digite a versão do Python: {RESET}").strip()
                        return custom if custom else None
                    except (KeyboardInterrupt, EOFError):
                        return None
                else:
                    continue
                
                clear_lines(lines)
                lines = self._render_suggestions()
                
        except Exception:
            print(SHOW_CURSOR, end="")
            raise
    
    def _render_suggestions(self) -> int:
        """Render suggestions list."""
        lines = []
        
        lines.append(f"\n{BOLD}{self.prompt}{RESET}")
        lines.append(f"{DIM}  ↑/↓ navegar  •  Enter selecionar  •  C digitar custom{RESET}\n")
        
        for i, suggestion in enumerate(self.suggestions):
            is_selected = i == self.selected_suggestion
            
            if is_selected:
                prefix = f"{GREEN}▸{RESET}"
                style = f"{BOLD}{GREEN}"
            else:
                prefix = " "
                style = DIM
            
            num = f"{DIM}[{i + 1}]{RESET}" if i < 9 else "   "
            lines.append(f"  {prefix} {num} {style}{suggestion}{RESET}")
        
        lines.append("")
        
        output = "\n".join(lines)
        print(output)
        
        return len(lines)


def get_installed_python_versions() -> list[str]:
    """Get list of Python versions installed via uv."""
    try:
        result = subprocess.run(
            ["uv", "python", "list", "--only-installed"],
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            return []
        
        versions = []
        for line in result.stdout.strip().split("\n"):
            if line.strip():
                # Parse version from output like "cpython-3.12.0-linux-x86_64-gnu"
                parts = line.strip().split()
                if parts:
                    version_str = parts[0]
                    # Extract version number
                    if "cpython-" in version_str:
                        ver = version_str.replace("cpython-", "").split("-")[0]
                        if ver not in versions:
                            versions.append(ver)
                    elif version_str[0].isdigit():
                        versions.append(version_str.split()[0])
        
        return sorted(versions, reverse=True)
        
    except FileNotFoundError:
        return []
    except Exception:
        return []


def get_available_python_versions() -> list[str]:
    """Get list of Python versions available to install via uv."""
    try:
        result = subprocess.run(
            ["uv", "python", "list"],
            capture_output=True,
            text=True,
        )
        
        if result.returncode != 0:
            return ["3.12", "3.11", "3.10", "3.9"]
        
        versions = set()
        for line in result.stdout.strip().split("\n"):
            if line.strip() and "cpython" in line.lower():
                parts = line.strip().split()
                if parts:
                    version_str = parts[0]
                    if "cpython-" in version_str:
                        ver = version_str.replace("cpython-", "").split("-")[0]
                        # Only major.minor
                        major_minor = ".".join(ver.split(".")[:2])
                        versions.add(major_minor)
        
        # Sort by version number (3.12 > 3.11 > 3.10)
        def version_key(v: str) -> tuple:
            try:
                parts = v.split(".")
                return tuple(int(p) for p in parts)
            except ValueError:
                return (0, 0)
        
        sorted_versions = sorted(versions, key=version_key, reverse=True)
        
        # Filter to stable versions (3.9 - 3.13)
        stable = [v for v in sorted_versions if v in ("3.13", "3.12", "3.11", "3.10", "3.9")]
        
        return stable if stable else sorted_versions[:6]
        
    except FileNotFoundError:
        return ["3.12", "3.11", "3.10", "3.9"]
    except Exception:
        return ["3.12", "3.11", "3.10", "3.9"]


def interactive_project_setup() -> dict[str, Any] | None:
    """
    Run full interactive project setup wizard.
    
    Returns dict with:
        - project_name: str
        - template: str
        - python_version: str
    
    Or None if cancelled.
    """
    from core.cli.templates import list_available_templates, get_template_metadata
    
    print(f"\n{BOLD}🚀 Core Framework - New Project Wizard{RESET}\n")
    print(f"{DIM}{'─' * 50}{RESET}")
    
    # Step 1: Project name
    print(f"\n{BOLD}Step 1/3: Project Name{RESET}")
    try:
        name = input(f"{CYAN}Nome do projeto [myproject]: {RESET}").strip()
        project_name = name or "myproject"
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return None
    
    # Validate project name
    if not project_name.replace("_", "").replace("-", "").isalnum():
        print(f"{YELLOW}Warning: Project name should be alphanumeric{RESET}")
    
    print(f"{GREEN}✓ Project: {project_name}{RESET}")
    
    # Step 2: Template selection
    print(f"\n{BOLD}Step 2/3: Select Template{RESET}")
    
    templates = list_available_templates()
    template_items = []
    for name in templates:
        meta = get_template_metadata(name)
        template_items.append({
            "value": name,
            "name": meta["name"],
            "description": meta["description"],
            "features": meta.get("features", []),
            "recommended_for": meta.get("recommended_for", ""),
        })
    
    menu = InteractiveMenu(
        title="📦 Select Template",
        items=template_items,
        show_details=True,
    )
    
    selected_template = menu.run()
    if selected_template is None:
        print("Cancelled.")
        return None
    
    template_name = selected_template["value"]
    print(f"\n{GREEN}✓ Template: {selected_template['name']}{RESET}")
    
    # Step 3: Python version
    print(f"\n{BOLD}Step 3/3: Python Version{RESET}")
    
    installed = get_installed_python_versions()
    
    if installed:
        print(f"{DIM}Installed versions found:{RESET}")
        
        # Add option to install new version
        version_items = []
        for ver in installed[:5]:
            version_items.append(ver)
        
        version_input = InteractiveInput(
            prompt="🐍 Select Python Version",
            suggestions=version_items,
            default=installed[0] if installed else "3.12",
        )
        
        python_version = version_input.run()
        if python_version is None:
            print("Cancelled.")
            return None
    else:
        print(f"{YELLOW}No Python versions found via uv.{RESET}")
        available = get_available_python_versions()
        
        if available:
            version_input = InteractiveInput(
                prompt="🐍 Select Python Version to Install",
                suggestions=available[:5],
                default="3.12",
            )
            
            python_version = version_input.run()
            if python_version is None:
                print("Cancelled.")
                return None
        else:
            try:
                python_version = input(f"{CYAN}Python version [3.12]: {RESET}").strip() or "3.12"
            except (KeyboardInterrupt, EOFError):
                print("\nCancelled.")
                return None
    
    print(f"{GREEN}✓ Python: {python_version}{RESET}")
    
    # Confirmation
    print(f"\n{DIM}{'─' * 50}{RESET}")
    print(f"\n{BOLD}📋 Summary:{RESET}")
    print(f"   Project:  {CYAN}{project_name}{RESET}")
    print(f"   Template: {CYAN}{selected_template['name']}{RESET}")
    print(f"   Python:   {CYAN}{python_version}{RESET}")
    print()
    
    try:
        confirm = input(f"{CYAN}Create project? [Y/n]: {RESET}").strip().lower()
        if confirm == 'n':
            print("Cancelled.")
            return None
    except (KeyboardInterrupt, EOFError):
        print("\nCancelled.")
        return None
    
    return {
        "project_name": project_name,
        "template": template_name,
        "python_version": python_version,
    }


# Fallback for non-TTY environments
def is_interactive() -> bool:
    """Check if running in interactive terminal."""
    return sys.stdin.isatty() and sys.stdout.isatty()

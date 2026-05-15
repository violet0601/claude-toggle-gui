#!/usr/bin/env python3
"""Claude Code Skill & MCP Toggle Tool - GUI"""

import json
import re
import shutil
import tomllib
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

HOME = Path.home()
CLAUDE_BASE = HOME / ".claude"
CODEX_BASE = HOME / ".codex"
MARKETPLACE = CLAUDE_BASE / "plugins" / "marketplaces" / "claude-plugins-official"

GROUPS = [
    ("Skills", CLAUDE_BASE / "skills", CLAUDE_BASE / "skills-disabled"),
    ("Plugins", MARKETPLACE / "plugins", MARKETPLACE / "plugins-disabled"),
    ("MCP Tools", MARKETPLACE / "external_plugins", MARKETPLACE / "external_plugins-disabled"),
]

# (label, config_path, config_type)
MCP_SOURCES = [
    ("Codex TOML", CODEX_BASE / "config.toml", "toml"),
    ("User Settings", CLAUDE_BASE / "settings.json", "json"),
    ("User .mcp.json", HOME / ".mcp.json", "json"),
]


def get_item_info(path):
    plugin_json = path / ".claude-plugin" / "plugin.json"
    if plugin_json.exists():
        try:
            data = json.loads(plugin_json.read_text(encoding="utf-8"))
            name = data.get("name", path.name)
            desc = data.get("description", "")[:50]
            return name, desc
        except Exception:
            pass
    skill_md = path / "SKILL.md"
    if skill_md.exists():
        try:
            content = skill_md.read_text(encoding="utf-8")
            for line in content.splitlines():
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("---"):
                    return path.name, line[:50]
        except Exception:
            pass
    return path.name, ""


def load_mcp_servers():
    """Scan all MCP config sources and return {server_name: {config, source_path, scope, enabled, type}}."""
    servers = {}

    for scope, config_path, cfg_type in MCP_SOURCES:
        if not config_path.exists():
            continue

        try:
            content = config_path.read_text(encoding="utf-8")

            if cfg_type == "json":
                _load_json_mcp(content, config_path, scope, servers)
            elif cfg_type == "toml":
                _load_toml_mcp(content, config_path, scope, servers)
        except Exception:
            pass

    return servers


def _load_json_mcp(content, config_path, scope, servers):
    data = json.loads(content)
    for key in ("mcpServers", "mcpServers-disabled"):
        if key in data and isinstance(data[key], dict):
            for name, cfg in data[key].items():
                if isinstance(cfg, dict):
                    servers[name] = {
                        "name": name,
                        "config": cfg,
                        "source": config_path,
                        "scope": scope,
                        "enabled": key == "mcpServers",
                        "config_type": "json",
                    }


def _load_toml_mcp(content, config_path, scope, servers):
    data = tomllib.loads(content)
    mcp_servers = data.get("mcp_servers", {})
    if not isinstance(mcp_servers, dict):
        return
    for name, cfg in mcp_servers.items():
        if isinstance(cfg, dict):
            enabled = cfg.get("enabled", True)
            servers[name] = {
                "name": name,
                "config": cfg,
                "source": config_path,
                "scope": scope,
                "enabled": enabled,
                "config_type": "toml",
            }


def save_mcp_server(server_info, enable):
    """Toggle a single MCP server in its source config file."""
    config_path = server_info["source"]
    cfg_type = server_info.get("config_type", "json")
    name = server_info["name"]

    if cfg_type == "json":
        return _save_json_mcp(config_path, name, enable)
    elif cfg_type == "toml":
        return _save_toml_mcp(config_path, name, enable)
    return False


def _save_json_mcp(config_path, name, enable):
    try:
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception:
        return False

    src_key = "mcpServers-disabled" if enable else "mcpServers"
    dst_key = "mcpServers" if enable else "mcpServers-disabled"

    if src_key not in data or name not in data[src_key]:
        return False

    entry = data[src_key].pop(name)
    data.setdefault(dst_key, {})[name] = entry

    try:
        config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return True
    except Exception:
        return False


def _save_toml_mcp(config_path, name, enable):
    try:
        content = config_path.read_text(encoding="utf-8")
    except Exception:
        return False

    header = f"[mcp_servers.{name}]"
    header_idx = content.find(header)
    if header_idx < 0:
        return False

    # Find the section end (next [section] or EOF)
    rest = content[header_idx:]
    next_section = re.search(r"\n\[(?![^\[]*\])", rest)
    if next_section:
        section_end = header_idx + next_section.start()
    else:
        section_end = len(content)

    section = content[header_idx:section_end]

    # Toggle the enabled line
    old_line = f"enabled = {str(not enable).lower()}"
    new_line = f"enabled = {str(enable).lower()}"

    if old_line in section:
        new_section = section.replace(old_line, new_line, 1)
    else:
        # If there's no enabled line, add one before the section ends
        new_section = section.rstrip() + f"\nenabled = {str(enable).lower()}\n"

    new_content = content[:header_idx] + new_section + content[section_end:]

    try:
        config_path.write_text(new_content, encoding="utf-8")
        return True
    except Exception:
        return False


class ToggleApp:
    def __init__(self):
        self.win = tk.Tk()
        self.win.title("Claude Code Skills & MCP 开关管理")
        self.win.geometry("750x650")
        self.win.resizable(True, True)
        self.win.configure(bg="#1e1e1e")

        self.vars = {}
        self.mcp_servers = {}

        self._build_ui()
        self._load_items()

    def _build_ui(self):
        top = tk.Frame(self.win, bg="#2d2d2d", height=36)
        top.pack(fill=tk.X, side=tk.TOP)
        tk.Label(top, text="Claude Code 开关管理", bg="#2d2d2d", fg="#cccccc",
                 font=("Microsoft YaHei UI", 11)).pack(side=tk.LEFT, padx=12, pady=6)
        self.count_label = tk.Label(top, text="", bg="#2d2d2d", fg="#888888",
                                    font=("Microsoft YaHei UI", 9))
        self.count_label.pack(side=tk.RIGHT, padx=12, pady=6)

        self.canvas = tk.Canvas(self.win, bg="#1e1e1e", highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self.win, orient=tk.VERTICAL, command=self.canvas.yview)
        self.frame = tk.Frame(self.canvas, bg="#1e1e1e")

        self.frame.bind("<Configure>", lambda _: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.frame, anchor=tk.NW, tags="inner")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        def on_mousewheel(event):
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.canvas.bind_all("<MouseWheel>", on_mousewheel)

        bottom = tk.Frame(self.win, bg="#2d2d2d", height=32)
        bottom.pack(fill=tk.X, side=tk.BOTTOM)
        tk.Label(bottom, text="改动后需重启 Claude Code 生效", bg="#2d2d2d", fg="#666666",
                 font=("Microsoft YaHei UI", 8)).pack(side=tk.LEFT, padx=12, pady=6)

    def _add_section_header(self, text):
        hf = tk.Frame(self.frame, bg="#2d2d2d")
        hf.pack(fill=tk.X, padx=0, pady=(8, 2))
        tk.Label(hf, text=f"  {text}", bg="#2d2d2d", fg="#e0e0e0",
                 font=("Microsoft YaHei UI", 10, "bold")).pack(side=tk.LEFT, padx=12, pady=5)

    def _add_empty_label(self):
        tk.Label(self.frame, text="  (空)", bg="#1e1e1e", fg="#555555",
                 font=("Microsoft YaHei UI", 9)).pack(anchor=tk.W, padx=28)

    def _load_items(self):
        for widget in self.frame.winfo_children():
            widget.destroy()
        self.vars.clear()
        self.mcp_servers.clear()

        # Marketplace groups
        for group_name, en_dir, dis_dir in GROUPS:
            self._add_section_header(group_name)
            total = 0
            if en_dir.exists():
                for item in sorted(en_dir.iterdir()):
                    if item.is_dir() and not item.name.startswith("."):
                        self._add_row(item, group_name, en_dir, dis_dir, True)
                        total += 1
            if dis_dir.exists():
                for item in sorted(dis_dir.iterdir()):
                    if item.is_dir() and not item.name.startswith("."):
                        self._add_row(item, group_name, en_dir, dis_dir, False)
                        total += 1
            if total == 0:
                self._add_empty_label()

        # User MCP group (from config files)
        self._add_section_header("User MCP (来自配置文件)")
        self.mcp_servers = load_mcp_servers()
        if self.mcp_servers:
            for name in sorted(self.mcp_servers.keys()):
                self._add_mcp_row(name)
        else:
            self._add_empty_label()

        self._update_count()

    def _add_row(self, item_path, group_name, en_dir, dis_dir, enabled):
        name, desc = get_item_info(item_path)
        key = f"{group_name}|{name}"

        var = tk.BooleanVar(value=enabled)
        info = {
            "path": item_path,
            "en_dir": en_dir,
            "dis_dir": dis_dir,
            "name": name,
            "group": group_name,
        }
        self.vars[key] = (var, info)

        row = tk.Frame(self.frame, bg="#1e1e1e", height=34)
        row.pack(fill=tk.X, padx=8, pady=1)

        cb = tk.Checkbutton(
            row, text="", variable=var,
            command=lambda k=key: self._toggle(k),
            bg="#1e1e1e", fg="#e0e0e0",
            selectcolor="#1e1e1e", activebackground="#2a2a2a",
            activeforeground="#e0e0e0",
            font=("Microsoft YaHei UI", 10),
        )
        cb.pack(side=tk.LEFT, padx=(12, 6))

        status = "✓" if enabled else "—"
        fg = "#d4d4d4" if enabled else "#666666"
        tk.Label(row, text=f"{status}  {name}", bg="#1e1e1e", fg=fg,
                 font=("Microsoft YaHei UI", 10), anchor=tk.W, width=26).pack(side=tk.LEFT)

        if desc:
            tk.Label(row, text=desc, bg="#1e1e1e", fg="#666666",
                     font=("Microsoft YaHei UI", 9), anchor=tk.W).pack(side=tk.LEFT, padx=8)

    def _add_mcp_row(self, name):
        info = self.mcp_servers[name]
        enabled = info["enabled"]
        cfg = info["config"]
        scope = info["scope"]

        cmd = cfg.get("command", "")
        mcp_type = cfg.get("type", "stdio")
        desc = f"{mcp_type}: {Path(cmd).name}" if cmd else mcp_type

        key = f"User MCP|{name}"
        var = tk.BooleanVar(value=enabled)
        self.vars[key] = (var, info)

        row = tk.Frame(self.frame, bg="#1e1e1e", height=34)
        row.pack(fill=tk.X, padx=8, pady=1)

        cb = tk.Checkbutton(
            row, text="", variable=var,
            command=lambda k=key: self._toggle_mcp(k),
            bg="#1e1e1e", fg="#e0e0e0",
            selectcolor="#1e1e1e", activebackground="#2a2a2a",
            activeforeground="#e0e0e0",
            font=("Microsoft YaHei UI", 10),
        )
        cb.pack(side=tk.LEFT, padx=(12, 6))

        status = "✓" if enabled else "—"
        fg = "#d4d4d4" if enabled else "#666666"
        tk.Label(row, text=f"{status}  {name}", bg="#1e1e1e", fg=fg,
                 font=("Microsoft YaHei UI", 10), anchor=tk.W, width=20).pack(side=tk.LEFT)

        tk.Label(row, text=desc, bg="#1e1e1e", fg="#888888",
                 font=("Microsoft YaHei UI", 9), anchor=tk.W).pack(side=tk.LEFT, padx=4)

        tk.Label(row, text=f"[{scope}]", bg="#1e1e1e", fg="#555555",
                 font=("Microsoft YaHei UI", 8), anchor=tk.W).pack(side=tk.LEFT)

    def _toggle(self, key):
        var, info = self.vars[key]
        en_dir = info["en_dir"]
        dis_dir = info["dis_dir"]

        if var.get():
            src = dis_dir
            dst = en_dir
        else:
            src = en_dir
            dst = dis_dir

        dst.mkdir(parents=True, exist_ok=True)
        src_item = src / info["name"]
        dst_item = dst / info["name"]
        if dst_item.exists():
            shutil.rmtree(dst_item)
        if src_item.exists():
            shutil.move(str(src_item), str(dst_item))
        info["path"] = dst_item
        self._update_count()

    def _toggle_mcp(self, key):
        var, info = self.vars[key]
        success = save_mcp_server(info, var.get())
        if not success:
            messagebox.showerror(
                "错误",
                f"无法修改 MCP 配置文件:\n{info['source']}\n\n请检查文件权限或配置格式。"
            )
            var.set(not var.get())
        else:
            info["enabled"] = var.get()
        self._update_count()

    def _update_count(self):
        total = len(self.vars)
        enabled = sum(1 for var, _ in self.vars.values() if var.get())
        self.count_label.config(text=f"{enabled}/{total} 已启用")


def main():
    app = ToggleApp()
    app.win.mainloop()


if __name__ == "__main__":
    main()

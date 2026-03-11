from __future__ import annotations

import subprocess

from screenmemory.config import ScreenMemoryConfig


def launch_agent_plist(config: ScreenMemoryConfig, project_root: str) -> str:
    # The launch agent runs a short indexing pass every 2 minutes.
    # It does not watch files continuously, which keeps memory use small.
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.alanman.screenmemoryrag</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/uv</string>
        <string>run</string>
        <string>--directory</string>
        <string>{project_root}</string>
        <string>screenmemory</string>
        <string>index</string>
        <string>--recent-days</string>
        <string>{config.default_recent_days}</string>
        <string>--batch-limit</string>
        <string>50</string>
    </array>
    <key>StartInterval</key>
    <integer>120</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{config.log_dir / "launchd.out.log"}</string>
    <key>StandardErrorPath</key>
    <string>{config.log_dir / "launchd.err.log"}</string>
</dict>
</plist>
"""


def install_launch_agent(config: ScreenMemoryConfig, project_root: str) -> str:
    plist_contents = launch_agent_plist(config, project_root)
    config.launch_agent_path.write_text(plist_contents, encoding="utf-8")
    subprocess.run(
        ["launchctl", "unload", str(config.launch_agent_path)],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["launchctl", "load", str(config.launch_agent_path)],
        check=True,
    )
    return str(config.launch_agent_path)


def full_index_launch_agent_plist(
    config: ScreenMemoryConfig,
    project_root: str,
    batch_limit: int,
    skip_embeddings: bool,
    batch_embeddings: bool,
) -> str:
    # This launch agent repeatedly runs the next full-index chunk until the cursor reaches the end.
    extra_args = ""
    if skip_embeddings:
        extra_args = "        <string>--skip-embeddings</string>\n"
    elif batch_embeddings:
        extra_args = "        <string>--batch-embeddings</string>\n"

    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>io.alanman.screenmemoryrag.fullindex</string>
    <key>ProgramArguments</key>
    <array>
        <string>/opt/homebrew/bin/uv</string>
        <string>run</string>
        <string>--directory</string>
        <string>{project_root}</string>
        <string>screenmemory</string>
        <string>index-everything</string>
        <string>--batch-limit</string>
        <string>{batch_limit}</string>
        <string>--stop-agent-when-done</string>
{extra_args}    </array>
    <key>StartInterval</key>
    <integer>120</integer>
    <key>RunAtLoad</key>
    <true/>
    <key>StandardOutPath</key>
    <string>{config.log_dir / "full-index.out.log"}</string>
    <key>StandardErrorPath</key>
    <string>{config.log_dir / "full-index.err.log"}</string>
</dict>
</plist>
"""


def install_full_index_launch_agent(
    config: ScreenMemoryConfig,
    project_root: str,
    batch_limit: int,
    skip_embeddings: bool,
    batch_embeddings: bool,
) -> str:
    plist_contents = full_index_launch_agent_plist(
        config=config,
        project_root=project_root,
        batch_limit=batch_limit,
        skip_embeddings=skip_embeddings,
        batch_embeddings=batch_embeddings,
    )
    config.full_index_launch_agent_path.write_text(plist_contents, encoding="utf-8")
    subprocess.run(
        ["launchctl", "unload", str(config.full_index_launch_agent_path)],
        check=False,
        capture_output=True,
    )
    subprocess.run(
        ["launchctl", "load", str(config.full_index_launch_agent_path)],
        check=True,
    )
    return str(config.full_index_launch_agent_path)


def remove_launch_agent(config: ScreenMemoryConfig) -> str:
    subprocess.run(
        ["launchctl", "unload", str(config.launch_agent_path)],
        check=False,
        capture_output=True,
    )
    config.launch_agent_path.unlink(missing_ok=True)
    return str(config.launch_agent_path)


def remove_full_index_launch_agent(config: ScreenMemoryConfig) -> str:
    subprocess.run(
        ["launchctl", "unload", str(config.full_index_launch_agent_path)],
        check=False,
        capture_output=True,
    )
    config.full_index_launch_agent_path.unlink(missing_ok=True)
    return str(config.full_index_launch_agent_path)

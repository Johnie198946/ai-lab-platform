"""Hermes native no-agent retry adapter. No LLM and no Wiki writes.

Install under the default profile scripts directory; schedule once per minute.
The existing six-hour Writer remains the only compiler and recovery fallback.
"""
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path.home() / '.hermes/hermes-agent'))


def main():
    from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
    from hermes_cli.config import get_hermes_home
    ctx = PluginContext(PluginManifest(name='ai-lab-capabilities'), PluginManager())
    cfg = ctx.get_config('research_deposit', {})
    if (ctx.profile_name != 'default' or cfg.get('enabled') is not True
            or cfg.get('writer_events_enabled') is not True
            or cfg.get('deployment_mode') != 'local_single_tenant'
            or os.environ.get('AI_LAB_AGENT_OS_MODE') == 'cloud_multi_tenant'):
        return
    path = Path(get_hermes_home()) / 'plugins/ai-lab-capabilities/writer_events.py'
    spec = importlib.util.spec_from_file_location('native_writer_events', path)
    if spec is None or spec.loader is None:
        raise RuntimeError('writer_events_module_unavailable')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    result = module.drain(ctx.state.data_dir / 'writer-events.sqlite3', cfg['writer_job_id'])
    if result['state'] not in ('idle', 'paused_or_disabled'):
        print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()

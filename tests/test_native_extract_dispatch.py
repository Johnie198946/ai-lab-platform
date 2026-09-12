"""Real Hermes dispatch/cache/hooks with synthetic HTTP and an isolated home."""
import os
from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
HERMES = Path(os.environ.get("HERMES_SOURCE", str(Path.home() / ".hermes/hermes-agent")))


def test_native_dispatch_hooks_cache_and_scope(tmp_path):
    if not (HERMES / "model_tools.py").is_file():
        pytest.skip("Requires Hermes source")
    code = r'''
import importlib.util, json, sys
from pathlib import Path
from unittest.mock import patch, AsyncMock
import httpx
import yaml
home, source = map(Path, sys.argv[1:])
(home / 'config.yaml').write_text(yaml.safe_dump({
    'web': {'extract_backend': 'ai-lab-native'},
    'plugins': {'entries': {'ai-lab-capabilities': {'settings': {
        'research_deposit': {'enabled': False, 'deployment_mode': 'cloud_multi_tenant'}
    }}}}
}))
from hermes_cli import plugins
from hermes_cli.plugins import PluginContext, PluginManager, PluginManifest
manager = PluginManager()
manager._discovered = True
with patch.object(plugins, 'get_plugin_manager', return_value=manager):
    import model_tools
    from tools import web_tools, url_safety, website_policy
    spec = importlib.util.spec_from_file_location('dispatch_fixture_plugin', source / '__init__.py', submodule_search_locations=[str(source)])
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    ctx = PluginContext(PluginManifest(name='ai-lab-capabilities'), manager)
    module.register(ctx)
    router = sys.modules[spec.name + '.capability_router']
    seen, observed = [], []
    ctx.register_hook('post_tool_call', lambda **kw: observed.append(kw))
    client = httpx.Client
    def transport(req):
        seen.append(str(req.url))
        if req.url.path == '/start':
            return httpx.Response(302, headers={'location': '/final'})
        if req.url.path == '/fail':
            return httpx.Response(429, headers={'content-type': 'text/html'}, text='<html>not evidence</html>')
        return httpx.Response(200, headers={'content-type': 'text/plain'}, text='Synthetic evidence ' + req.url.path)
    with patch.object(httpx, 'Client', side_effect=lambda **kw: client(transport=httpx.MockTransport(transport), **kw)), \
         patch.object(web_tools, 'async_is_safe_url', new=AsyncMock(return_value=True)), \
         patch.object(url_safety, 'is_safe_url', return_value=True), \
         patch.object(website_policy, 'check_website_access', return_value=None):
        for scope in ({'turn_id':'synthetic-turn', 'task_id':'synthetic-task', 'session_id':'synthetic-session'},
                      {'task_id':'synthetic-no-session-or-turn'}):
            key = scope.get('turn_id') or scope['task_id']
            base = 'https://example.org'
            manager.invoke_hook('pre_llm_call', user_message='研究 ' + base, **scope)
            def call(paths, wrapped=False):
                args = {'urls': [base + path for path in paths]}
                name = 'web_extract'
                if wrapped:
                    name, args = 'tool_call', {'name': name, 'arguments': args}
                raw = model_tools.handle_function_call(name, args, enabled_toolsets=['web'], **scope)
                return json.loads(raw)
            first = call(['/start', '/fail'])
            assert first['results'][0]['content'].startswith('Synthetic evidence'), first
            assert first['results'][1]['error'], first
            assert router._WEB_RESEARCH_TURNS[key][base + '/start'] == 'success'
            assert router._WEB_RESEARCH_TURNS[key][base + '/fail'] == 'failed'
            count = seen.count(base + '/start')
            # This SDK keeps web_extract non-deferrable; its bridge must reject
            # it before execution without poisoning the already successful URL.
            bridge = call(['/start'], wrapped=True)
            assert 'not a deferrable tool' in bridge['error'], bridge
            assert router._WEB_RESEARCH_TURNS[key][base + '/start'] == 'success'
            repeat = call(['/start', '/fresh'])
            assert 'results' in repeat, repeat
            assert all(row['content'] for row in repeat['results']), repeat
            assert seen.count(base + '/start') == count, 'successful URL must reuse real core cache'
            assert router._WEB_RESEARCH_TURNS[key][base + '/fresh'] == 'success'
            fail_count = seen.count(base + '/fail')
            denied = call(['/fail'])
            assert denied.get('error'), denied
            assert seen.count(base + '/fail') == fail_count
            # Real model_tools observer receives JSON before conversation wrapping.
            posts = [p for p in observed if p['tool_name'] == 'web_extract']
            assert posts and all(isinstance(json.loads(p['result']), dict) for p in posts)
            assert all(p.get('task_id') == scope['task_id'] for p in posts[-3:])
    manager.unload()
print('NATIVE_DISPATCH_CACHE_HOOKS_OK')
'''
    env = dict(os.environ, HOME=str(tmp_path), HERMES_HOME=str(tmp_path),
               AI_LAB_AGENT_OS_MODE="cloud_multi_tenant",
               PYTHONPATH=str(HERMES))
    completed = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path),
         str(ROOT / "agency/hermes-plugins/ai-lab-capabilities")],
        cwd=tmp_path, env=env, text=True, capture_output=True, timeout=90,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert "NATIVE_DISPATCH_CACHE_HOOKS_OK" in completed.stdout

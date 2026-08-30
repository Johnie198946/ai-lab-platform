import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { chmodSync, existsSync, mkdirSync, mkdtempSync, readFileSync, realpathSync, rmSync, symlinkSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = new URL('../public/showroom/', import.meta.url);
const html = readFileSync(new URL('index.html', root), 'utf8');
const script = readFileSync(new URL('showroom-journey.js', root), 'utf8');
const updateScript = readFileSync(new URL('../../scripts/update.sh', import.meta.url), 'utf8');
const deployExactScript = readFileSync(new URL('../../scripts/deploy_exact_sha.sh', import.meta.url), 'utf8');
const linkVaultScriptUrl = new URL('../../scripts/link_release_vault.sh', import.meta.url);
const backendDockerfile = readFileSync(new URL('../../backend/Dockerfile', import.meta.url), 'utf8');

test('new default entry is isolated from the legacy nine-screen app', () => {
  assert.match(html, /showroom-journey\.js/);
  assert.doesNotMatch(html, /app\.js/);
  assert.match(readFileSync(new URL('legacy.html', root), 'utf8'), /app\.js/);
});

test('journey defines S0 through S10 and the five evidence contract fields', () => {
  for (let index = 0; index <= 10; index += 1) assert.match(script, new RegExp(`['"]S${index}['"]`));
  for (const field of ['customerQuestion', 'screenGoal', 'coreArtifact', 'chat', 'agentDesign', 'businessSystemNeed', 'tokenFactoryFeature', 'hardwareCommercialValue', 'evidenceStatus']) {
    assert.match(script, new RegExp(field));
  }
});

test('CustomerDemand API is server-backed and the approved panorama is present', () => {
  assert.match(script, /\/api\/v1\/demands/);
  assert.match(script, /POST|PATCH/);
  assert.match(script, /\/confirm/);
  assert.ok(existsSync(new URL('assets/manufacturing-panorama.png', root)));
  assert.doesNotMatch(script, /localStorage\.setItem\([^)]*demand/i);
  assert.doesNotMatch(script, /LIVE[^\n]*(台|卡|%)/);
});

test('S3 and S4 use structured demand fields and the shared showroom API', () => {
  for (const field of ['business_scene', 'overall_goal', 'stakeholders', 'requirement_items', 'conflict_notes', 'constraints', 'acceptance_criteria']) {
    assert.match(script, new RegExp(field));
  }
  assert.match(script, /window\.showroomApi\.init\(\)/);
  assert.match(script, /window\.showroomApi\.submitHermesPrompt/);
  assert.match(html, /showroom-api\.js/);
  assert.doesNotMatch(script, /JsonRpcGatewayClient/);
});

test('immutable deployment audits the release before switching the live symlink', () => {
  const migration = updateScript.indexOf('python scripts/migrate_quantum_workspace.py');
  const restart = updateScript.indexOf(
    'docker compose -p "$COMPOSE_PROJECT" up -d --build',
    migration,
  );
  const health = updateScript.indexOf('if [ -z "$status" ]');
  const runtimeDirs = updateScript.indexOf('mkdir -p data/manifests data/runtime');
  const matrixLink = updateScript.indexOf('ln -s vault/knowledge_matrix.json data/knowledge_matrix.json');
  const audit = updateScript.indexOf('audit_runtime_contracts.py');
  const marker = updateScript.indexOf('> .deployed-sha');
  const cleanupTrap = updateScript.indexOf('trap cleanup EXIT');
  const tarballAllocation = updateScript.indexOf('TARBALL="$(mktemp');
  const releaseAllocation = updateScript.indexOf('RELEASE_DIR="$(allocate_release_dir');
  const switchLink = updateScript.indexOf('mv -Tf "$LINK_TMP" "$APP_LINK"');
  const vaultLinks = updateScript.indexOf(
    'bash scripts/link_release_vault.sh "$RELEASE_DIR" "$RELEASE_ROOT" "$VAULT_ROOT"',
  );
  const runtimeRestart = updateScript.indexOf('restart_hermes_runtime', switchLink);
  const bridgeRestartDefinition = updateScript.indexOf('systemctl restart hermes-bridge.service');
  const finalApiHealth = updateScript.lastIndexOf(
    'api_status="$(curl -fsS --max-time 5 http://127.0.0.1:8000/ready || true)"',
  );
  const finalBridgeHealth = updateScript.lastIndexOf(
    'bridge_status="$(curl -fsS --max-time 5 http://127.0.0.1:9118/health || true)"',
  );
  assert.ok(migration >= 0 && restart > migration && health > restart);
  assert.ok(runtimeDirs > health && matrixLink > runtimeDirs && audit > matrixLink);
  assert.ok(marker > audit && vaultLinks > marker && switchLink > vaultLinks && runtimeRestart > switchLink);
  assert.ok(bridgeRestartDefinition >= 0 && finalApiHealth > runtimeRestart && finalBridgeHealth > finalApiHealth);
  assert.ok(vaultLinks >= 0);
  assert.ok(cleanupTrap >= 0 && tarballAllocation > cleanupTrap && releaseAllocation > cleanupTrap);
  assert.match(updateScript, /\[ "\$#" -ne 1 \]/);
  assert.match(updateScript, /\^\[0-9a-fA-F\]\{40\}\$/);
  assert.doesNotMatch(updateScript, /refs\/heads\/main/);
  assert.doesNotMatch(updateScript, /audit_runtime_contracts[^\n]*\|\|/);
  assert.doesNotMatch(updateScript, /rm -rf "\$CURRENT_DIR"/);
  assert.match(updateScript, /trap cleanup EXIT/);
  assert.match(backendDockerfile, /PYTHONPATH=\/app/);
});

test('exact-SHA bootstrap exports, verifies, and executes the target commit update script', () => {
  assert.match(deployExactScript, /git show "\$EXPECTED_SHA:scripts\/update\.sh"/);
  assert.match(deployExactScript, /mktemp "\$\{TMPDIR:-\/tmp\}\/ai-lab-update\.XXXXXX"/);
  assert.doesNotMatch(deployExactScript, /XXXXXX\.sh/);
  assert.match(deployExactScript, /ssh[^\n]*mktemp \/tmp\/ai-lab-update\.XXXXXX/);
  assert.match(deployExactScript, /ssh[^\n]*rm -f -- "\$REMOTE_SCRIPT"/);
  assert.match(deployExactScript, /sha256sum "\$REMOTE_SCRIPT"/);
  assert.match(deployExactScript, /bash "\$REMOTE_SCRIPT" "\$EXPECTED_SHA"/);
  assert.doesNotMatch(deployExactScript, /\/opt\/ai-lab-platform\/scripts\/update\.sh/);
});

test('exact-SHA bootstrap executes the update script stored in the target commit', () => {
  const fixture = mkdtempSync(join(tmpdir(), 'ailab-exact-sha-'));
  const repository = join(fixture, 'repository');
  const fakeBin = join(fixture, 'bin');
  const marker = join(fixture, 'executed-sha');
  const remotePathLog = join(fixture, 'remote-path');
  mkdirSync(join(repository, 'scripts'), { recursive: true });
  mkdirSync(fakeBin);
  writeFileSync(join(repository, 'scripts', 'update.sh'), '#!/bin/bash\nset -eu\nprintf "%s" "$1" > "$DEPLOY_MARKER"\n');
  writeFileSync(join(fakeBin, 'scp'), '#!/bin/bash\nset -eu\ncp "$2" "${3#*:}"\n');
  writeFileSync(join(fakeBin, 'ssh'), '#!/bin/bash\nset -eu\nif [ "$1" = "-o" ]; then shift 2; fi\nshift\nif [ "$1" = "mktemp" ]; then\n  path="$("$@")"\n  printf "%s" "$path" > "$REMOTE_PATH_LOG"\n  printf "%s\\n" "$path"\n  exit 0\nfi\nexec "$@"\n');
  chmodSync(join(fakeBin, 'scp'), 0o755);
  chmodSync(join(fakeBin, 'ssh'), 0o755);
  try {
    execFileSync('git', ['init', '-q'], { cwd: repository });
    execFileSync('git', ['config', 'user.email', 'test@example.invalid'], { cwd: repository });
    execFileSync('git', ['config', 'user.name', 'Test'], { cwd: repository });
    execFileSync('git', ['add', 'scripts/update.sh'], { cwd: repository });
    execFileSync('git', ['commit', '-qm', 'fixture'], { cwd: repository });
    const sha = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: repository, encoding: 'utf8' }).trim();
    execFileSync('bash', [fileURLToPath(new URL('../../scripts/deploy_exact_sha.sh', import.meta.url)), sha], {
      cwd: repository,
      env: {
        ...process.env,
        AI_LAB_DEPLOY_HOST: 'fake-host',
        DEPLOY_MARKER: marker,
        REMOTE_PATH_LOG: remotePathLog,
        PATH: `${fakeBin}:${process.env.PATH}`,
      },
    });
    assert.equal(readFileSync(marker, 'utf8'), sha);
    assert.equal(existsSync(readFileSync(remotePathLog, 'utf8')), false);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test('the same SHA allocates a fresh immutable release instance on every attempt', () => {
  const fixture = mkdtempSync(join(tmpdir(), 'ailab-release-allocation-'));
  const updatePath = fileURLToPath(new URL('../../scripts/update.sh', import.meta.url));
  try {
    const output = execFileSync('bash', ['-c', `
      AI_LAB_UPDATE_LIBRARY_ONLY=1 source "$1"
      first="$(allocate_release_dir "$2" abcdef123456)"
      second="$(allocate_release_dir "$2" abcdef123456)"
      test "$first" != "$second"
      test -d "$first"
      test -d "$second"
      printf '%s\\n%s\\n' "$first" "$second"
    `, 'bash', updatePath, fixture], { encoding: 'utf8' }).trim().split('\n');
    assert.equal(output.length, 2);
    assert.notEqual(output[0], output[1]);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test('deployment cleanup is armed before tarball and release allocation failures', () => {
  const fixture = realpathSync(mkdtempSync(join(tmpdir(), 'ailab-release-cleanup-')));
  const fakeBin = join(fixture, 'bin');
  const current = join(fixture, 'current');
  const releaseRoot = join(fixture, 'releases');
  const victimRelease = join(fixture, 'outside-release');
  const victimSentinel = join(victimRelease, 'sentinel');
  const validRelease = join(releaseRoot, 'ai-lab-platform-abcdef123456.A1b2C3');
  const tarballLog = join(fixture, 'tarball-path');
  mkdirSync(fakeBin);
  mkdirSync(current);
  mkdirSync(releaseRoot);
  mkdirSync(victimRelease);
  writeFileSync(victimSentinel, 'KEEP');
  writeFileSync(join(fakeBin, 'readlink'), '#!/bin/bash\nprintf "%s\\n" "$FAKE_CURRENT"\n');
  writeFileSync(join(fakeBin, 'mktemp'), '#!/bin/bash\nset -eu\nif [ "$1" = "-d" ]; then\n  mkdir -p "$FAKE_RELEASE"\n  printf "%s\\n" "$FAKE_RELEASE"\nelse\n  path="$(/usr/bin/mktemp /tmp/ailab-src.XXXXXX)"\n  printf "%s" "$path" > "$FAKE_TARBALL_LOG"\n  printf "%s\\n" "$path"\nfi\n');
  writeFileSync(join(fakeBin, 'curl'), '#!/bin/bash\nexit 1\n');
  chmodSync(join(fakeBin, 'readlink'), 0o755);
  chmodSync(join(fakeBin, 'mktemp'), 0o755);
  chmodSync(join(fakeBin, 'curl'), 0o755);
  const run = (release) => assert.throws(() => execFileSync('bash', [
    fileURLToPath(new URL('../../scripts/update.sh', import.meta.url)),
    'abcdef123456abcdef123456abcdef123456abcd',
  ], {
    env: {
      ...process.env,
      AI_LAB_APP_LINK: join(fixture, 'app-link'),
      AI_LAB_RELEASE_ROOT: releaseRoot,
      FAKE_CURRENT: current,
      FAKE_RELEASE: release,
      FAKE_TARBALL_LOG: tarballLog,
      PATH: `${fakeBin}:${process.env.PATH}`,
    },
    stdio: 'pipe',
  }));
  try {
    run(victimRelease);
    assert.equal(readFileSync(victimSentinel, 'utf8'), 'KEEP');
    assert.equal(existsSync(readFileSync(tarballLog, 'utf8')), false);

    run(validRelease);
    assert.equal(existsSync(validRelease), false);
    assert.equal(existsSync(readFileSync(tarballLog, 'utf8')), false);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test('a fresh release gets all Hermes Vault links before activation', () => {
  const fixture = realpathSync(mkdtempSync(join(tmpdir(), 'ailab-vault-links-')));
  const releaseRoot = join(fixture, 'releases');
  const release = join(releaseRoot, 'ai-lab-platform-abcdef123456.A1b2C3');
  const vault = join(fixture, 'vault');
  mkdirSync(release, { recursive: true });
  for (const name of ['wiki', 'raw', 'knowledge', 'tools']) mkdirSync(join(vault, name), { recursive: true });
  try {
    execFileSync('bash', [fileURLToPath(linkVaultScriptUrl), release, releaseRoot, vault]);
    for (const name of ['wiki', 'raw', 'knowledge', 'tools']) {
      assert.equal(realpathSync(join(release, name)), realpathSync(join(vault, name)));
    }
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test('missing Vault sources fail before changing any release path', () => {
  const fixture = realpathSync(mkdtempSync(join(tmpdir(), 'ailab-vault-links-fail-')));
  const releaseRoot = join(fixture, 'releases');
  const release = join(releaseRoot, 'ai-lab-platform-abcdef123456.A1b2C3');
  const vault = join(fixture, 'vault');
  mkdirSync(join(release, 'wiki'), { recursive: true });
  writeFileSync(join(release, 'wiki', 'sentinel'), 'unchanged');
  for (const name of ['wiki', 'raw', 'knowledge']) mkdirSync(join(vault, name), { recursive: true });
  try {
    assert.throws(() => execFileSync('bash', [fileURLToPath(linkVaultScriptUrl), release, releaseRoot, vault]));
    assert.equal(readFileSync(join(release, 'wiki', 'sentinel'), 'utf8'), 'unchanged');
    assert.equal(existsSync(join(release, 'raw')), false);
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

test('Vault linking rejects symlinks, non-canonical paths, roots, and overlap without deletion', () => {
  const fixture = realpathSync(mkdtempSync(join(tmpdir(), 'ailab-vault-boundary-')));
  const releaseRoot = join(fixture, 'releases');
  const vault = join(fixture, 'vault');
  const victim = join(fixture, 'victim');
  const releaseName = 'ai-lab-platform-abcdef123456.A1b2C3';
  const canonicalRelease = join(releaseRoot, releaseName);
  const linkRelease = join(releaseRoot, 'ai-lab-platform-abcdef123456.D4e5F6');
  mkdirSync(canonicalRelease, { recursive: true });
  mkdirSync(join(releaseRoot, 'nested'));
  for (const name of ['wiki', 'raw', 'knowledge', 'tools']) {
    mkdirSync(join(vault, name), { recursive: true });
    mkdirSync(join(victim, name), { recursive: true });
    writeFileSync(join(victim, name, 'sentinel'), 'unchanged');
  }
  symlinkSync(victim, linkRelease);
  const helper = fileURLToPath(linkVaultScriptUrl);
  try {
    assert.throws(() => execFileSync('bash', [helper, linkRelease, releaseRoot, vault]));
    assert.throws(() => execFileSync('bash', [helper, `${releaseRoot}/nested/../${releaseName}`, releaseRoot, vault]));
    assert.throws(() => execFileSync('bash', [helper, releaseRoot, releaseRoot, vault]));
    assert.throws(() => execFileSync('bash', [helper, canonicalRelease, releaseRoot, releaseRoot]));
    for (const name of ['wiki', 'raw', 'knowledge', 'tools']) {
      assert.equal(readFileSync(join(victim, name, 'sentinel'), 'utf8'), 'unchanged');
    }
  } finally {
    rmSync(fixture, { recursive: true, force: true });
  }
});

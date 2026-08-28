#!/bin/bash
# 为尚未激活的 release 建立 Hermes 所需的持久 Vault 链接。

set -euo pipefail

if [ "$#" -ne 3 ]; then
  echo "ERROR: 用法: link_release_vault.sh <release_dir> <release_root> <vault_root>" >&2
  exit 2
fi

RELEASE_DIR="$1"
RELEASE_ROOT="$2"
VAULT_ROOT="$3"

for path in "$RELEASE_DIR" "$RELEASE_ROOT" "$VAULT_ROOT"; do
  case "$path" in
    /*) ;;
    *) echo "ERROR: 所有路径必须是绝对路径: $path" >&2; exit 2 ;;
  esac
  if [ -L "$path" ] || [ ! -d "$path" ]; then
    echo "ERROR: 路径必须是非符号链接目录: $path" >&2
    exit 2
  fi
done

RELEASE_REAL="$(cd "$RELEASE_DIR" && pwd -P)"
RELEASE_ROOT_REAL="$(cd "$RELEASE_ROOT" && pwd -P)"
VAULT_ROOT_REAL="$(cd "$VAULT_ROOT" && pwd -P)"

# 拒绝 ..、尾斜杠、符号链接祖先和其他非规范输入。
if [ "$RELEASE_DIR" != "$RELEASE_REAL" ] || \
   [ "$RELEASE_ROOT" != "$RELEASE_ROOT_REAL" ] || \
   [ "$VAULT_ROOT" != "$VAULT_ROOT_REAL" ]; then
  echo "ERROR: 路径必须使用规范物理路径" >&2
  exit 2
fi

RELEASE_BASENAME="$(basename "$RELEASE_REAL")"
if [ "$(dirname "$RELEASE_REAL")" != "$RELEASE_ROOT_REAL" ] || \
   [[ ! "$RELEASE_BASENAME" =~ ^ai-lab-platform-[0-9a-f]{12}\.[A-Za-z0-9]{6}$ ]]; then
  echo "ERROR: release 必须是授权根目录下的直接不可变实例" >&2
  exit 2
fi

if [[ "$RELEASE_REAL/" == "$VAULT_ROOT_REAL/"* ]] || \
   [[ "$VAULT_ROOT_REAL/" == "$RELEASE_REAL/"* ]]; then
  echo "ERROR: release 与 Vault 路径不得重叠" >&2
  exit 2
fi

# 先验证完整且规范的源集合，确保缺任一目录时零写入。
for name in wiki raw knowledge tools; do
  source="$VAULT_ROOT_REAL/$name"
  if [ -L "$source" ] || [ ! -d "$source" ] || \
     [ "$(cd "$source" && pwd -P)" != "$source" ]; then
    echo "ERROR: Vault 源必须是规范的非符号链接目录: $source" >&2
    exit 2
  fi
done

for name in wiki raw knowledge tools; do
  rm -rf -- "$RELEASE_REAL/$name"
  ln -s "$VAULT_ROOT_REAL/$name" "$RELEASE_REAL/$name"
done

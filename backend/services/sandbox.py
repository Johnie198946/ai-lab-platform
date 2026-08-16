"""
临时代码容器 —— Code Agent 专用沙箱

核心思想:
- Agent 被放进一个代码专用隔离容器
- 容器内有: 文件系统 + 执行权限 + 工具链
- 容器外的一切碰不到
- 任务结束容器销毁

实现: 每个租户 + 任务 = 一个临时工作目录
"""

import shutil
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Optional


class CodeSandbox:
    """
    代码沙箱

    用法:
        sandbox = CodeSandbox(tenant_id="bank_a")

        with sandbox.create(task_id="gen-html-001") as ws:
            # ws.root = /tmp/sandbox/bank_a/gen-html-001/
            # Agent 在这个目录里写文件、跑命令
            workspace.write_file("index.html", content)
            result = workspace.run("cat index.html")

        # 退出 with 块 → 沙箱自动清理
    """

    def __init__(self, tenant_id: str, base_dir: str = "/tmp/ai-lab-sandbox"):
        self.tenant_id = tenant_id
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def create(self, task_id: Optional[str] = None):
        """
        创建临时工作区

        Args:
            task_id: 任务标识(默认自动生成)

        Yields:
            Workspace 对象
        """
        task_id = task_id or uuid.uuid4().hex[:12]

        # 租户隔离: 每个租户有自己的子目录
        tenant_dir = self.base_dir / self.tenant_id
        tenant_dir.mkdir(parents=True, exist_ok=True)

        # 任务隔离: 每个任务有自己的工作区
        workspace_dir = tenant_dir / task_id

        # 清理同名旧目录
        if workspace_dir.exists():
            shutil.rmtree(workspace_dir)

        workspace_dir.mkdir()

        ws = Workspace(
            root=workspace_dir,
            tenant_id=self.tenant_id,
            task_id=task_id,
        )

        try:
            yield ws
        finally:
            # 退出时清理
            if workspace_dir.exists():
                shutil.rmtree(workspace_dir)

    def list_active(self) -> list:
        """列出当前活跃的沙箱"""
        tenant_dir = self.base_dir / self.tenant_id
        if not tenant_dir.exists():
            return []
        return [d.name for d in tenant_dir.iterdir() if d.is_dir()]

    def cleanup_all(self):
        """清理租户的所有沙箱"""
        tenant_dir = self.base_dir / self.tenant_id
        if tenant_dir.exists():
            shutil.rmtree(tenant_dir)


class Workspace:
    """代码工作区 —— Agent 的操作空间"""

    def __init__(self, root: Path, tenant_id: str, task_id: str):
        self.root = root
        self.tenant_id = tenant_id
        self.task_id = task_id

    def write_file(self, path: str, content: str):
        """写文件到工作区"""
        file_path = self.root / path
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        return str(file_path)

    def read_file(self, path: str) -> str:
        """读工作区文件"""
        file_path = self.root / path
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {path}")
        return file_path.read_text(encoding="utf-8")

    def list_files(self, subdir: str = ".") -> list:
        """列出工作区文件"""
        target = self.root / subdir
        if not target.exists():
            return []
        return [str(p.relative_to(self.root)) for p in target.rglob("*") if p.is_file()]

    def run(self, command: str, timeout: int = 30) -> dict:
        """
        在工作区内执行命令

        安全约束:
        - 禁止网络访问(生产环境需额外限制)
        - timeout 上限 30s
        """
        import subprocess

        result = subprocess.run(
            command,
            shell=True,
            cwd=str(self.root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode,
        }

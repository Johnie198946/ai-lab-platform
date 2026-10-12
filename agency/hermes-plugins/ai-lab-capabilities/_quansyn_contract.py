"""Shared bounded QuanSyn wire contract, independent of runtime/database imports."""
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator


class FileRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    artifact_id: str = Field(pattern=r"^ga_[a-f0-9]{32}$")


class Block(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["markdown", "code", "table", "chart"]
    content: str = Field("", max_length=250_000)
    labels: list[str] = Field(default_factory=list, max_length=100)
    values: list[float] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def shape(self):
        if self.kind == "chart" and (not self.labels or len(self.labels) != len(self.values)):
            raise ValueError("图表必须提供等长的真实标签和数值")
        if any(not (-1e15 < x < 1e15) for x in self.values):
            raise ValueError("图表数值无效")
        return self


class TransferBody(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(min_length=8, max_length=100)
    direction: Literal["request", "result"] = "request"
    target: Literal["ios", "mac"] = "ios"
    reply_to: str | None = Field(None, pattern=r"^qs_[a-f0-9]{32}$")
    text: str = Field("", max_length=250_000)
    blocks: list[Block] = Field(default_factory=list, max_length=100)
    files: list[FileRef] = Field(default_factory=list, max_length=10)

    @model_validator(mode="after")
    def complete(self):
        if not (self.text.strip() or self.blocks or self.files):
            raise ValueError("请输入内容或添加附件")
        if len(self.model_dump_json().encode()) > 512_000:
            raise ValueError("内容超过 512 KB")
        if self.direction == "request" and self.reply_to:
            raise ValueError("需求不能关联另一条需求")
        return self

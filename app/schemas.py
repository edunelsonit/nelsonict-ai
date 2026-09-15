from typing import Literal
from pydantic import BaseModel, Field


class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9_.@-]+$")
    password: str = Field(min_length=12, max_length=128)


class Setup(Credentials):
    setup_token: str = Field(min_length=20, max_length=128)


class NewUser(Credentials):
    role: Literal["admin", "member"] = "member"


class Name(BaseModel):
    name: str = Field(min_length=1, max_length=100)


class Assistant(Name):
    instructions: str = Field(default="You are Nelsonict AI, a helpful and accurate assistant.", max_length=3000)
    kb_id: int | None = None


class Conversation(BaseModel):
    title: str = Field(default="New conversation", min_length=1, max_length=100)
    assistant_id: int | None = None


class Chat(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    mode: Literal["general", "documents"] = "documents"
    kb_id: int | None = None
    task: Literal["question", "summary", "compare"] = "question"
    document_ids: list[int] = Field(default_factory=list, max_length=8)


class ModelConfig(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    context: int = Field(default=4096, ge=1024, le=32768)
    threads: int = Field(default=4, ge=1, le=128)
    gpu_layers: int = Field(default=0, ge=-1, le=200)
    chat_format: str | None = Field(default=None, max_length=80)
    max_tokens: int = Field(default=512, ge=64, le=2048)
    temperature: float = Field(default=0.3, ge=0, le=1.5)


class Share(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    permission: Literal["reader", "editor"] = "reader"


class Profile(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    config: ModelConfig

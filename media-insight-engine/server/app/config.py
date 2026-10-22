"""Settings from the environment, and loading of config/collections/*.yaml + config/lenses/*.yaml (FR-1)."""
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal


import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator


class Settings:
    database_url = os.environ.get("DATABASE_URL", "postgresql://mie:mie@localhost:5437/mie")
    # DB auth: "password" (default; existing/local behavior) or "cert" (mutual TLS, certs from Vault).
    db_auth = os.environ.get("DB_AUTH", "password")
    vault_addr = os.environ.get("VAULT_ADDR", "http://vault:8200")
    vault_token = os.environ.get("VAULT_TOKEN", "")            # empty -> read vault_token_file instead
    vault_token_file = os.environ.get("VAULT_TOKEN_FILE", "/certs-shared/vault-token")
    vault_db_cert_path = os.environ.get("VAULT_DB_CERT_PATH", "mie/db-client")
    db_cert_dir = os.environ.get("DB_CERT_DIR", "/run/mie-certs")  # tmpfs; keys live in RAM only
    config_dir = Path(os.environ.get("CONFIG_DIR", "/config"))
    prompts_dir = Path(os.environ.get("PROMPTS_DIR", "/prompts"))
    golden_dir = Path(os.environ.get("GOLDEN_DIR", "/golden"))
    analysis_model = os.environ.get("ANALYSIS_MODEL", "claude-opus-5-5")
    answer_model = os.environ.get("ANSWER_MODEL", "claude-sonnet-5-5")
    ingest_workers = int(os.environ.get("INGEST_WORKERS", "2"))
    bank_workers = int(os.environ.get("BANK_WORKERS", "4"))
    cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:5176").split(",")
    api_url = os.environ.get("API_URL", "http://localhost:8003")  # used by the CLIs


settings = Settings()
SLUG = re.compile(r"^[a-z0-9-]+$")


class ConfigError(Exception):
    """The whole collection file is unusable (HTTP 422)."""


class Lens(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = "inline"
    domain: str
    reader_role: str
    focus: str
    tags: list[str] = Field(min_length=1)
    segment_seconds: int = Field(60, ge=30, le=300)
    stale_after_months: int = Field(18, ge=1)


class SourceEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    url: str
    label: str | None = None
    type: Literal["youtube", "web", "audio", "pdf", "rss"] | None = None
    priority: Literal["high", "normal", "low"] = "normal"
    notes: str | None = None
    episodes: int = Field(10, ge=1, le=200)  # rss: newest N episodes (after `match`)
    match: str | None = None                 # rss: regex on episode titles, case-insensitive

    @field_validator("match")
    @classmethod
    def _valid_regex(cls, v: str | None) -> str | None:
        if v is not None:
            try:
                re.compile(v)
            except re.error as e:  # not a ValueError, so pydantic wouldn't turn it into a validation error
                raise ValueError(f"invalid regex: {e}") from e
        return v


class CollectionFile(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    lens: str | dict
    focus_note: str | None = None
    tags: list[str] = []
    sources: list = []  # validated one by one, so one bad entry doesn't sink the file


@dataclass
class InvalidEntry:
    url: str | None
    reason: str


@dataclass
class Collection:
    id: str
    name: str
    lens: Lens
    lens_name: str
    lens_text: str
    focus_note: str | None
    entries: list[SourceEntry | InvalidEntry] = field(default_factory=list)


def _read_yaml(path: Path) -> dict:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise ConfigError(f"{path.name}: not valid YAML ({e})") from e
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name}: expected a mapping at the top level")
    return data


def _errors(e: ValidationError) -> str:
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or 'file'}: {err['msg']}" for err in e.errors())


def load_lens(name: str, config_dir: Path) -> dict:
    path = config_dir / "lenses" / f"{name}.yaml"
    if not path.is_file():
        raise ConfigError(f"lens '{name}' not found in config/lenses/")
    return _read_yaml(path)


def render_lens(lens: Lens, focus_note: str | None) -> str:
    lines = [f"Domain: {lens.domain}", f"Reader: {lens.reader_role}", f"Focus: {lens.focus.strip()}"]
    if focus_note:
        lines.append(f"Collection note: {focus_note}")
    lines.append("Tag vocabulary: " + ", ".join(lens.tags))
    return "\n".join(lines)


def collection_slugs(config_dir: Path | None = None) -> list[str]:
    folder = (config_dir or settings.config_dir) / "collections"
    return sorted(p.stem for p in folder.glob("*.yaml") if SLUG.match(p.stem))


def load_collection(slug: str, config_dir: Path | None = None) -> Collection:
    """Raise FileNotFoundError for an unknown slug, ConfigError for a broken file."""
    config_dir = config_dir or settings.config_dir
    path = config_dir / "collections" / f"{slug}.yaml"
    if not SLUG.match(slug) or not path.is_file():
        raise FileNotFoundError(slug)
    try:
        cf = CollectionFile.model_validate(_read_yaml(path))
    except ValidationError as e:
        raise ConfigError(f"collections/{slug}.yaml: {_errors(e)}") from e

    # Effective lens (FR-1.5): shared file, inline fields replace it, college tags are added.
    if isinstance(cf.lens, str):
        lens_name, raw = cf.lens, load_lens(cf.lens, config_dir)
    else:
        inline = dict(cf.lens)
        base = inline.pop("extends", None)
        lens_name = base or "inline"
        raw = {**(load_lens(base, config_dir) if base else {}), **inline}
    raw["tags"] = list(dict.fromkeys([*raw.get("tags", []), *cf.tags]))
    try:
        lens = Lens.model_validate(raw)
    except ValidationError as e:
        raise ConfigError(f"collections/{slug}.yaml: lens: {_errors(e)}") from e

    entries: list[SourceEntry | InvalidEntry] = []
    for item in cf.sources:
        try:
            entries.append(SourceEntry.model_validate(item if isinstance(item, dict) else {"url": item}))
        except ValidationError as e:
            url = item.get("url") if isinstance(item, dict) else item
            entries.append(InvalidEntry(str(url) if url else None, f"Invalid entry: {_errors(e)}"))
    return Collection(slug, cf.name, lens, lens_name, render_lens(lens, cf.focus_note), cf.focus_note, entries)

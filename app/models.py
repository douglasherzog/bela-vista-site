from sqlalchemy import String, Integer, Text, ForeignKey, DateTime, Table, Boolean, Numeric, Column
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from .database import Base

# Associação N:N entre Suite e Amenidade
suite_amenidade = Table(
    "suite_amenidade",
    Base.metadata,
    Column("suite_id", ForeignKey("suites.id"), primary_key=True),
    Column("amenidade_id", ForeignKey("amenidades.id"), primary_key=True),
)


class SiteConfig(Base):
    __tablename__ = "site_config"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome_site: Mapped[str | None] = mapped_column(String(200), nullable=True)
    descricao_breve: Mapped[str | None] = mapped_column(Text, nullable=True)
    endereco: Mapped[str | None] = mapped_column(String(300), nullable=True)
    whatsapp: Mapped[str | None] = mapped_column(String(50), nullable=True)
    telefone: Mapped[str | None] = mapped_column(String(50), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    primary_color: Mapped[str | None] = mapped_column(String(20), nullable=True)
    maps_embed_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[DateTime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class TipoSuite(Base):
    __tablename__ = "tipos_suite"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0)

    suites: Mapped[list["Suite"]] = relationship(back_populates="tipo")


class Amenidade(Base):
    __tablename__ = "amenidades"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    nome: Mapped[str] = mapped_column(String(120))
    icone: Mapped[str | None] = mapped_column(String(120), nullable=True)

    suites: Mapped[list["Suite"]] = relationship(
        secondary=suite_amenidade, back_populates="amenidades"
    )


class Suite(Base):
    __tablename__ = "suites"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    titulo: Mapped[str] = mapped_column(String(200))
    slug: Mapped[str] = mapped_column(String(200), unique=True)
    tipo_id: Mapped[int | None] = mapped_column(ForeignKey("tipos_suite.id"), nullable=True)
    descricao: Mapped[str | None] = mapped_column(Text, nullable=True)
    preco_hora: Mapped[Numeric | None] = mapped_column(Numeric(10,2), nullable=True)
    preco_pernoite: Mapped[Numeric | None] = mapped_column(Numeric(10,2), nullable=True)
    destaque: Mapped[bool] = mapped_column(Boolean, default=False)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20), default="ativo")

    tipo: Mapped[TipoSuite | None] = relationship(back_populates="suites")
    amenidades: Mapped[list[Amenidade]] = relationship(
        secondary=suite_amenidade, back_populates="suites"
    )
    fotos: Mapped[list["Foto"]] = relationship(back_populates="suite", cascade="all, delete-orphan")


class Foto(Base):
    __tablename__ = "fotos"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    suite_id: Mapped[int] = mapped_column(ForeignKey("suites.id"))
    url: Mapped[str] = mapped_column(String(500))
    legenda: Mapped[str | None] = mapped_column(String(200), nullable=True)
    ordem: Mapped[int] = mapped_column(Integer, default=0)
    capa: Mapped[bool] = mapped_column(Boolean, default=False)

    suite: Mapped[Suite] = relationship(back_populates="fotos")

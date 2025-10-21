from fastapi import FastAPI, Request, Form, status, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from .database import Base, engine, get_session
from .models import SiteConfig, TipoSuite, Amenidade, Suite, Foto
from .auth import require_basic_auth
from typing import List
import re

# Garantir criação das tabelas inicialmente (depois usaremos Alembic)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="Motel Bela Vista - Rio Pardo/RS")

# Templates Jinja
templates_env = Environment(
    loader=FileSystemLoader("app/templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

# Static
app.mount("/static", StaticFiles(directory="app/static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    t = templates_env.get_template("index.html")
    return t.render(site=site)


@app.get("/sobre", response_class=HTMLResponse)
async def sobre(request: Request):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    t = templates_env.get_template("sobre.html")
    return t.render(site=site)


@app.get("/contato", response_class=HTMLResponse)
async def contato(request: Request):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    t = templates_env.get_template("contato.html")
    return t.render(site=site)


# ---------------------- Admin básico ----------------------

@app.get("/config", response_class=HTMLResponse)
async def config_get(request: Request, _: bool = Depends(require_basic_auth)):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    t = templates_env.get_template("config.html")
    return t.render(site=site)


@app.post("/config")
async def config_post(
    nomeSite: str = Form(""),
    descricaoBreve: str = Form(""),
    endereco: str = Form(""),
    whatsapp: str = Form(""),
    telefone: str = Form(""),
    mapsEmbedUrl: str = Form(""),
    _: bool = Depends(require_basic_auth),
):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        if site is None:
            site = SiteConfig(
                nome_site=nomeSite or None,
                descricao_breve=descricaoBreve or None,
                endereco=endereco or None,
                whatsapp=whatsapp or None,
                telefone=telefone or None,
                maps_embed_url=mapsEmbedUrl or None,
            )
            db.add(site)
        else:
            site.nome_site = nomeSite or None
            site.descricao_breve = descricaoBreve or None
            site.endereco = endereco or None
            site.whatsapp = whatsapp or None
            site.telefone = telefone or None
            site.maps_embed_url = mapsEmbedUrl or None
        db.commit()
    return RedirectResponse(url="/config", status_code=status.HTTP_302_FOUND)


# ---------------------- Util ----------------------
def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text


# ---------------------- CRUD: Tipos de Suíte ----------------------
@app.get("/admin/tipos", response_class=HTMLResponse)
async def tipos_list(_: bool = Depends(require_basic_auth)):
    with get_session() as db:
        items = db.execute(select(TipoSuite).order_by(TipoSuite.ordem.asc(), TipoSuite.nome.asc())).scalars().all()
    t = templates_env.get_template("admin_tipos.html")
    return t.render(items=items)


@app.get("/admin/tipos/novo", response_class=HTMLResponse)
async def tipos_new(_: bool = Depends(require_basic_auth)):
    t = templates_env.get_template("admin_tipos_form.html")
    return t.render(item=None)


@app.post("/admin/tipos/novo")
async def tipos_create(
    nome: str = Form(""),
    descricao: str = Form(""),
    ordem: int = Form(0),
    _: bool = Depends(require_basic_auth),
):
    with get_session() as db:
        item = TipoSuite(nome=nome, descricao=descricao or None, ordem=ordem or 0)
        db.add(item)
        db.commit()
    return RedirectResponse(url="/admin/tipos", status_code=status.HTTP_302_FOUND)


@app.get("/admin/tipos/editar/{id}", response_class=HTMLResponse)
async def tipos_edit(id: int, _: bool = Depends(require_basic_auth)):
    with get_session() as db:
        item = db.get(TipoSuite, id)
    t = templates_env.get_template("admin_tipos_form.html")
    return t.render(item=item)


@app.post("/admin/tipos/editar/{id}")
async def tipos_update(
    id: int,
    nome: str = Form(""),
    descricao: str = Form(""),
    ordem: int = Form(0),
    _: bool = Depends(require_basic_auth),
):
    with get_session() as db:
        item = db.get(TipoSuite, id)
        if item:
            item.nome = nome
            item.descricao = descricao or None
            item.ordem = ordem or 0
            db.commit()
    return RedirectResponse(url="/admin/tipos", status_code=status.HTTP_302_FOUND)


@app.post("/admin/tipos/excluir/{id}")
async def tipos_delete(id: int, _: bool = Depends(require_basic_auth)):
    with get_session() as db:
        item = db.get(TipoSuite, id)
        if item:
            db.delete(item)
            db.commit()
    return RedirectResponse(url="/admin/tipos", status_code=status.HTTP_302_FOUND)


# ---------------------- CRUD: Amenidades ----------------------
@app.get("/admin/amenidades", response_class=HTMLResponse)
async def amenidades_list(_: bool = Depends(require_basic_auth)):
    with get_session() as db:
        items = db.execute(select(Amenidade).order_by(Amenidade.nome.asc())).scalars().all()
    t = templates_env.get_template("admin_amenidades.html")
    return t.render(items=items)


@app.get("/admin/amenidades/novo", response_class=HTMLResponse)
async def amenidades_new(_: bool = Depends(require_basic_auth)):
    t = templates_env.get_template("admin_amenidades_form.html")
    return t.render(item=None)


@app.post("/admin/amenidades/novo")
async def amenidades_create(
    nome: str = Form(""),
    icone: str = Form(""),
    _: bool = Depends(require_basic_auth),
):
    with get_session() as db:
        item = Amenidade(nome=nome, icone=icone or None)
        db.add(item)
        db.commit()
    return RedirectResponse(url="/admin/amenidades", status_code=status.HTTP_302_FOUND)


@app.get("/admin/amenidades/editar/{id}", response_class=HTMLResponse)
async def amenidades_edit(id: int, _: bool = Depends(require_basic_auth)):
    with get_session() as db:
        item = db.get(Amenidade, id)
    t = templates_env.get_template("admin_amenidades_form.html")
    return t.render(item=item)


@app.post("/admin/amenidades/editar/{id}")
async def amenidades_update(
    id: int,
    nome: str = Form(""),
    icone: str = Form(""),
    _: bool = Depends(require_basic_auth),
):
    with get_session() as db:
        item = db.get(Amenidade, id)
        if item:
            item.nome = nome
            item.icone = icone or None
            db.commit()
    return RedirectResponse(url="/admin/amenidades", status_code=status.HTTP_302_FOUND)


@app.post("/admin/amenidades/excluir/{id}")
async def amenidades_delete(id: int, _: bool = Depends(require_basic_auth)):
    with get_session() as db:
        item = db.get(Amenidade, id)
        if item:
            db.delete(item)
            db.commit()
    return RedirectResponse(url="/admin/amenidades", status_code=status.HTTP_302_FOUND)


# ---------------------- CRUD: Suítes ----------------------
@app.get("/admin/suites", response_class=HTMLResponse)
async def suites_list(_: bool = Depends(require_basic_auth)):
    with get_session() as db:
        items = db.execute(select(Suite).order_by(Suite.ordem.asc(), Suite.titulo.asc())).scalars().all()
        tipos = db.execute(select(TipoSuite).order_by(TipoSuite.nome.asc())).scalars().all()
    t = templates_env.get_template("admin_suites.html")
    return t.render(items=items, tipos=tipos)


@app.get("/admin/suites/novo", response_class=HTMLResponse)
async def suites_new(_: bool = Depends(require_basic_auth)):
    with get_session() as db:
        tipos = db.execute(select(TipoSuite).order_by(TipoSuite.nome.asc())).scalars().all()
        amenidades = db.execute(select(Amenidade).order_by(Amenidade.nome.asc())).scalars().all()
    t = templates_env.get_template("admin_suites_form.html")
    return t.render(item=None, tipos=tipos, amenidades=amenidades)


@app.post("/admin/suites/novo")
async def suites_create(
    titulo: str = Form(""),
    slug: str = Form(""),
    tipo_id: int = Form(None),
    descricao: str = Form(""),
    preco_hora: str = Form(""),
    preco_pernoite: str = Form(""),
    destaque: str = Form(""),
    ordem: int = Form(0),
    amenidades_ids: List[int] = Form(default=[]),
    _: bool = Depends(require_basic_auth),
):
    with get_session() as db:
        s = Suite(
            titulo=titulo,
            slug=slug or slugify(titulo),
            tipo_id=tipo_id or None,
            descricao=descricao or None,
            preco_hora=(preco_hora or None),
            preco_pernoite=(preco_pernoite or None),
            destaque=True if (destaque == "on") else False,
            ordem=ordem or 0,
        )
        if amenidades_ids:
            s.amenidades = db.execute(select(Amenidade).where(Amenidade.id.in_(amenidades_ids))).scalars().all()
        db.add(s)
        db.commit()
    return RedirectResponse(url="/admin/suites", status_code=status.HTTP_302_FOUND)


@app.get("/admin/suites/editar/{id}", response_class=HTMLResponse)
async def suites_edit(id: int, _: bool = Depends(require_basic_auth)):
    with get_session() as db:
        item = db.get(Suite, id)
        tipos = db.execute(select(TipoSuite).order_by(TipoSuite.nome.asc())).scalars().all()
        amenidades = db.execute(select(Amenidade).order_by(Amenidade.nome.asc())).scalars().all()
    t = templates_env.get_template("admin_suites_form.html")
    return t.render(item=item, tipos=tipos, amenidades=amenidades)


@app.post("/admin/suites/editar/{id}")
async def suites_update(
    id: int,
    titulo: str = Form(""),
    slug: str = Form(""),
    tipo_id: int = Form(None),
    descricao: str = Form(""),
    preco_hora: str = Form(""),
    preco_pernoite: str = Form(""),
    destaque: str = Form(""),
    ordem: int = Form(0),
    amenidades_ids: List[int] = Form(default=[]),
    _: bool = Depends(require_basic_auth),
):
    with get_session() as db:
        s = db.get(Suite, id)
        if s:
            s.titulo = titulo
            s.slug = slug or slugify(titulo)
            s.tipo_id = tipo_id or None
            s.descricao = descricao or None
            s.preco_hora = (preco_hora or None)
            s.preco_pernoite = (preco_pernoite or None)
            s.destaque = True if (destaque == "on") else False
            s.ordem = ordem or 0
            if amenidades_ids is not None:
                s.amenidades = db.execute(select(Amenidade).where(Amenidade.id.in_(amenidades_ids))).scalars().all()
            db.commit()
    return RedirectResponse(url="/admin/suites", status_code=status.HTTP_302_FOUND)


@app.post("/admin/suites/excluir/{id}")
async def suites_delete(id: int, _: bool = Depends(require_basic_auth)):
    with get_session() as db:
        s = db.get(Suite, id)
        if s:
            db.delete(s)
            db.commit()
    return RedirectResponse(url="/admin/suites", status_code=status.HTTP_302_FOUND)


# ---------------------- CRUD: Fotos (por suíte) ----------------------
@app.get("/admin/suites/{suite_id}/fotos", response_class=HTMLResponse)
async def fotos_list(suite_id: int, _: bool = Depends(require_basic_auth)):
    with get_session() as db:
        suite = db.get(Suite, suite_id)
        fotos = db.execute(select(Foto).where(Foto.suite_id == suite_id).order_by(Foto.ordem.asc())).scalars().all()
    t = templates_env.get_template("admin_fotos.html")
    return t.render(suite=suite, fotos=fotos)


@app.post("/admin/suites/{suite_id}/fotos/novo")
async def fotos_create(
    suite_id: int,
    url: str = Form(""),
    legenda: str = Form(""),
    ordem: int = Form(0),
    capa: str = Form(""),
    _: bool = Depends(require_basic_auth),
):
    with get_session() as db:
        f = Foto(
            suite_id=suite_id,
            url=url,
            legenda=legenda or None,
            ordem=ordem or 0,
            capa=True if (capa == "on") else False,
        )
        db.add(f)
        db.commit()
    return RedirectResponse(url=f"/admin/suites/{suite_id}/fotos", status_code=status.HTTP_302_FOUND)


@app.post("/admin/fotos/excluir/{id}")
async def fotos_delete(id: int, _: bool = Depends(require_basic_auth)):
    with get_session() as db:
        f = db.get(Foto, id)
        suite_id = f.suite_id if f else None
        if f:
            db.delete(f)
            db.commit()
    return RedirectResponse(url=f"/admin/suites/{suite_id}/fotos", status_code=status.HTTP_302_FOUND)


# ---------------------- Público: Suítes ----------------------
@app.get("/suites", response_class=HTMLResponse)
async def suites_public_list(request: Request):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        tipos = db.execute(select(TipoSuite).order_by(TipoSuite.ordem.asc(), TipoSuite.nome.asc())).scalars().all()
        suites = db.execute(select(Suite).order_by(Suite.ordem.asc(), Suite.titulo.asc())).scalars().all()
    t = templates_env.get_template("suites.html")
    return t.render(site=site, tipos=tipos, suites=suites)


@app.get("/suites/{slug}", response_class=HTMLResponse)
async def suite_public_detail(slug: str):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        suite = db.execute(select(Suite).where(Suite.slug == slug)).scalar_one_or_none()
        fotos = []
        if suite:
            fotos = db.execute(
                select(Foto).where(Foto.suite_id == suite.id).order_by(Foto.capa.desc(), Foto.ordem.asc())
            ).scalars().all()
    t = templates_env.get_template("suite_detail.html")
    return t.render(site=site, suite=suite, fotos=fotos)

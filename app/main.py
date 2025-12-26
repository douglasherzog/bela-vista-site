from fastapi import FastAPI, Request, Form, status, Depends
from fastapi import HTTPException
from fastapi.exception_handlers import http_exception_handler as fastapi_http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse, Response, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from .database import Base, engine, get_session
from .models import SiteConfig, TipoSuite, Amenidade, Suite, Foto, Funcionario, User
from .auth import (
    bootstrap_admin_user,
    get_current_user,
    require_role,
    sign_session,
    verify_password,
    SESSION_COOKIE_NAME,
    hash_password,
)
from typing import List
import re
import os
import random
from pathlib import Path
from datetime import date
from typing import Optional
from urllib.parse import urlparse

# Garantir criação das tabelas inicialmente (depois usaremos Alembic)
Base.metadata.create_all(bind=engine)

try:
    bootstrap_admin_user()
except Exception:
    pass

# Migração leve: adicionar coluna 'email' em SiteConfig no SQLite, se não existir
try:
    with engine.connect() as conn:
        dialect = engine.dialect.name
        if dialect == "sqlite":
            cols = conn.exec_driver_sql("PRAGMA table_info(site_config)").fetchall()
            col_names = {row[1] for row in cols}
            if "email" not in col_names:
                conn.exec_driver_sql("ALTER TABLE site_config ADD COLUMN email VARCHAR(200)")
            if "primary_color" not in col_names:
                conn.exec_driver_sql("ALTER TABLE site_config ADD COLUMN primary_color VARCHAR(20)")
except Exception:
    # silencioso em dev; em prod usar Alembic
    pass

app = FastAPI(title="Motel Bela Vista - Rio Pardo/RS")

SITE_URL = os.getenv("SITE_URL", "https://www.motelbelavista.com.br").rstrip("/")
_parsed_site_url = urlparse(SITE_URL)
_default_canonical_scheme = (_parsed_site_url.scheme or "https").lower()
_default_canonical_host = _parsed_site_url.netloc
if _default_canonical_host.startswith("www."):
    _default_canonical_host = _default_canonical_host[4:]
CANONICAL_SCHEME = (os.getenv("CANONICAL_SCHEME") or _default_canonical_scheme).lower()
CANONICAL_HOST = os.getenv("CANONICAL_HOST") or _default_canonical_host
CANONICAL_SITE_URL = f"{CANONICAL_SCHEME}://{CANONICAL_HOST}".rstrip("/")


@app.middleware("http")
async def enforce_canonical_host(request: Request, call_next):
    host = (request.headers.get("host") or "").split(":", 1)[0].lower()
    if host and host != CANONICAL_HOST.lower() and host not in {"localhost", "127.0.0.1"}:
        qs = (request.url.query or "")
        location = f"{CANONICAL_SITE_URL}{request.url.path}" + (f"?{qs}" if qs else "")
        return RedirectResponse(url=location, status_code=status.HTTP_301_MOVED_PERMANENTLY)
    return await call_next(request)

# Templates Jinja
templates_env = Environment(
    loader=FileSystemLoader("app/templates"),
    autoescape=select_autoescape(["html", "xml"]),
)

class CachedStaticFiles(StaticFiles):
    def __init__(
        self,
        *args,
        cache_control: str = "public, max-age=2592000, immutable",
        cache_extensions: Optional[set[str]] = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self._cache_control = cache_control
        self._cache_extensions = cache_extensions or {
            ".webp",
            ".jpg",
            ".jpeg",
            ".png",
            ".gif",
            ".svg",
            ".ico",
        }

    async def get_response(self, path: str, scope):
        resp = await super().get_response(path, scope)
        if getattr(resp, "status_code", None) == 200:
            p = path.lower()
            for ext in self._cache_extensions:
                if p.endswith(ext):
                    resp.headers["Cache-Control"] = self._cache_control
                    break
        return resp

# Static
app.mount("/static", CachedStaticFiles(directory="app/static"), name="static")

fotos_apartamentos_dir = Path(os.getenv("FOTOS_APARTAMENTOS_DIR", "fotos_apartamentos"))
fotos_apartamentos_web_dir = Path(os.getenv("FOTOS_APARTAMENTOS_WEB_DIR", "fotos_apartamentos_web"))

if fotos_apartamentos_dir.is_dir():
    app.mount(
        "/fotos-apartamentos",
        CachedStaticFiles(directory=str(fotos_apartamentos_dir)),
        name="fotos-apartamentos",
    )
if fotos_apartamentos_web_dir.is_dir():
    app.mount(
        "/fotos-apartamentos-web",
        CachedStaticFiles(directory=str(fotos_apartamentos_web_dir)),
        name="fotos-apartamentos-web",
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    if exc.status_code == status.HTTP_401_UNAUTHORIZED:
        path = request.url.path
        if path.startswith("/admin") or path in ("/administracao", "/config"):
            return RedirectResponse(url="/admin/login", status_code=status.HTTP_302_FOUND)
    return await fastapi_http_exception_handler(request, exc)


def _render(template_name: str, request: Request, **ctx):
    ctx.setdefault("request", request)
    ctx.setdefault("current_user", get_current_user(request))
    ctx.setdefault("site_url", CANONICAL_SITE_URL)
    ctx.setdefault("ga4_measurement_id", os.getenv("GA4_MEASUREMENT_ID", "").strip() or None)
    t = templates_env.get_template(template_name)
    return t.render(**ctx)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        suites = db.execute(
            select(Suite)
            .options(selectinload(Suite.tipo))
            .order_by(Suite.destaque.desc(), Suite.ordem.asc(), Suite.titulo.asc())
        ).scalars().all()
        suite_ids = [s.id for s in suites]
        cover_map: dict[int, Foto | None] = {}
        amen_map: dict[int, list[str]] = {}
        for s in suites:
            f = db.execute(
                select(Foto).where(Foto.suite_id == s.id).order_by(Foto.capa.desc(), Foto.ordem.asc())
            ).scalars().first()
            cover_map[s.id] = f
        if suite_ids:
            from .models import suite_amenidade
            rows = db.execute(
                select(suite_amenidade.c.suite_id, Amenidade.nome)
                .join(Amenidade, Amenidade.id == suite_amenidade.c.amenidade_id)
                .where(suite_amenidade.c.suite_id.in_(suite_ids))
                .order_by(Amenidade.nome.asc())
            ).all()
            for sid, anome in rows:
                amen_map.setdefault(sid, []).append(anome)
    return _render("index.html", request, site=site, suites=suites, cover_map=cover_map, amen_map=amen_map)


@app.get("/sobre", response_class=HTMLResponse)
async def sobre(request: Request):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("sobre.html", request, site=site)


@app.get("/contato", response_class=HTMLResponse)
async def contato(request: Request):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("contato.html", request, site=site)


@app.get("/login", response_class=HTMLResponse)
async def login_get(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("login.html", request, site=site, error=None, admin_mode=False)


@app.post("/login")
async def login_post(request: Request, username: str = Form(""), password: str = Form("")):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        user = db.execute(select(User).where(User.username == username).limit(1)).scalar_one_or_none()
    if not user or user.status != "ativo" or not verify_password(password, user.password_hash):
        return HTMLResponse(
            _render("login.html", request, site=site, error="Usuário ou senha inválidos", admin_mode=False),
            status_code=401,
        )

    resp = RedirectResponse(
        url=("/administracao" if user.role == "admin" else "/funcionarios"),
        status_code=status.HTTP_302_FOUND,
    )
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sign_session(user.id),
        httponly=True,
        samesite="lax",
        secure=(request.url.scheme == "https"),
        path="/",
    )
    return resp


@app.get("/admin/login", response_class=HTMLResponse)
async def admin_login_get(request: Request):
    if get_current_user(request):
        return RedirectResponse(url="/administracao", status_code=status.HTTP_302_FOUND)
    admin_user = (os.getenv("ADMIN_USER") or "admin")
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render(
        "login.html",
        request,
        site=site,
        error=None,
        admin_mode=True,
        username_prefill=admin_user,
        form_action="/admin/login",
    )


@app.post("/admin/login")
async def admin_login_post(request: Request, password: str = Form("")):
    admin_user = (os.getenv("ADMIN_USER") or "admin")
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        user = db.execute(select(User).where(User.username == admin_user).limit(1)).scalar_one_or_none()
    if not user or user.status != "ativo" or user.role != "admin" or not verify_password(password, user.password_hash):
        return HTMLResponse(
            _render(
                "login.html",
                request,
                site=site,
                error="Senha inválida",
                admin_mode=True,
                username_prefill=admin_user,
                form_action="/admin/login",
            ),
            status_code=401,
        )

    resp = RedirectResponse(url="/administracao", status_code=status.HTTP_302_FOUND)
    resp.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=sign_session(user.id),
        httponly=True,
        samesite="lax",
        secure=(request.url.scheme == "https"),
        path="/",
    )
    return resp


@app.post("/logout")
async def logout_post(_: Request):
    resp = RedirectResponse(url="/", status_code=status.HTTP_302_FOUND)
    resp.delete_cookie(key=SESSION_COOKIE_NAME, path="/")
    return resp


@app.get("/robots.txt", response_class=PlainTextResponse)
async def robots_txt() -> str:
    return (
        "User-agent: *\n"
        "Allow: /\n\n"
        "Disallow: /admin\n"
        "Disallow: /administracao\n"
        "Disallow: /config\n"
        "Disallow: /funcionarios\n\n"
        f"Sitemap: {CANONICAL_SITE_URL}/sitemap.xml\n"
    )


@app.get("/sitemap.xml")
async def sitemap_xml() -> Response:
    lastmod = date.today().isoformat()
    urls: list[str] = [
        f"{CANONICAL_SITE_URL}/",
        f"{CANONICAL_SITE_URL}/sobre",
        f"{CANONICAL_SITE_URL}/contato",
        f"{CANONICAL_SITE_URL}/apartamentos",
        f"{CANONICAL_SITE_URL}/suites",
    ]
    try:
        with get_session() as db:
            slugs = (
                db.execute(
                    select(Suite.slug).where(Suite.status == "ativo").order_by(Suite.slug.asc())
                )
                .scalars()
                .all()
            )
        for slug in slugs:
            urls.append(f"{CANONICAL_SITE_URL}/suites/{slug}")
    except Exception:
        # Em produção, não falhar o sitemap se o banco estiver indisponível.
        pass

    body = [
        "<?xml version=\"1.0\" encoding=\"UTF-8\"?>",
        "<urlset xmlns=\"http://www.sitemaps.org/schemas/sitemap/0.9\">",
    ]
    for u in urls:
        body.append("  <url>")
        body.append(f"    <loc>{u}</loc>")
        body.append(f"    <lastmod>{lastmod}</lastmod>")
        body.append("  </url>")
    body.append("</urlset>")
    xml = "\n".join(body) + "\n"
    return Response(content=xml, media_type="application/xml")


@app.get("/funcionarios", response_class=HTMLResponse)
async def funcionarios_dashboard(request: Request, current_user: User = Depends(require_role("funcionario", "admin"))):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("funcionarios_dashboard.html", request, site=site, current_user=current_user)


# ---------------------- Administração ----------------------

@app.get("/administracao", response_class=HTMLResponse)
async def admin_dashboard(request: Request, current_user: User = Depends(require_role("admin"))):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_dashboard.html", request, site=site, current_user=current_user)

@app.get("/config", response_class=HTMLResponse)
async def config_get(request: Request, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    t = templates_env.get_template("config.html")
    return t.render(request=request, site=site, current_user=get_current_user(request), site_url=CANONICAL_SITE_URL)


@app.post("/config")
async def config_post(
    nomeSite: str = Form(""),
    descricaoBreve: str = Form(""),
    endereco: str = Form(""),
    whatsapp: str = Form(""),
    telefone: str = Form(""),
    email: str = Form(""),
    primaryColor: str = Form(""),
    mapsEmbedUrl: str = Form(""),
    _: User = Depends(require_role("admin")),
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
                email=email or None,
                primary_color=primaryColor or None,
                maps_embed_url=mapsEmbedUrl or None,
            )
            db.add(site)
        else:
            site.nome_site = nomeSite or None
            site.descricao_breve = descricaoBreve or None
            site.endereco = endereco or None
            site.whatsapp = whatsapp or None
            site.telefone = telefone or None
            site.email = email or None
            site.primary_color = primaryColor or None
            site.maps_embed_url = mapsEmbedUrl or None
        db.commit()
    return RedirectResponse(url="/config", status_code=status.HTTP_302_FOUND)


# ---------------------- Admin: Tipos de Suíte ----------------------
@app.get("/admin/tipos", response_class=HTMLResponse)
async def tipos_list(request: Request, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        items = db.execute(select(TipoSuite).order_by(TipoSuite.ordem.asc(), TipoSuite.nome.asc())).scalars().all()
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_tipos.html", request, site=site, items=items)


@app.get("/admin/tipos/novo", response_class=HTMLResponse)
async def tipos_new(request: Request, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_tipos_form.html", request, site=site, item=None)


@app.post("/admin/tipos/novo")
async def tipos_create(
    nome: str = Form(""),
    descricao: str = Form(""),
    ordem: int = Form(0),
    _: User = Depends(require_role("admin")),
):
    with get_session() as db:
        item = TipoSuite(nome=nome, descricao=descricao or None, ordem=ordem or 0)
        db.add(item)
        db.commit()
    return RedirectResponse(url="/admin/tipos", status_code=status.HTTP_302_FOUND)


@app.get("/admin/tipos/editar/{id}", response_class=HTMLResponse)
async def tipos_edit(request: Request, id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        item = db.get(TipoSuite, id)
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_tipos_form.html", request, site=site, item=item)


@app.post("/admin/tipos/editar/{id}")
async def tipos_update(
    id: int,
    nome: str = Form(""),
    descricao: str = Form(""),
    ordem: int = Form(0),
    _: User = Depends(require_role("admin")),
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
async def tipos_delete(id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        item = db.get(TipoSuite, id)
        if item:
            db.delete(item)
            db.commit()
    return RedirectResponse(url="/admin/tipos", status_code=status.HTTP_302_FOUND)


# ---------------------- Admin: Amenidades ----------------------
@app.get("/admin/amenidades", response_class=HTMLResponse)
async def amenidades_list(request: Request, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        items = db.execute(select(Amenidade).order_by(Amenidade.nome.asc())).scalars().all()
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_amenidades.html", request, site=site, items=items)


@app.get("/admin/amenidades/novo", response_class=HTMLResponse)
async def amenidades_new(request: Request, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_amenidades_form.html", request, site=site, item=None)


@app.post("/admin/amenidades/novo")
async def amenidades_create(
    nome: str = Form(""),
    icone: str = Form(""),
    _: User = Depends(require_role("admin")),
):
    with get_session() as db:
        item = Amenidade(nome=nome, icone=icone or None)
        db.add(item)
        db.commit()
    return RedirectResponse(url="/admin/amenidades", status_code=status.HTTP_302_FOUND)


@app.get("/admin/amenidades/editar/{id}", response_class=HTMLResponse)
async def amenidades_edit(request: Request, id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        item = db.get(Amenidade, id)
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_amenidades_form.html", request, site=site, item=item)


@app.post("/admin/amenidades/editar/{id}")
async def amenidades_update(
    id: int,
    nome: str = Form(""),
    icone: str = Form(""),
    _: User = Depends(require_role("admin")),
):
    with get_session() as db:
        item = db.get(Amenidade, id)
        if item:
            item.nome = nome
            item.icone = icone or None
            db.commit()
    return RedirectResponse(url="/admin/amenidades", status_code=status.HTTP_302_FOUND)


@app.post("/admin/amenidades/excluir/{id}")
async def amenidades_delete(id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        item = db.get(Amenidade, id)
        if item:
            db.delete(item)
            db.commit()
    return RedirectResponse(url="/admin/amenidades", status_code=status.HTTP_302_FOUND)


# ---------------------- Admin: Suítes ----------------------
@app.get("/admin/suites", response_class=HTMLResponse)
async def suites_list(request: Request, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        items = db.execute(select(Suite).options(selectinload(Suite.tipo)).order_by(Suite.ordem.asc(), Suite.titulo.asc())).scalars().all()
        tipos = db.execute(select(TipoSuite).order_by(TipoSuite.nome.asc())).scalars().all()
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_suites.html", request, site=site, items=items, tipos=tipos)


@app.get("/admin/suites/novo", response_class=HTMLResponse)
async def suites_new(request: Request, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        tipos = db.execute(select(TipoSuite).order_by(TipoSuite.nome.asc())).scalars().all()
        amenidades = db.execute(select(Amenidade).order_by(Amenidade.nome.asc())).scalars().all()
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_suites_form.html", request, site=site, item=None, tipos=tipos, amenidades=amenidades)


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
    _: User = Depends(require_role("admin")),
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
async def suites_edit(request: Request, id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        item = db.get(Suite, id)
        tipos = db.execute(select(TipoSuite).order_by(TipoSuite.nome.asc())).scalars().all()
        amenidades = db.execute(select(Amenidade).order_by(Amenidade.nome.asc())).scalars().all()
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_suites_form.html", request, site=site, item=item, tipos=tipos, amenidades=amenidades)


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
    _: User = Depends(require_role("admin")),
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
async def suites_delete(id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        s = db.get(Suite, id)
        if s:
            db.delete(s)
            db.commit()
    return RedirectResponse(url="/admin/suites", status_code=status.HTTP_302_FOUND)


# ---------------------- Admin: Fotos ----------------------
@app.get("/admin/suites/{suite_id}/fotos", response_class=HTMLResponse)
async def fotos_list(request: Request, suite_id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        suite = db.get(Suite, suite_id)
        fotos = db.execute(select(Foto).where(Foto.suite_id == suite_id).order_by(Foto.ordem.asc())).scalars().all()
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_fotos.html", request, site=site, suite=suite, fotos=fotos)


@app.post("/admin/suites/{suite_id}/fotos/novo")
async def fotos_create(
    suite_id: int,
    url: str = Form(""),
    legenda: str = Form(""),
    ordem: int = Form(0),
    capa: str = Form(""),
    _: User = Depends(require_role("admin")),
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
async def fotos_delete(id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        f = db.get(Foto, id)
        suite_id = f.suite_id if f else None
        if f:
            db.delete(f)
            db.commit()
    return RedirectResponse(url=f"/admin/suites/{suite_id}/fotos", status_code=status.HTTP_302_FOUND)


@app.get("/admin/usuarios", response_class=HTMLResponse)
async def users_list(request: Request, current_user: User = Depends(require_role("admin"))):
    with get_session() as db:
        items = db.execute(select(User).order_by(User.role.asc(), User.username.asc())).scalars().all()
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_usuarios.html", request, site=site, current_user=current_user, items=items)


@app.get("/admin/usuarios/novo", response_class=HTMLResponse)
async def users_new(request: Request, current_user: User = Depends(require_role("admin"))):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_usuarios_form.html", request, site=site, current_user=current_user, item=None)


@app.post("/admin/usuarios/novo")
async def users_create(
    request: Request,
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form("funcionario"),
    status_val: str = Form("ativo"),
    _: User = Depends(require_role("admin")),
):
    if role not in ("admin", "funcionario"):
        role = "funcionario"
    if status_val not in ("ativo", "inativo"):
        status_val = "ativo"
    if not username or not password:
        return RedirectResponse(url="/admin/usuarios/novo", status_code=status.HTTP_302_FOUND)
    with get_session() as db:
        exists = db.execute(select(User).where(User.username == username).limit(1)).scalar_one_or_none()
        if exists:
            return RedirectResponse(url="/admin/usuarios", status_code=status.HTTP_302_FOUND)
        u = User(username=username, password_hash=hash_password(password), role=role, status=status_val)
        db.add(u)
        db.commit()
    return RedirectResponse(url="/admin/usuarios", status_code=status.HTTP_302_FOUND)


@app.get("/admin/usuarios/editar/{id}", response_class=HTMLResponse)
async def users_edit(request: Request, id: int, current_user: User = Depends(require_role("admin"))):
    with get_session() as db:
        item = db.get(User, id)
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_usuarios_form.html", request, site=site, current_user=current_user, item=item)


@app.post("/admin/usuarios/editar/{id}")
async def users_update(
    id: int,
    username: str = Form(""),
    password: str = Form(""),
    role: str = Form("funcionario"),
    status_val: str = Form("ativo"),
    _: User = Depends(require_role("admin")),
):
    if role not in ("admin", "funcionario"):
        role = "funcionario"
    if status_val not in ("ativo", "inativo"):
        status_val = "ativo"
    with get_session() as db:
        item = db.get(User, id)
        if item:
            if username:
                item.username = username
            item.role = role
            item.status = status_val
            if password:
                item.password_hash = hash_password(password)
            db.commit()
    return RedirectResponse(url="/admin/usuarios", status_code=status.HTTP_302_FOUND)


@app.post("/admin/usuarios/excluir/{id}")
async def users_delete(id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        item = db.get(User, id)
        if item:
            db.delete(item)
            db.commit()
    return RedirectResponse(url="/admin/usuarios", status_code=status.HTTP_302_FOUND)


# ---------------------- Util ----------------------
def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text


# ---------------------- Público: Suítes ----------------------
@app.get("/suites", response_class=HTMLResponse)
async def suites_public_list(request: Request):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        tipos = db.execute(select(TipoSuite).order_by(TipoSuite.ordem.asc(), TipoSuite.nome.asc())).scalars().all()
        suites = db.execute(select(Suite).options(selectinload(Suite.tipo)).order_by(Suite.ordem.asc(), Suite.titulo.asc())).scalars().all()
    return _render("suites.html", request, site=site, tipos=tipos, suites=suites)


@app.get("/suites/{slug}", response_class=HTMLResponse)
async def suite_public_detail(request: Request, slug: str):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        suite = db.execute(
            select(Suite)
            .where(Suite.slug == slug)
            .options(selectinload(Suite.tipo), selectinload(Suite.amenidades))
        ).scalar_one_or_none()
        fotos = []
        if suite:
            fotos = db.execute(
                select(Foto).where(Foto.suite_id == suite.id).order_by(Foto.capa.desc(), Foto.ordem.asc())
            ).scalars().all()
    return _render("suite_detail.html", request, site=site, suite=suite, fotos=fotos)


# ---------------------- Público: Quartos (com painéis) ----------------------
@app.get("/apartamentos", response_class=HTMLResponse)
async def apartamentos_public_list(request: Request):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
        suites = db.execute(
            select(Suite)
            .options(selectinload(Suite.tipo))
            .order_by(Suite.destaque.desc(), Suite.ordem.asc(), Suite.titulo.asc())
        ).scalars().all()
        suite_ids = [s.id for s in suites]
        cover_map: dict[int, Foto | None] = {}
        amen_map: dict[int, list[str]] = {}
        for s in suites:
            f = db.execute(
                select(Foto).where(Foto.suite_id == s.id).order_by(Foto.capa.desc(), Foto.ordem.asc())
            ).scalars().first()
            cover_map[s.id] = f
        if suite_ids:
            # coletar amenidades por suíte
            from .models import suite_amenidade
            rows = db.execute(
                select(suite_amenidade.c.suite_id, Amenidade.nome)
                .join(Amenidade, Amenidade.id == suite_amenidade.c.amenidade_id)
                .where(suite_amenidade.c.suite_id.in_(suite_ids))
                .order_by(Amenidade.nome.asc())
            ).all()
            for sid, anome in rows:
                amen_map.setdefault(sid, []).append(anome)

        fotos_apartamentos: list[dict[str, str]] = []

        if fotos_apartamentos_web_dir.exists() and fotos_apartamentos_web_dir.is_dir():
            exts = {".webp", ".jpg", ".jpeg", ".png", ".gif"}
            for p in fotos_apartamentos_web_dir.iterdir():
                if not (p.is_file() and p.suffix.lower() in exts):
                    continue
                if p.suffix.lower() == ".webp" and p.stem.endswith("-600"):
                    continue

                src = f"/fotos-apartamentos-web/{p.name}"
                thumb_path = p.with_name(f"{p.stem}-600{p.suffix}")
                thumb = (
                    f"/fotos-apartamentos-web/{thumb_path.name}"
                    if thumb_path.exists()
                    else src
                )

                srcset = f"{thumb} 600w, {src} 1600w" if thumb != src else f"{src} 1600w"
                fotos_apartamentos.append({"src": src, "thumb": thumb, "srcset": srcset})
        elif fotos_apartamentos_dir.exists() and fotos_apartamentos_dir.is_dir():
            exts = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
            for p in fotos_apartamentos_dir.iterdir():
                if p.is_file() and p.suffix.lower() in exts:
                    src = f"/fotos-apartamentos/{p.name}"
                    fotos_apartamentos.append({"src": src, "thumb": src, "srcset": src})
        random.shuffle(fotos_apartamentos)

        return _render(
            "quartos.html",
            request,
            site=site,
            suites=suites,
            cover_map=cover_map,
            amen_map=amen_map,
            fotos_apartamentos=fotos_apartamentos,
        )


@app.get("/quartos")
async def quartos_redirect() -> Response:
    return RedirectResponse(url="/apartamentos", status_code=status.HTTP_301_MOVED_PERMANENTLY)


# ---------------------- Admin: Funcionários ----------------------
@app.get("/admin/funcionarios", response_class=HTMLResponse)
async def funcionarios_list(request: Request, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        items = db.execute(select(Funcionario).order_by(Funcionario.ordem.asc(), Funcionario.nome.asc())).scalars().all()
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_funcionarios.html", request, site=site, items=items)


@app.get("/admin/funcionarios/novo", response_class=HTMLResponse)
async def funcionarios_new(request: Request, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_funcionarios_form.html", request, site=site, item=None)


@app.post("/admin/funcionarios/novo")
async def funcionarios_create(
    nome: str = Form(""),
    cargo: str = Form(""),
    telefone: str = Form(""),
    whatsapp: str = Form(""),
    email: str = Form(""),
    status_val: str = Form("ativo"),
    ordem: int = Form(0),
    _: User = Depends(require_role("admin")),
):
    if status_val not in ("ativo", "inativo"):
        status_val = "ativo"
    with get_session() as db:
        f = Funcionario(
            nome=nome,
            cargo=cargo or None,
            telefone=telefone or None,
            whatsapp=whatsapp or None,
            email=email or None,
            status=status_val,
            ordem=ordem or 0,
        )
        db.add(f)
        db.commit()
    return RedirectResponse(url="/admin/funcionarios", status_code=status.HTTP_302_FOUND)


@app.get("/admin/funcionarios/editar/{id}", response_class=HTMLResponse)
async def funcionarios_edit(request: Request, id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        item = db.get(Funcionario, id)
        site = db.execute(select(SiteConfig).limit(1)).scalar_one_or_none()
    return _render("admin_funcionarios_form.html", request, site=site, item=item)


@app.post("/admin/funcionarios/editar/{id}")
async def funcionarios_update(
    id: int,
    nome: str = Form(""),
    cargo: str = Form(""),
    telefone: str = Form(""),
    whatsapp: str = Form(""),
    email: str = Form(""),
    status_val: str = Form("ativo"),
    ordem: int = Form(0),
    _: User = Depends(require_role("admin")),
):
    if status_val not in ("ativo", "inativo"):
        status_val = "ativo"
    with get_session() as db:
        item = db.get(Funcionario, id)
        if item:
            item.nome = nome
            item.cargo = cargo or None
            item.telefone = telefone or None
            item.whatsapp = whatsapp or None
            item.email = email or None
            item.status = status_val
            item.ordem = ordem or 0
            db.commit()
    return RedirectResponse(url="/admin/funcionarios", status_code=status.HTTP_302_FOUND)


@app.post("/admin/funcionarios/excluir/{id}")
async def funcionarios_delete(id: int, _: User = Depends(require_role("admin"))):
    with get_session() as db:
        item = db.get(Funcionario, id)
        if item:
            db.delete(item)
            db.commit()
    return RedirectResponse(url="/admin/funcionarios", status_code=status.HTTP_302_FOUND)

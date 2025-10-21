# Motel Bela Vista — Site (FastAPI + Jinja)

Projeto institucional para o Motel Bela Vista (Rio Pardo-RS).

## Stack
- FastAPI + Jinja2
- SQLAlchemy (PostgreSQL via psycopg3)
- Uvicorn
- Deploy: Render

## Variáveis de ambiente
- DATABASE_URL (ex.: postgresql+psycopg://user:pass@host:5432/db?sslmode=require)
- ADMIN_USER, ADMIN_PASS

## Desenvolvimento
```bash
py -3.13 -m pip install -r requirements.txt
$env:DATABASE_URL="postgresql+psycopg://postgres:postgres@localhost:5432/belavista"
$env:ADMIN_USER="admin"
$env:ADMIN_PASS="senha"
py -3.13 -m uvicorn app.main:app --reload --port 8001
```

## Estrutura
- app/
  - main.py, models.py, database.py, auth.py
  - templates/ (Jinja)
  - static/

## Rotas
- Público: `/`, `/suites`, `/suites/{slug}`, `/sobre`, `/contato`
- Admin (Basic Auth): `/admin/tipos`, `/admin/suites`, `/admin/amenidades`, `/admin/fotos`, `/config`

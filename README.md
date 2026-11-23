# MerchantAI — Week 1: Foundations

Implements the Week 1 slice of the roadmap (see `docs/architecture/MerchantAI-Architecture-v1.md`):

- Monorepo scaffold (`apps/api`, `apps/dashboard`, `packages/types`)
- Postgres schema + Alembic migrations for tenancy (`merchants`, `users`, `api_keys`)
- Row-Level Security enforced per `merchant_id`
- Auth & tenancy: JWT login/refresh, `/auth/me`, tenant context middleware
- Docker Compose local environment (Postgres, Redis, Qdrant, API, Dashboard)
- Dashboard shell: login page + empty authenticated shell (sidebar nav, no feature pages yet)

**Exit criteria for this slice:** a merchant admin can log in, receive a JWT, and see the empty
dashboard shell with tenant-scoped identity resolved end-to-end.

## Running it locally

```bash
cp .env.example .env
docker compose up --build
```

- API: http://localhost:8000 (docs at `/docs`)
- Dashboard: http://localhost:3000
- Postgres: localhost:5432
- Qdrant: http://localhost:6333
- Redis: localhost:6379

On first boot, run migrations and seed a demo merchant + admin user:

```bash
docker compose exec api alembic upgrade head
docker compose exec api python -m core.seed
```

Seeded login: `admin@demo-merchant.test` / `changeme123`

## What's deliberately NOT in this slice

Per the roadmap, product import, documents, Knowledge Graph, AI Engine, widget, and analytics
land in Weeks 2–7. This slice only proves the tenancy/auth spine everything else builds on.

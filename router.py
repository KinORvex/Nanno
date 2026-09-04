"""Agrega todos os routers de endpoints da v1 em um unico APIRouter."""
from fastapi import APIRouter

from app.api.v1.endpoints import (
    analyze,
    auth,
    cultures,
    digital_twin,
    experiments,
    forecast,
    images,
    observations,
    projects,
    trends,
)

api_router = APIRouter()
api_router.include_router(auth.router)      # rotas publicas: /auth/register, /auth/login, /auth/refresh
api_router.include_router(projects.router)  # CRUD de AnalysisProject
api_router.include_router(analyze.router)   # POST /analyze (pipeline original, inalterado)
api_router.include_router(trends.router)    # GET /trends/{project_id}
api_router.include_router(images.router)    # upload/download avulso de imagens
api_router.include_router(forecast.router)  # POST /projects/{project_id}/forecast (calculo explicito)

# --- Adicionado nesta etapa: Experiment / Culture / Observation / Digital Twin ---
api_router.include_router(experiments.router)         # POST/GET /projects/{project_id}/experiments
api_router.include_router(experiments.detail_router)  # GET/PATCH /experiments/{id}
api_router.include_router(cultures.router)            # POST/GET /experiments/{id}/cultures
api_router.include_router(cultures.detail_router)     # GET /cultures/{id}, /cultures/{id}/history, /cultures/compare
api_router.include_router(observations.router)        # POST/GET /cultures/{id}/observations
api_router.include_router(observations.image_router)  # POST /observations/{id}/images, GET /observations/{id}/analyses
api_router.include_router(digital_twin.router)         # /cultures/{id}/digital-twin, /stress-assessment, /predictions

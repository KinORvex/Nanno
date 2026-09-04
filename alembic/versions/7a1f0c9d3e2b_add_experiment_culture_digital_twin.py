"""add experiment, culture, observation, image_analysis, digital_twin_state, prediction

Revision ID: 7a1f0c9d3e2b
Revises: 49da4b9e0f47
Create Date: 2026-08-26

Migration ADITIVA: cria tabelas novas e adiciona UMA coluna nullable em uma
tabela existente (microalgae_images.observation_id). Nenhuma tabela ou
coluna existente é removida, renomeada ou tem seu tipo alterado. O pipeline
/analyze (e qualquer linha já existente em microalgae_images) continua
funcionando sem nenhuma alteração de comportamento.

NÃO rode `alembic upgrade head` sem antes validar esta migration em um
ambiente de staging/cópia do banco.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "7a1f0c9d3e2b"
down_revision = "49da4b9e0f47"
branch_labels = None
depends_on = None


def _uuid_pk_column() -> sa.Column:
    """Réplica exata do UUIDPKMixin usado em todos os models existentes."""
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.text("gen_random_uuid()"),
        primary_key=True,
    )


def _timestamp_columns() -> list[sa.Column]:
    """Réplica exata do TimestampMixin usado em todos os models existentes."""
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    ]


def upgrade() -> None:
    bind = op.get_bind()

    # --- Novos tipos ENUM Postgres ---
    experiment_status_enum = postgresql.ENUM(
        "planning", "active", "completed", "aborted", name="experiment_status_enum"
    )
    experiment_status_enum.create(bind, checkfirst=True)

    health_status_enum = postgresql.ENUM(
        "unknown", "normal", "warning", "stressed", name="health_status_enum"
    )
    health_status_enum.create(bind, checkfirst=True)

    # Versões de referência (create_type=False) para uso nas colunas abaixo:
    # evita que op.create_table tente criar o tipo novamente (Alembic invoca
    # os eventos DDL da tabela com checkfirst=False), o que causaria
    # DuplicateObject já que o tipo acabou de ser criado explicitamente acima.
    experiment_status_enum_ref = postgresql.ENUM(
        "planning", "active", "completed", "aborted",
        name="experiment_status_enum", create_type=False,
    )
    health_status_enum_ref = postgresql.ENUM(
        "unknown", "normal", "warning", "stressed",
        name="health_status_enum", create_type=False,
    )

    # Tipos ENUM já existentes (criados pela migration 49da4b9e0f47) —
    # reutilizados SEM recriar o tipo (create_type=False evita "type already exists").
    processing_status_enum = postgresql.ENUM(
        "PENDING", "PROCESSING", "COMPLETED", "FAILED",
        name="processing_status_enum", create_type=False,
    )
    trend_metric_enum = postgresql.ENUM(
        "CELL_COUNT", "AVG_CELL_SIZE", "CELL_DENSITY",
        name="trend_metric_enum", create_type=False,
    )

    # --- experiments ---
    op.create_table(
        "experiments",
        _uuid_pk_column(),
        *_timestamp_columns(),
        sa.Column(
            "project_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("analysis_projects.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hypothesis", sa.Text(), nullable=True),
        sa.Column("status", experiment_status_enum_ref, nullable=False, server_default="planning"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_experiments_project_id", "experiments", ["project_id"])

    # --- cultures ---
    op.create_table(
        "cultures",
        _uuid_pk_column(),
        *_timestamp_columns(),
        sa.Column(
            "experiment_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("experiments.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("label", sa.String(50), nullable=False),
        sa.Column("condition_label", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stress_induced_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_cultures_experiment_id", "cultures", ["experiment_id"])

    # --- observations ---
    op.create_table(
        "observations",
        _uuid_pk_column(),
        *_timestamp_columns(),
        sa.Column(
            "culture_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cultures.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("relative_hours", sa.Float(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "environmental_reading_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("environmental_readings.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_observations_culture_id", "observations", ["culture_id"])
    op.create_index("ix_observations_observed_at", "observations", ["observed_at"])

    # --- microalgae_images: UMA coluna aditiva (nullable) — NAO destrutivo.
    # Imagens já existentes (e o endpoint /analyze, inalterado) continuam
    # funcionando normalmente com este campo NULL.
    op.add_column(
        "microalgae_images",
        sa.Column(
            "observation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("observations.id", ondelete="SET NULL"), nullable=True,
        ),
    )
    op.create_index("ix_microalgae_images_observation_id", "microalgae_images", ["observation_id"])

    # --- image_analyses ---
    op.create_table(
        "image_analyses",
        _uuid_pk_column(),
        *_timestamp_columns(),
        sa.Column(
            "image_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("microalgae_images.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "observation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("observations.id", ondelete="CASCADE"), nullable=True,
        ),
        sa.Column("status", processing_status_enum, nullable=False, server_default="PENDING"),
        sa.Column("processing_error", sa.String(2000), nullable=True),
        sa.Column("algorithm_name", sa.String(120), nullable=False, server_default="nannochloropsis_watershed"),
        sa.Column("algorithm_version", sa.String(40), nullable=False, server_default="v1"),
        sa.Column("preprocessing_version", sa.String(40), nullable=True),
        sa.Column("segmentation_version", sa.String(40), nullable=True),
        sa.Column("parameters", sa.JSON(), nullable=True),
        sa.Column("metrics", sa.JSON(), nullable=True),
    )
    op.create_index("ix_image_analyses_image_id", "image_analyses", ["image_id"])
    op.create_index("ix_image_analyses_observation_id", "image_analyses", ["observation_id"])
    op.create_index("ix_image_analyses_status", "image_analyses", ["status"])

    # --- digital_twin_states ---
    op.create_table(
        "digital_twin_states",
        _uuid_pk_column(),
        *_timestamp_columns(),
        sa.Column(
            "culture_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cultures.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column(
            "based_on_observation_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("observations.id", ondelete="SET NULL"), nullable=True,
        ),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("biomass_estimate", sa.Float(), nullable=True),
        sa.Column("density_estimate", sa.Float(), nullable=True),
        sa.Column("morphological_state", sa.JSON(), nullable=True),
        sa.Column("environmental_state", sa.JSON(), nullable=True),
        sa.Column("growth_state", sa.String(30), nullable=True),
        sa.Column("health_status", health_status_enum_ref, nullable=False, server_default="unknown"),
        sa.Column("stress_score", sa.Float(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("contributing_factors", sa.JSON(), nullable=True),
    )
    op.create_index("ix_digital_twin_states_culture_id", "digital_twin_states", ["culture_id"])
    op.create_index("ix_digital_twin_states_computed_at", "digital_twin_states", ["computed_at"])

    # --- predictions ---
    op.create_table(
        "predictions",
        _uuid_pk_column(),
        *_timestamp_columns(),
        sa.Column(
            "culture_id", postgresql.UUID(as_uuid=True),
            sa.ForeignKey("cultures.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("target_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metric", trend_metric_enum, nullable=False),
        sa.Column("predicted_value", sa.Float(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("model_name", sa.String(120), nullable=False),
        sa.Column("model_version", sa.String(40), nullable=False),
    )
    op.create_index("ix_predictions_culture_id", "predictions", ["culture_id"])


def downgrade() -> None:
    bind = op.get_bind()

    op.drop_index("ix_predictions_culture_id", table_name="predictions")
    op.drop_table("predictions")

    op.drop_index("ix_digital_twin_states_computed_at", table_name="digital_twin_states")
    op.drop_index("ix_digital_twin_states_culture_id", table_name="digital_twin_states")
    op.drop_table("digital_twin_states")

    op.drop_index("ix_image_analyses_status", table_name="image_analyses")
    op.drop_index("ix_image_analyses_observation_id", table_name="image_analyses")
    op.drop_index("ix_image_analyses_image_id", table_name="image_analyses")
    op.drop_table("image_analyses")

    op.drop_index("ix_microalgae_images_observation_id", table_name="microalgae_images")
    op.drop_column("microalgae_images", "observation_id")

    op.drop_index("ix_observations_observed_at", table_name="observations")
    op.drop_index("ix_observations_culture_id", table_name="observations")
    op.drop_table("observations")

    op.drop_index("ix_cultures_experiment_id", table_name="cultures")
    op.drop_table("cultures")

    op.drop_index("ix_experiments_project_id", table_name="experiments")
    op.drop_table("experiments")

    # processing_status_enum e trend_metric_enum NÃO são removidos: pertencem
    # à migration 49da4b9e0f47 e ainda são usados por tabelas dela.
    postgresql.ENUM(name="health_status_enum").drop(bind, checkfirst=True)
    postgresql.ENUM(name="experiment_status_enum").drop(bind, checkfirst=True)

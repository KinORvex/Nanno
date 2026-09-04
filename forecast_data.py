"""
Ponte entre o banco de dados e o módulo de ML: agrega imagens processadas e
leituras ambientais de um projeto em uma série temporal diária, no formato
esperado por `app.ml.dataset.build_feature_matrix`.

Mantido fora de `app/ml/` propositalmente — o pacote de ML não deve conhecer
SQLAlchemy/sessões de banco, apenas arrays NumPy, o que facilita testar o
modelo isoladamente (ex.: em notebooks de treino) sem subir um Postgres.
"""
import uuid
from typing import List

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.environment import EnvironmentalReading
from app.models.image import MicroalgaeImage, ProcessingStatus


def get_daily_time_series(db: Session, project_id: uuid.UUID) -> List[dict]:
    """
    Retorna uma lista ordenada cronologicamente de dicionários — um por dia
    com pelo menos uma imagem processada ou leitura ambiental — prontos para
    `app.ml.dataset.build_feature_matrix`. Dias sem uma das duas fontes ficam
    com `None` nos campos correspondentes (a interpolação cuida do resto).
    """
    image_day = func.date(func.coalesce(MicroalgaeImage.captured_at, MicroalgaeImage.created_at))
    image_rows = (
        db.query(
            image_day.label("day"),
            func.avg(MicroalgaeImage.cell_density_cells_per_ml).label("cell_density_cells_per_ml"),
            func.avg(MicroalgaeImage.avg_cell_diameter_um).label("avg_cell_diameter_um"),
        )
        .filter(
            MicroalgaeImage.project_id == project_id,
            MicroalgaeImage.processing_status == ProcessingStatus.COMPLETED,
            MicroalgaeImage.cell_density_cells_per_ml.isnot(None),
        )
        .group_by(image_day)
        .all()
    )

    env_day = func.date(EnvironmentalReading.recorded_at)
    env_rows = (
        db.query(
            env_day.label("day"),
            func.avg(EnvironmentalReading.temperature_c).label("temperature_c"),
            func.avg(EnvironmentalReading.ph).label("ph"),
            func.avg(EnvironmentalReading.light_intensity_umol_m2_s).label("light_intensity_umol_m2_s"),
        )
        .filter(EnvironmentalReading.project_id == project_id)
        .group_by(env_day)
        .all()
    )

    by_day: dict = {}
    for row in image_rows:
        by_day.setdefault(row.day, {})
        by_day[row.day]["cell_density_cells_per_ml"] = row.cell_density_cells_per_ml
        by_day[row.day]["avg_cell_diameter_um"] = row.avg_cell_diameter_um
    for row in env_rows:
        by_day.setdefault(row.day, {})
        by_day[row.day]["temperature_c"] = row.temperature_c
        by_day[row.day]["ph"] = row.ph
        by_day[row.day]["light_intensity_umol_m2_s"] = row.light_intensity_umol_m2_s

    records = []
    for day in sorted(by_day.keys()):
        record = by_day[day]
        records.append(
            {
                "date": day,
                "cell_density_cells_per_ml": record.get("cell_density_cells_per_ml"),
                "avg_cell_diameter_um": record.get("avg_cell_diameter_um"),
                "temperature_c": record.get("temperature_c"),
                "ph": record.get("ph"),
                "light_intensity_umol_m2_s": record.get("light_intensity_umol_m2_s"),
            }
        )
    return records

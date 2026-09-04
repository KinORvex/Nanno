# Nannochloropsis Image Analysis API

API para análise de imagens de microscopia de microalgas (*Nannochloropsis*):
upload de imagens no S3, contagem/tamanho de células e estimativas de tendência
por projeto de cultivo.

## Estrutura do projeto

```
app/
├── main.py                    # instancia o FastAPI, middlewares, routers, health check
├── core/
│   ├── config.py               # Settings (pydantic-settings) lidas do .env
│   ├── database.py             # engine, SessionLocal, Base, get_db()
│   ├── security.py             # hash de senha (bcrypt) + emissão/validação de JWT
│   └── exception_handlers.py   # traduz exceções de domínio em respostas HTTP
├── models/                     # SQLAlchemy ORM (ver seção "Modelo de dados")
│   ├── mixins.py                # UUIDPKMixin, TimestampMixin
│   ├── user.py                  # User
│   ├── project.py               # AnalysisProject
│   ├── image.py                 # MicroalgaeImage
│   └── trend.py                 # TrendEstimate
├── schemas/                    # DTOs Pydantic (request/response)
│   └── image.py
├── services/
│   ├── exceptions.py            # exceções de domínio (Storage*, InvalidFileError)
│   ├── s3_service.py            # S3Service: upload/download/presigned URL/delete
│   └── cell_analysis/           # pipeline de visão computacional (OpenCV + scikit-image)
│       ├── config.py             # CellDetectionParams (calibração, thresholds)
│       ├── preprocessing.py      # normalização, remoção de ruído, CLAHE
│       ├── segmentation.py       # threshold + watershed (separa células que se tocam)
│       ├── metrics.py            # contagem, área/diâmetro por célula, resumo estatístico
│       ├── visualization.py      # desenha bounding circles + contador na imagem
│       ├── pipeline.py           # orquestra as etapas acima (não depende de S3/DB)
│       └── s3_integration.py     # baixa original do S3, roda o pipeline, sobe anotada
├── crud/                       # (a implementar) camada de acesso a dados por model
└── api/
    ├── deps.py                  # get_db, get_current_user (JWT)
    └── v1/
        ├── router.py             # agrega todos os endpoints da v1
        └── endpoints/
            └── images.py         # upload / download-url / delete de imagens
requirements.txt
.env.example
```

## Modelo de dados

| Tabela               | Descrição                                                                 |
|-----------------------|----------------------------------------------------------------------------|
| `users`               | Contas de usuário; senha armazenada como hash bcrypt, autenticação via JWT |
| `analysis_projects`   | Sessão/lote de análise (ex.: "Cultivo Tanque 3"), pertence a um usuário    |
| `microalgae_images`   | Metadados de cada imagem enviada + métricas extraídas (contagem, tamanho)  |
| `trend_estimates`     | Tendências agregadas por período (ex.: crescimento populacional semanal)   |

Relacionamentos: `User 1—N AnalysisProject 1—N MicroalgaeImage`, e
`AnalysisProject 1—N TrendEstimate`. Todas as FKs usam `ON DELETE CASCADE`.

## Como rodar

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # preencha as credenciais reais

# Cria as extensões necessárias (uma vez, no banco de destino):
#   CREATE EXTENSION IF NOT EXISTS pgcrypto;

# Gera e aplica a primeira migration
alembic init alembic   # se ainda não existir
# configure alembic/env.py para importar app.models.Base.metadata e settings.DATABASE_URI
alembic revision --autogenerate -m "initial schema"
alembic upgrade head

uvicorn app.main:app --reload
```

A documentação interativa fica em `http://localhost:8000/docs` (desabilitada
automaticamente quando `ENVIRONMENT=production`).

## Endpoints principais

Convenção de versionamento: todas as rotas ficam sob `settings.API_V1_PREFIX`
(`/api/v1` por padrão). Os nomes pedidos como `/api/analyze` correspondem,
neste projeto, a `/api/v1/analyze` — ajuste `API_V1_PREFIX=""` no `.env` se
precisar do caminho sem versionamento.

| Método | Rota                                   | Auth | Descrição |
|--------|------------------------------------------|:---:|-----------|
| POST   | `/api/v1/auth/register`                  | ❌  | Cria uma conta de usuário |
| POST   | `/api/v1/auth/login`                     | ❌  | Login (`OAuth2PasswordRequestForm`: `username`=e-mail) → access + refresh token |
| POST   | `/api/v1/auth/refresh`                   | ❌  | Troca um refresh token válido por um novo par |
| POST   | `/api/v1/analyze`                        | ✅  | Upload de imagem (multipart) → S3 → pipeline CV → Postgres → contagem/distribuição de tamanhos |
| GET    | `/api/v1/trends/{project_id}`            | ✅  | Estimativas de tendência (lê as persistidas; calcula uma nova se não houver, ou com `?refresh=true`) |
| POST   | `/api/v1/projects/{project_id}/forecast` | ✅  | Força o cálculo de uma nova previsão (variante de escrita de `/trends`) |
| POST   | `/api/v1/images/projects/{project_id}/upload` | ✅ | Upload avulso no S3, sem rodar o pipeline de CV |
| GET    | `/api/v1/images/{image_id}/download-url` | ✅  | URL pré-assinada de download |
| DELETE | `/api/v1/images/{image_id}`              | ✅  | Remove imagem do S3 + banco |
| GET    | `/health`                                | ❌  | Health check |

Todas as rotas marcadas com ✅ exigem `Authorization: Bearer <access_token>`
(injetado via `Depends(get_current_user)` em `app/api/deps.py`). O Swagger UI
(`/docs`) já expõe o botão **Authorize** para colar o token e testar as rotas
protegidas diretamente pela documentação interativa.

### Exemplo de uso end-to-end

```bash
# 1. Registrar e logar
curl -X POST /api/v1/auth/register -H "Content-Type: application/json" \
  -d '{"email":"lab@exemplo.com","password":"senha-segura-123","full_name":"Lab"}'

curl -X POST /api/v1/auth/login -d "username=lab@exemplo.com&password=senha-segura-123"
# -> {"access_token": "...", "refresh_token": "...", "token_type": "bearer"}

# 2. Enviar uma imagem para análise (requer um AnalysisProject já criado)
curl -X POST /api/v1/analyze \
  -H "Authorization: Bearer <access_token>" \
  -F "project_id=<uuid-do-projeto>" \
  -F "microns_per_pixel=0.15" \
  -F "file=@amostra.png"

# 3. Consultar a tendência populacional (calcula automaticamente se necessário)
curl -X GET "/api/v1/trends/<uuid-do-projeto>" \
  -H "Authorization: Bearer <access_token>"
```

## Módulo de análise de imagens (`app/services/cell_analysis`)

Pipeline de visão computacional para Nannochloropsis, usando OpenCV + scikit-image:

1. **Pré-processamento** (`preprocessing.py`) — escala de cinza, normalização
   de intensidade, remoção de ruído (median blur + fastNlMeansDenoising) e
   realce de contraste local via CLAHE.
2. **Segmentação** (`segmentation.py`) — limiarização (Otsu ou adaptativa) +
   limpeza morfológica + transformada de distância + **watershed**, que
   separa corretamente células que se tocam (comum em amostras densas).
3. **Contagem e medição** (`metrics.py`) — `skimage.measure.regionprops`
   extrai área, diâmetro equivalente, perímetro, excentricidade e solidez de
   cada célula; regiões fora da faixa de área esperada ou com solidez baixa
   (debris irregular) são descartadas.
4. **Resumo estatístico** — média, mediana, desvio padrão, min/max e
   percentis 25/75 do diâmetro e da área, mais um `avg_confidence_score`
   (solidez média, usado como proxy de qualidade da segmentação).
5. **Visualização** (`visualization.py`) — desenha um círculo delimitador em
   cada célula detectada e um contador no canto da imagem.

### Uso direto (sem S3)

```python
from app.services.cell_analysis import analyze_nannochloropsis_image, CellDetectionParams

# microns_per_pixel é OBRIGATÓRIO calibrar para a objetiva/câmera real
params = CellDetectionParams(microns_per_pixel=0.15)

result = analyze_nannochloropsis_image(image_bytes, params=params)
json_payload = result.to_dict()             # {"cell_count": ..., "summary": {...}, "measurements": [...]}
annotated_png = result.annotated_image_bytes  # bytes prontos para upload
```

### Uso integrado ao S3

```python
from app.services.cell_analysis import analyze_image_from_s3

payload = analyze_image_from_s3(source_key="project_id/abc-imagem.png")
# payload inclui cell_count, summary, measurements, annotated_s3_key, annotated_s3_bucket
```

Este é o ponto de entrada recomendado para o worker de background (Celery/RQ)
mencionado na seção de modelo de dados: ele consome imagens `PENDING`, chama
`analyze_image_from_s3`, e faz o PATCH de `MicroalgaeImage` com
`cell_count`, `avg_cell_diameter_um` (de `summary["diameter_um"]["mean"]`),
`std_cell_diameter_um`, `cell_density_cells_per_ml`, `confidence_score` e
`extra_metrics` (o payload completo, incluindo `measurements`).

**Importante — calibração**: `microns_per_pixel` depende da objetiva e da
câmera do microscópio e deve ser determinado com uma lâmina micrométrica
antes de usar o sistema em produção; um valor incorreto invalida todas as
medidas de tamanho (a contagem de células continua válida, pois independe da escala).

## Módulo de IA — previsão de tendência populacional (`app/ml`)

Modelo PyTorch que prevê a densidade celular futura a partir do histórico de
`[densidade celular, diâmetro médio, temperatura, pH, luminosidade]`.

- **Arquitetura** (`model.py`): `LSTMForecaster` (padrão) recebe uma janela de
  `input_window` dias e prevê os próximos `forecast_horizon` dias de uma vez
  (multi-step direto, não autoregressivo). `MLPForecaster` é um baseline mais
  simples (achata a janela), útil quando o histórico é curto.
- **Dados** (`dataset.py`, puro NumPy — sem PyTorch): interpolação linear de
  valores ausentes, normalização z-score ajustada só no treino (evita
  vazamento de dados) e janelamento deslizante temporal.
- **Treino** (`train.py`): split treino/validação respeitando a ordem
  cronológica (a validação é sempre o trecho mais recente), early stopping,
  gradient clipping, checkpoint com os melhores pesos observados.
- **Inferência** (`inference.py`): `ForecastModelRegistry` mantém o modelo
  carregado em memória (singleton). A incerteza é estimada via **MC-Dropout**
  (múltiplas passagens com dropout ativo na cabeça da rede), gerando um
  intervalo de confiança (percentis 10/90) em torno da previsão pontual.
- **Ponte com o banco** (`app/services/forecast_data.py`): agrega
  `MicroalgaeImage` + `EnvironmentalReading` de um projeto em uma série diária
  — este módulo fica FORA de `app/ml` de propósito, para o pacote de ML não
  depender de SQLAlchemy e poder ser testado com um simples array NumPy.

### Treinando o modelo

```bash
python -m scripts.train_forecaster --project-id <uuid-do-projeto>
```

Requer um projeto com histórico suficiente: pelo menos
`input_window + forecast_horizon` dias com dados (padrão: 14 + 7 = 21 dias).
Gera `app/ml/artifacts/nanno_forecaster.pt`.

### Endpoint de previsão

```
POST /api/v1/projects/{project_id}/forecast
Authorization: Bearer <jwt>

{
  "forecast_horizon_days": 7,       // opcional; não pode exceder o horizonte treinado
  "persist_as_trend_estimate": true // salva o resultado em TrendEstimate
}
```

Retorna a previsão pontual, intervalo de confiança, direção da tendência
(`increasing`/`decreasing`/`stable`) e variação percentual. Erros tratados:
`422` (histórico insuficiente ou horizonte maior que o treinado) e `503`
(nenhum modelo treinado ainda neste ambiente).

**Limitação conhecida do MC-Dropout**: o dropout interno do `nn.LSTM` não é
perturbado (não é exposto como submódulo `nn.Dropout` pelo PyTorch); a
incerteza estimada reflete apenas a variação induzida na cabeça da rede —
ainda útil, mas conservadora.

## Notas de produção

- **boto3 é síncrono**: os endpoints chamam `S3Service` via
  `starlette.concurrency.run_in_threadpool` para não bloquear o event loop.
  Em alta escala, considere migrar para `aioboto3`.
- **Criptografia em repouso**: uploads usam `ServerSideEncryption=AES256` por padrão.
- **Chaves de S3** são organizadas por `project_id/` para permitir listagem
  eficiente por prefixo e evitar colisão de nomes.
- **Processamento assíncrono**: o pipeline de contagem/medição de células não
  roda na requisição de upload — a imagem é salva com `processing_status=PENDING`
  e uma task de background (Celery/RQ/SQS) deve consumir a fila e fazer o
  PATCH das métricas usando `MicroalgaeImageMetricsUpdate`.
- **Segurança**: nunca comitar `.env`; `SECRET_KEY` deve ser um valor
  aleatório de alta entropia gerado por ambiente (ex.: `openssl rand -hex 32`).

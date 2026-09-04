"""Exceções específicas do pipeline de análise de imagens de microalgas."""


class CellAnalysisError(Exception):
    """Erro base do módulo de análise de células — não instanciar diretamente."""


class InvalidImageError(CellAnalysisError):
    """A imagem está corrompida, vazia, ou não pôde ser decodificada."""


class SegmentationError(CellAnalysisError):
    """Falha durante a etapa de segmentação (watershed/threshold)."""

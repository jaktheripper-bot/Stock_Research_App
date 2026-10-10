"""
Anvik Cortex Engine
===================
Proprietary Institutional Quantitative Architecture for Indian Financial Markets.
"""

from core.cortex.engine import (
    DynamicStatutoryYieldWedge,
    StatutoryYieldWedgeResult,
    ReverseDcfHurdleDeconstruct,
    ReverseDcfHurdleResult,
    PeadQuantDriftVelocity,
    PeadDriftVelocityResult,
    FiduciaryGovernanceScoringIndex,
    FiduciaryGovernanceResult,
    AnvikCortexEngine,
    CortexCompositeEvaluation,
)
from core.cortex.chanakya import (
    ChanakyaGate,
    ChanakyaResult,
    ChanakyaCheckResult,
)
from core.cortex.varan import (
    VaranEngine,
    VaranDeltaPacket,
    DuPontAnalysis,
    WorkingCapitalCycle,
    FinancialCAGRs,
    CapitalReturnsSummary,
)
from core.cortex.setu import (
    SetuMatrixEngine,
    SetuMatrixResult,
    CapitalTranche,
    CapitalStructureAnomaly,
)
from core.cortex.garuda import (
    GarudaReflexEngine,
    MicroSnapshotDelta,
)
from core.cortex.sutra import (
    SutraLookThroughEngine,
    SutraLookThroughResult,
    ConsolidatedStockExposure,
    SectorExposure,
    CapitalAllocationHierarchy,
)

__all__ = [
    # Core Cortex
    "DynamicStatutoryYieldWedge",
    "StatutoryYieldWedgeResult",
    "ReverseDcfHurdleDeconstruct",
    "ReverseDcfHurdleResult",
    "PeadQuantDriftVelocity",
    "PeadDriftVelocityResult",
    "FiduciaryGovernanceScoringIndex",
    "FiduciaryGovernanceResult",
    "AnvikCortexEngine",
    "CortexCompositeEvaluation",
    # Phase 1: Chanakya
    "ChanakyaGate",
    "ChanakyaResult",
    "ChanakyaCheckResult",
    # Phase 2: Varan
    "VaranEngine",
    "VaranDeltaPacket",
    "DuPontAnalysis",
    "WorkingCapitalCycle",
    "FinancialCAGRs",
    "CapitalReturnsSummary",
    # Phase 3: Setu
    "SetuMatrixEngine",
    "SetuMatrixResult",
    "CapitalTranche",
    "CapitalStructureAnomaly",
    # Phase 4: Garuda
    "GarudaReflexEngine",
    "MicroSnapshotDelta",
    # Phase 5: Sutra
    "SutraLookThroughEngine",
    "SutraLookThroughResult",
    "ConsolidatedStockExposure",
    "SectorExposure",
    "CapitalAllocationHierarchy",
]


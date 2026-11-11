"""Martingale choice of the monitoring interval for VM memory, with growth detectors.

The package implements the methods of the article "Martingale approach to the choice
of the monitoring interval in the adaptive memory management of KVM virtual machines"
(A. Ferubko, Bryansk State Engineering-Technological University):

* :func:`monitoring_interval`, the interval from the Azuma-Hoeffding inequality (7)-(9);
* :class:`GrowthDetector`, :class:`CusumGrowthDetector`, betting tests valid at any
  check moment by Ville's inequality (11), (12) and (14);
* :class:`MonitoringScheduler`, the joint algorithm of Fig. 3, and the streaming
  monitors :class:`VmMonitor` and :class:`FleetMonitor`;
* :func:`estimate_c`, the estimate of the largest change from a log, and the log
  analysis :func:`analyse_log`.

Additions beyond the article are marked in the docstrings: :class:`MixtureGrowthDetector`
(a mixture of bets with no tuned fraction) and :class:`SubGaussianGrowthDetector`.
"""

from __future__ import annotations

from .analysis import (
    AnalysisOptions,
    DetectorSummary,
    GrowthSegment,
    GuaranteeCheck,
    PolicyReplay,
    VmReport,
    analyse_log,
    render_markdown,
    report_to_dict,
)
from .detectors import (
    DEFAULT_BETS,
    CusumGrowthDetector,
    GrowthDetector,
    GrowthTest,
    MixtureGrowthDetector,
    SubGaussianGrowthDetector,
)
from .estimate import estimate_c, exceedance_share
from .interval import azuma_bound, max_rise_bound, monitoring_interval
from .logs import GROWTH_PHASE, MonitoringLog, VmLog, read_log
from .monitor import FleetMonitor, VmMonitor
from .scheduler import DETECTOR_KINDS, Decision, DetectorKind, MonitoringScheduler

__version__ = "0.1.0"

__all__ = [
    "DEFAULT_BETS",
    "DETECTOR_KINDS",
    "GROWTH_PHASE",
    "AnalysisOptions",
    "CusumGrowthDetector",
    "Decision",
    "DetectorKind",
    "DetectorSummary",
    "FleetMonitor",
    "GrowthDetector",
    "GrowthSegment",
    "GrowthTest",
    "GuaranteeCheck",
    "MixtureGrowthDetector",
    "MonitoringLog",
    "MonitoringScheduler",
    "PolicyReplay",
    "SubGaussianGrowthDetector",
    "VmLog",
    "VmMonitor",
    "VmReport",
    "__version__",
    "analyse_log",
    "azuma_bound",
    "estimate_c",
    "exceedance_share",
    "max_rise_bound",
    "monitoring_interval",
    "read_log",
    "render_markdown",
    "report_to_dict",
]

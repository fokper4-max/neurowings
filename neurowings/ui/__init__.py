#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""NeuroWings UI package.

Еager imports in __init__ pulled PyQt5 before torch and ломали torch на Windows.
Оставляем ленивую загрузку, чтобы UI модули подтягивались только когда нужны.
"""

__all__ = [
    'PointItem', 'WingLabelItem', 'BBoxItem', 'MeasurementLineItem',
    'ZoomableGraphicsView', 'AnalysisWidget', 'GraphsWidget',
    'InterpretationWidget', 'GlobalInterpretationWidget',
    'BatchResultsWidget', 'PointSettingsDialog'
]


def __getattr__(name):
    if name in {'PointItem', 'WingLabelItem', 'BBoxItem', 'MeasurementLineItem'}:
        from .graphics_items import PointItem, WingLabelItem, BBoxItem, MeasurementLineItem
        return {
            'PointItem': PointItem,
            'WingLabelItem': WingLabelItem,
            'BBoxItem': BBoxItem,
            'MeasurementLineItem': MeasurementLineItem,
        }[name]
    if name == 'ZoomableGraphicsView':
        from .graphics_view import ZoomableGraphicsView
        return ZoomableGraphicsView
    if name in {'AnalysisWidget'}:
        from .analysis_widget import AnalysisWidget
        return AnalysisWidget
    if name == 'GraphsWidget':
        from .graphs_widget import GraphsWidget
        return GraphsWidget
    if name in {'InterpretationWidget', 'GlobalInterpretationWidget'}:
        from .interpretation_widget import InterpretationWidget, GlobalInterpretationWidget
        return {'InterpretationWidget': InterpretationWidget, 'GlobalInterpretationWidget': GlobalInterpretationWidget}[name]
    if name == 'BatchResultsWidget':
        from .batch_widget import BatchResultsWidget
        return BatchResultsWidget
    if name == 'PointSettingsDialog':
        from .dialogs import PointSettingsDialog
        return PointSettingsDialog
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

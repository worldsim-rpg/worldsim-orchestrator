"""
Форматирование AcquisitionPlan в читаемый текст для игрока.

Вызывается из loop._run_acquisition_turn вместо scene-master:
план — структурированные данные, не нарратив мира.
"""

from __future__ import annotations

from worldsim_schemas import AcquisitionPlan, ConflictStatus, FeasibilityStatus

_VECTOR_LABELS = {
    "information": "Информация",
    "property": "Имущество",
    "skills": "Навыки",
    "connections": "Связи",
}

_STATUS_LABELS = {
    FeasibilityStatus.FULL: "✓ Выполнимо",
    FeasibilityStatus.PARTIAL: "⚠ Частично выполнимо",
    FeasibilityStatus.BLOCKED: "✗ Заблокировано",
}


def render_acquisition_plan(plan: AcquisitionPlan) -> str:
    lines: list[str] = []

    vector_label = _VECTOR_LABELS.get(plan.vector.value, plan.vector.value)
    feasibility_label = _STATUS_LABELS.get(plan.feasibility_status, str(plan.feasibility_status))

    lines.append("═══ ПЛАН ПРИОБРЕТЕНИЯ ВОЗМОЖНОСТИ ═══")
    lines.append("")
    lines.append(f"Вектор: {vector_label}")
    lines.append(f"Выполнимость: {feasibility_label} (балл {plan.feasibility_score:.2f})")

    if plan.blocking_factor:
        lines.append(f"Причина блокировки: {plan.blocking_factor}")
        lines.append("")
        lines.append("Маршруты не построены — устрани блокирующий фактор.")
        return "\n".join(lines)

    lines.append(f"Ценность: {plan.value:.1f}  (ядро {plan.value_core:.1f} · надбавка {plan.value_bonus:.1f})")
    lines.append(f"Сложность цели: {plan.difficulty_target:.1f}")
    if plan.type_saturation_penalty > 0:
        lines.append(f"  в т.ч. штраф насыщения: +{plan.type_saturation_penalty:.1f}")
    lines.append(f"Уникальность сценария: {plan.scenario_uniqueness:.2f}")
    if plan.partial_coverage:
        lines.append("⚠ Частичное покрытие: условия ограничены, сложность снижена.")

    if plan.conflict_status == ConflictStatus.FULL_CONFLICT_PENDING:
        lines.append("")
        lines.append("⚠ КОНФЛИКТ: путь невозможен без отказа от одной из возможностей.")
        if plan.conflicting_capability_ids:
            lines.append("Конфликтующие возможности: " + ", ".join(plan.conflicting_capability_ids))
        lines.append("Сообщи, от чего готов отказаться — и план будет пересчитан.")
        return "\n".join(lines)

    if plan.conflict_status == ConflictStatus.PARTIAL_CONFLICT and plan.conflicting_capability_ids:
        lines.append("")
        lines.append("⚠ Частичный конфликт с: " + ", ".join(plan.conflicting_capability_ids))
        lines.append("Маршрут построен; конфликты остаются на твой риск.")

    if not plan.routes:
        lines.append("")
        lines.append("Маршруты не построены.")
        return "\n".join(lines)

    lines.append("")
    for i, route in enumerate(plan.routes, start=1):
        route_vector_label = _VECTOR_LABELS.get(route.vector.value, route.vector.value)
        lines.append(f"── Маршрут {i}: {route_vector_label} ──")
        lines.append(f"   Суммарная сложность: {route.total_difficulty:.1f}  (раздутие ×{route.inflation_factor:.2f})")
        lines.append(f"   Испытаний: {len(route.trials)}")
        lines.append("")
        for trial in route.trials:
            error_pct = int(trial.error_chance * 100)
            lines.append(f"   [{trial.id}] {trial.description}")
            lines.append(f"        сложность {trial.difficulty:.1f}  |  ошибка {error_pct}%  |  цена {trial.error_cost:.1f}")
        lines.append("")

    return "\n".join(lines).rstrip()

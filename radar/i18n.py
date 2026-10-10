"""E-mail strings. `language` in the config picks the table (en, es).

To add a language, copy the "en" table, translate the values and keep the keys.
"""
from __future__ import annotations

STRINGS = {
    "en": {
        "why": "Why", "gaps": "Gaps", "comp": "Compensation", "watch_out": "Watch out",
        "daily.subject": "Job radar {day}: {n} relevant posting(s)", "daily.subject_high": ", {n} strong",
        "daily.intro": ("Checked {boards} boards. New relevant today: {new}. Evaluated today: {evaluated} "
                        "({queue} left in the queue)."),
        "daily.matching": "Postings that fit", "daily.closed": "Closed (they were a fit)",
        "daily.no_data": "No data today from",
        "weekly.subject": "Weekly job search review — {day}",
        "weekly.intro": ("Last 7 days: {new} new postings passed the filter; {closed} that fit were closed. "
                         "Open with a high/medium fit: {open}. Waiting for evaluation: {queue}."),
        "weekly.where": "Where the fit concentrates", "weekly.priority": "Priority this week",
        "weekly.closed": "Closed this week", "weekly.manual": "Companies without an API (weekly check)",
        "weekly.manual_failed": "Could not check", "weekly.reminder": "Reminder",
        "footer": "Job radar. Daily sweep with evaluation; weekly review on Mondays.",
    },
    "es": {
        "why": "Por qué", "gaps": "Lagunas", "comp": "Salario", "watch_out": "Ojo",
        "daily.subject": "Radar de empleo {day}: {n} oferta(s) relevante(s)", "daily.subject_high": ", {n} de encaje alto",
        "daily.intro": ("Revisados {boards} tableros. Nuevas relevantes hoy: {new}. Evaluadas hoy: {evaluated} "
                        "(quedan {queue} en cola)."),
        "daily.matching": "Ofertas con encaje", "daily.closed": "Cerradas (tenían encaje)",
        "daily.no_data": "Sin datos hoy de",
        "weekly.subject": "Revisión semanal de la búsqueda — {day}",
        "weekly.intro": ("Últimos 7 días: {new} ofertas nuevas que pasan el filtro; {closed} con encaje se han "
                         "cerrado. Abiertas con encaje alto/medio: {open}. En cola sin evaluar: {queue}."),
        "weekly.where": "Dónde se concentra el encaje", "weekly.priority": "Prioridad para esta semana",
        "weekly.closed": "Se cerraron", "weekly.manual": "Empresas sin API (revisión semanal)",
        "weekly.manual_failed": "No se pudo revisar", "weekly.reminder": "Recordatorio",
        "footer": "Radar de empleo. Barrido diario con evaluación; revisión semanal los lunes.",
    },
}

LANGUAGE_NAMES = {"en": "English", "es": "Spanish (Spain)"}


class T:
    def __init__(self, cfg: dict):
        self.lang = cfg.get("language", "en") if cfg.get("language", "en") in STRINGS else "en"

    def __call__(self, key: str, **kw) -> str:
        s = STRINGS[self.lang].get(key) or STRINGS["en"].get(key, key)
        return s.format(**kw) if kw else s

# Сторонние компоненты

| Компонент | Источник | Коммит | Лицензия | Что взято |
|---|---|---|---|---|
| planhaus | https://github.com/pepuscz/planhaus | 5b78df6a370ce2f1cb23ea1c239351235e2718bc | MIT (`tools/planhaus/LICENSE`) | 11 скиллов → `.claude/skills/planhaus-*`, 3 агента → `.claude/agents/planhaus-*`, `scripts/room_spatial.py`, `scripts/rules/clearances.yaml`, `templates/`, `sample-project/`, `hooks/on_room_edit.py`, `docs/architecture.md` → `tools/planhaus/` |
| threejs-skills | https://github.com/cloudai-x/threejs-skills | 0e181866f095b5f06d005133876e926515390d95 | MIT (`tools/third-party-licenses/threejs-skills.LICENSE`) | 13 скиллов → `.claude/skills/threejs-*`, без изменений |
| spatial-layout-guide | https://github.com/revfactory/harness-100 (`en/77-space-concept-board`) | 8e8d35c6a19166614d1af1df85512266d51121ae | Apache-2.0 (`tools/third-party-licenses/harness-100.LICENSE`) | `.claude/skills/spatial-layout-guide/SKILL.md`; изменено описание (убраны ссылки на агентов исходного проекта) и строка про отсутствующий файл references |

Изменения в planhaus при переносе: `${CLAUDE_PLUGIN_ROOT}` заменён на `tools/planhaus`,
`/planhaus:<name>` → `/planhaus-<name>`, имена скиллов и агентов получили префикс `planhaus-`.
Не перенесены: каталог мебели (MCP-сервер, векторная БД) и скиллы select, search,
enrich-catalog, setup, migrate, агент furniture-curator, хуки плагина.

Свой код: `.claude/skills/kitchen-living-planner/`, `tools/room3d/`.

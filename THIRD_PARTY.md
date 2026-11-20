# Сторонние компоненты

| Компонент | Источник | Коммит | Лицензия | Что взято |
|---|---|---|---|---|
| planhaus | https://github.com/pepuscz/planhaus | 5b78df6a370ce2f1cb23ea1c239351235e2718bc | MIT (`tools/planhaus/LICENSE`) | 11 скиллов → `.agents/skills/planhaus-*`, 3 агента → `.agents/agents/planhaus-*`, `scripts/room_spatial.py`, `scripts/rules/clearances.yaml`, `templates/`, `sample-project/`, `hooks/on_room_edit.py`, `docs/architecture.md` → `tools/planhaus/` |
| threejs-skills | https://github.com/cloudai-x/threejs-skills | 0e181866f095b5f06d005133876e926515390d95 | MIT (`tools/third-party-licenses/threejs-skills.LICENSE`) | 13 скиллов → `.agents/skills/threejs-*`, без изменений |
| spatial-layout-guide | https://github.com/revfactory/harness-100 (`en/77-space-concept-board`) | 8e8d35c6a19166614d1af1df85512266d51121ae | Apache-2.0 (`tools/third-party-licenses/harness-100.LICENSE`) | `.agents/skills/spatial-layout-guide/SKILL.md`; изменено описание (убраны ссылки на агентов исходного проекта) и строка про отсутствующий файл references |

Изменения в planhaus при переносе: пути привязаны к `tools/planhaus`, документация адаптирована под проект,
`/planhaus:<name>` → `/planhaus-<name>`, имена скиллов и агентов получили префикс `planhaus-`.
Не перенесены: каталог мебели (MCP-сервер, векторная БД) и скиллы select, search,
enrich-catalog, setup, migrate, агент furniture-curator, хуки плагина.

Свой код: `.agents/skills/kitchen-living-planner/`, `tools/room3d/`.

## 3D-модели техники и мебели (`assets/models/`)

CAD-модели производителей, скачанные Максимом в формате .3ds и сконвертированные `tools/room3d/tds_to_glb.py`
(геометрия без изменений, цвета материалов заданы вручную). Используются только для визуализации планировки.

| Файл | Изделие |
|---|---|
| `hansgrohe-c51-f450-01.glb` | Hansgrohe C51-F450-01 sink combi 450 select, арт. 43212000 |
| `aeg-fridge-freezer-bottom-silver.glb` | AEG, холодильник с нижней морозилкой, серебристый |
| `ideal-standard-i-life-bath.glb` | Ideal Standard i-Life, прямоугольная ванна 160 × 70 см, из предоставленного файла `.3ds` |
| `duravit-luv-037960.glb` | Duravit Luv, накладная раковина 60 см, арт. 037960, из предоставленного файла `.3ds` |
| `alterna-ray-s-towel-warmer.glb` | Alterna Ray S, полотенцесушитель из предоставленного файла `.3ds` |
| `asko-t5hp117ldlw.glb` | ASKO T5HP117LDLW, сушильная машина из предоставленного файла `.max`. Экспорт из Blender, сетка упрощена, материалы воссозданы вручную. |

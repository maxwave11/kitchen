# room3d — 3D-вьюер комнаты

`build_room_3d.py` берёт комнату в формате planhaus, считает геометрию тем же движком
(`tools/planhaus/scripts/room_spatial.py --json`) и пишет один HTML-файл на three.js 0.169
(подключается с cdn.jsdelivr.net): стены с проёмами, окна, двери с дугой открывания,
кухонные модули со столешницей и верхними шкафами, мебель, светильники, зоны, подписи.

```bash
python3 tools/room3d/build_room_3d.py rooms/kitchen-living.yaml -o viewer/kitchen-living.html
```

Дополнительные поля YAML для 3D описаны в начале `build_room_3d.py`.

Проверка без доступа к CDN (облачная сессия): поставить `three@0.169.0` через npm во временную
папку и в Playwright перехватить запросы `https://cdn.jsdelivr.net/npm/three@0.169.0/**`,
отдавая файлы из `node_modules/three/`. Страница выставляет `window.__ready = true`, когда сцена построена.

Проверено на демо-комнате planhaus:
`python3 tools/room3d/build_room_3d.py tools/planhaus/sample-project/rooms/living-room.yaml -o viewer/sample-living-room.html`

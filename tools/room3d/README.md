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

## 3D-модели вместо коробок

У объекта в `objects:` можно указать `model: assets/models/<name>.glb` — сборщик встроит GLB прямо в HTML,
а вьюер впишет модель в коробку объекта (ширина вдоль стены, глубина от стены, высота; перед модели (+Z в glTF)
смотрит в комнату). `cutout: {in: <id>, width, depth}` вырезает отверстие в корпусе и столешнице другого
объекта (мойка в нижнем шкафу). Модель производителя в .3ds конвертируется так:

```bash
python3 tools/room3d/tds_to_glb.py model.3ds -o assets/models/name.glb --scale 0.001 --mat ma3=#c9ccce:0.7:0.32
```

`--scale` — перевод единиц файла в метры (мм → 0.001), `--mat имя=#цвет:metalness:roughness` — материалы
(в .3ds нет PBR-данных); скрипт печатает размеры модели в см — их и ставить в `width/height/depth`.

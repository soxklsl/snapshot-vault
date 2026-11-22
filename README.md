# Snapshot Vault

CLI резервного копирования на Python: файлы хранятся по SHA-256, одинаковое содержимое занимает один объект. Каждая копия имеет отдельный JSON-манифест. Восстановление проверяет хеши и отказывается писать поверх существующего каталога.

## Запуск

Python 3.11+; команды выполняются из корня репозитория.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest -q
ruff check .
```

```bash
mkdir -p /tmp/vault-demo-source
printf 'example data\n' > /tmp/vault-demo-source/note.txt
snapshot-vault --vault /tmp/vault-demo-store snapshot /tmp/vault-demo-source
snapshot-vault --vault /tmp/vault-demo-store list
# Подставьте ID, напечатанный командой snapshot:
snapshot-vault --vault /tmp/vault-demo-store verify SNAPSHOT_ID
snapshot-vault --vault /tmp/vault-demo-store restore SNAPSHOT_ID /tmp/vault-demo-restored
```

## Хранение

```text
vault/
  objects/<sha256>          # содержимое, общее для всех снимков
  snapshots/<uuid>.json    # относительный путь, размер и хеш
```

Манифест публикуется после объектов через замену временного файла. Восстановление сначала проверяет все объекты, затем собирает файлы во временном каталоге. Пути с `..`, абсолютные пути и повторяющиеся имена отклоняются. Символические ссылки в исходнике отклоняются, чтобы случайно не включить данные за его пределами.

## Ограничения

Прототип для локальных неизменяемых исходников и доверенного хранилища. Не обеспечивает согласованный снимок активно изменяемой файловой системы. Один процесс за раз; нет блокировки, шифрования, подписи манифеста, retention или garbage collection. Файл читается целиком в память. Пустые каталоги, права, timestamps, ACL и extended attributes не сохраняются. Финальное перемещение файлов не является crash-atomic; сбой питания может оставить частичный каталог. SHA-256 обнаруживает повреждение, но не подмену манифеста злоумышленником.

Тесты проверяют round trip, дедупликацию, предыдущую версию файла, повреждение объекта, path traversal, symlink и отказ от перезаписи.

Следующие задачи: потоковое хеширование, fsync и recovery journal, блокировка писателя, retention с mark-and-sweep и S3 backend.

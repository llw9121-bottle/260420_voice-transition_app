"""下载并校验本地 ASR 模型。

两种模式：
1. 文件模式（默认）：从模型仓库逐个下载 int8 三件套并校验 SHA256。
2. 归档模式：给定 --url 或 --archive，从归档中只提取白名单文件。

安全约束：
- 每个文件都按固定的 SHA256 校验。
- 归档模式只提取白名单文件，使用 basename 落盘，防止路径穿越。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from pathlib import Path

WHITELIST = {
    'model.int8.onnx',
    'model.onnx',
    'tokens.txt',
    'silero_vad.onnx',
}
REQUIRED_SETS = (
    ('model.int8.onnx', 'tokens.txt', 'silero_vad.onnx'),
    ('model.onnx', 'tokens.txt', 'silero_vad.onnx'),
)
_CHUNK = 1024 * 1024

# 模型来源：优先国内镜像，失败后回退到 Hugging Face 官方地址。
_REPO_PATH = 'csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17/resolve/main'
DEFAULT_FILE_BASE_URLS = (
    f'https://hf-mirror.com/{_REPO_PATH}',
    f'https://huggingface.co/{_REPO_PATH}',
)
DEFAULT_FILES = (
    {
        'name': 'model.int8.onnx',
        'size': 239233841,
        'sha256': 'c71f0ce00bec95b07744e116345e33d8cbbe08cef896382cf907bf4b51a2cd51',
    },
    {
        'name': 'tokens.txt',
        'size': 315894,
        'sha256': 'f449eb28dc567533d7fa59be34e2abca8784f771850c78a47fb731a31429a1dc',
    },
    {
        'name': 'silero_vad.onnx',
        'size': 643854,
        'sha256': '9e2449e1087496d8d4caba907f23e0bd3f78d91fa552479bb9c23ac09cbb1fd6',
        'urls': (
            'https://github.com/k2-fsa/sherpa-onnx/releases/download/'
            'asr-models/silero_vad.onnx',
        ),
    },
)


class ModelFetchError(RuntimeError):
    pass


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(_CHUNK), b''):
            digest.update(block)
    return digest.hexdigest()


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + '.part')
    request = urllib.request.Request(url, headers={'User-Agent': 'voice-transition-app'})
    print(f'[model] 下载 {url}', flush=True)
    with urllib.request.urlopen(request, timeout=60) as response:
        total = int(response.headers.get('Content-Length') or 0)
        received = 0
        next_report = 0
        with temporary.open('wb') as handle:
            while True:
                block = response.read(_CHUNK)
                if not block:
                    break
                handle.write(block)
                received += len(block)
                if received >= next_report:
                    if total:
                        print(f'[model] {received / 1048576:.1f} / {total / 1048576:.1f} MB',
                              flush=True)
                    else:
                        print(f'[model] {received / 1048576:.1f} MB', flush=True)
                    next_report = received + 32 * 1048576
    os.replace(temporary, destination)


def fetch_files(base_urls, destination: Path, files) -> set[str]:
    destination.mkdir(parents=True, exist_ok=True)
    for item in files:
        name = item['name']
        target = destination / name
        expected_sha = item['sha256']
        if expected_sha.startswith('PENDING_'):
            raise ModelFetchError(
                f'{name} 的 SHA256 尚未固定；请更新 scripts/fetch_local_model.py'
            )
        if target.is_file() and sha256_file(target) == expected_sha:
            print(f'[model] 已存在且校验通过: {name}', flush=True)
            continue
        if target.exists():
            target.unlink()

        last_error = None
        urls = item.get('urls') or [
            f'{base_url.rstrip("/")}/{name}?download=true' for base_url in base_urls
        ]
        for url in urls:
            try:
                download(url, target)
                actual = sha256_file(target)
                if actual != expected_sha:
                    target.unlink(missing_ok=True)
                    # 哈希不匹配属于供应链问题，不再尝试其他源。
                    raise ModelFetchError(
                        f'{name} SHA256 不匹配\n期望: {expected_sha}\n实际: {actual}'
                    )
                expected_size = item.get('size')
                if expected_size and target.stat().st_size != expected_size:
                    target.unlink(missing_ok=True)
                    raise ModelFetchError(
                        f'{name} 大小不匹配：期望 {expected_size}，'
                        f'实际 {target.stat().st_size}'
                    )
                last_error = None
                break
            except ModelFetchError:
                raise
            except Exception as exc:
                last_error = exc
                target.unlink(missing_ok=True)
                print(f'[model] 源不可用，尝试下一个: {url} ({exc})', flush=True)

        if last_error is not None:
            raise ModelFetchError(f'{name} 下载失败：{last_error}')
    return {item['name'] for item in files}


def _safe_name(member_name: str) -> str:
    normalized = member_name.replace('\\', '/')
    if normalized.startswith('/') or '..' in normalized.split('/'):
        return ''
    return os.path.basename(normalized)


def extract(archive: Path, destination: Path) -> set[str]:
    destination.mkdir(parents=True, exist_ok=True)
    extracted: set[str] = set()

    if tarfile.is_tarfile(archive):
        with tarfile.open(archive, 'r:*') as bundle:
            for member in bundle.getmembers():
                if not member.isfile():
                    continue
                name = _safe_name(member.name)
                if name not in WHITELIST:
                    continue
                source = bundle.extractfile(member)
                if source is None:
                    continue
                with source, (destination / name).open('wb') as target:
                    while True:
                        block = source.read(_CHUNK)
                        if not block:
                            break
                        target.write(block)
                extracted.add(name)
    elif zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as bundle:
            for info in bundle.infolist():
                if info.is_dir():
                    continue
                name = _safe_name(info.filename)
                if name not in WHITELIST:
                    continue
                with bundle.open(info) as source, (destination / name).open('wb') as target:
                    while True:
                        block = source.read(_CHUNK)
                        if not block:
                            break
                        target.write(block)
                extracted.add(name)
    else:
        raise ModelFetchError(f'不支持的模型归档格式: {archive}')

    return extracted


def write_manifest(destination: Path, files: set[str]) -> None:
    lines = ['file\tsize\tsha256']
    for name in sorted(files):
        path = destination / name
        lines.append(f'{name}\t{path.stat().st_size}\t{sha256_file(path)}')
    (destination / 'MANIFEST.txt').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print('\n'.join(lines), flush=True)


def _archive_mode(args, destination: Path) -> set[str]:
    if args.archive:
        archive = Path(args.archive).expanduser().resolve()
        if not archive.is_file():
            raise ModelFetchError(f'归档不存在: {archive}')
    else:
        if not args.url:
            raise ModelFetchError('必须提供 --url 或 --archive')
        cache_dir = Path(args.cache_dir).expanduser().resolve() if args.cache_dir else None
        if cache_dir:
            cache_dir.mkdir(parents=True, exist_ok=True)
            archive = cache_dir / Path(args.url.split('?', 1)[0]).name
        else:
            handle, temp_name = tempfile.mkstemp(suffix='.archive')
            os.close(handle)
            archive = Path(temp_name)
        if not archive.is_file() or archive.stat().st_size == 0:
            download(args.url, archive)

    actual = sha256_file(archive)
    print(f'[model] archive sha256: {actual}', flush=True)
    if args.sha256:
        if actual.lower() != args.sha256.strip().lower():
            raise ModelFetchError(
                f'SHA256 不匹配\n期望: {args.sha256}\n实际: {actual}'
            )
    else:
        print('[model] 警告：未提供 --sha256，跳过归档校验', flush=True)

    return extract(archive, destination)


def main() -> int:
    parser = argparse.ArgumentParser(description='Fetch local ASR model files')
    parser.add_argument('--url', help='归档下载地址（归档模式）')
    parser.add_argument('--archive', help='已有归档路径（归档模式）')
    parser.add_argument('--sha256', default='', help='归档 SHA256（归档模式）')
    parser.add_argument('--file-base-url', default='', help='单文件模式的基础地址')
    parser.add_argument('--dest', required=True, help='模型输出目录')
    parser.add_argument('--cache-dir', default='', help='归档缓存目录（归档模式）')
    args = parser.parse_args()

    destination = Path(args.dest).expanduser().resolve()

    try:
        if args.url or args.archive:
            extracted = _archive_mode(args, destination)
        else:
            base_urls = (
                [args.file_base_url] if args.file_base_url else list(DEFAULT_FILE_BASE_URLS)
            )
            extracted = fetch_files(base_urls, destination, DEFAULT_FILES)

        if not any(set(required) <= extracted for required in REQUIRED_SETS):
            expected = ' / '.join(REQUIRED_SETS[0])
            raise ModelFetchError(
                f'缺少必需文件：{expected}；实际: {sorted(extracted)}'
            )

        write_manifest(destination, extracted)
        print(f'[model] 完成: {destination}', flush=True)
        return 0
    except Exception as exc:
        print(f'[model] 失败: {exc}', file=sys.stderr, flush=True)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())

"""DashScope 请求的代理策略与回退工具。

requests 和 websocket-client 都会读取系统/环境代理。本模块统一处理：
- system: 使用系统/环境代理
- direct: 忽略代理，DashScope 直连
- manual: 使用显式配置的代理地址

当系统代理是本机地址且无法正常转发时，自动为 DashScope 域名启用直连，
避免本地 VPN/代理未启动导致 API 调用失败。
"""

import contextlib
import ipaddress
import os
import socket
import urllib.parse
from typing import Iterable, Iterator, List, Optional, Tuple

from loguru import logger

_NO_PROXY_KEYS = ('NO_PROXY', 'no_proxy')


def parse_proxy_host_port(proxy_url: str) -> Optional[Tuple[str, int]]:
    """从代理地址中提取 (host, port)。"""
    if not proxy_url:
        return None
    value = proxy_url if '://' in proxy_url else f'http://{proxy_url}'
    parsed = urllib.parse.urlparse(value)
    if not parsed.hostname or not parsed.port:
        return None
    return parsed.hostname, parsed.port


def redact_proxy_url(proxy_url: str) -> str:
    """隐藏代理地址中的用户名和密码，避免写入日志。"""
    if not proxy_url:
        return ''
    value = proxy_url if '://' in proxy_url else f'http://{proxy_url}'
    parsed = urllib.parse.urlparse(value)
    if not parsed.username and not parsed.password:
        return value
    netloc = parsed.hostname or ''
    if parsed.port:
        netloc = f'{netloc}:{parsed.port}'
    return urllib.parse.urlunparse(
        (parsed.scheme, f'***@{netloc}', parsed.path, parsed.params, parsed.query, parsed.fragment)
    )


def is_loopback_host(host: str) -> bool:
    """判断是否为本机回环地址。"""
    if host in ('localhost',):
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_loopback_proxy(proxy_url: str) -> bool:
    """判断代理地址是否指向本机。"""
    host_port = parse_proxy_host_port(proxy_url)
    return bool(host_port and is_loopback_host(host_port[0]))


def effective_proxy(url: str) -> str:
    """返回 requests 对指定 URL 实际会使用的代理地址。"""
    import requests

    proxies = requests.utils.get_environ_proxies(url)
    return proxies.get('https') or proxies.get('http') or ''


def should_fallback_to_direct(url: str, mode: str = 'system') -> bool:
    """仅在 system 模式下、且代理为本机地址时允许直连回退。"""
    if (mode or 'system').strip().lower() != 'system':
        return False
    return is_loopback_proxy(effective_proxy(url))


def proxy_supports_connect(proxy_url: str, target_host: str,
                           target_port: int = 443, timeout: float = 1.0) -> bool:
    """探测代理是否真的能转发 HTTPS CONNECT 请求。

    TCP 端口能连上不代表代理可用（可能出现 RemoteDisconnected）。
    非 HTTP 代理（SOCKS/HTTPS）不做探测，避免误判。
    """
    if not proxy_url:
        return True
    scheme = urllib.parse.urlparse(proxy_url if '://' in proxy_url else f'http://{proxy_url}').scheme.lower()
    if scheme not in ('http', ''):
        return True
    host_port = parse_proxy_host_port(proxy_url)
    if not host_port:
        return True
    try:
        with socket.create_connection(host_port, timeout=timeout) as sock:
            sock.settimeout(timeout)
            request = (
                f'CONNECT {target_host}:{target_port} HTTP/1.1\r\n'
                f'Host: {target_host}:{target_port}\r\n\r\n'
            )
            sock.sendall(request.encode('ascii'))
            response = sock.recv(1024)
    except OSError:
        return False
    first_line = response.split(b'\r\n', 1)[0]
    # 200 表示可转发；407 表示代理存活但需要认证，不应误判为故障。
    return b' 200 ' in first_line or b' 407 ' in first_line


def _add_hosts_to_no_proxy(hosts: Iterable[str]) -> None:
    current = os.environ.get('NO_PROXY') or os.environ.get('no_proxy') or ''
    parts = [part for part in current.replace(' ', '').split(',') if part]
    for host in hosts:
        if host and host not in parts:
            parts.append(host)
    value = ','.join(parts)
    os.environ['NO_PROXY'] = value
    os.environ['no_proxy'] = value


def _remove_hosts_from_no_proxy(hosts: Iterable[str]) -> None:
    remove = {host for host in hosts if host}
    current = os.environ.get('NO_PROXY') or os.environ.get('no_proxy') or ''
    parts = [part for part in current.replace(' ', '').split(',') if part and part not in remove]
    if parts:
        value = ','.join(parts)
        os.environ['NO_PROXY'] = value
        os.environ['no_proxy'] = value
    else:
        for key in _NO_PROXY_KEYS:
            os.environ.pop(key, None)


@contextlib.contextmanager
def bypass_proxy_for(hosts: Iterable[str]) -> Iterator[None]:
    """临时让指定域名绕过代理，退出时恢复原 NO_PROXY。"""
    host_list: List[str] = [host for host in hosts if host]
    original = {key: os.environ.get(key) for key in _NO_PROXY_KEYS}
    _add_hosts_to_no_proxy(host_list)
    try:
        yield
    finally:
        for key, value in original.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def apply_proxy_policy(mode: str, proxy_url: str, hosts: Iterable[str]) -> None:
    """按配置初始化进程级代理策略。"""
    mode = (mode or 'system').strip().lower()
    host_list = [host for host in hosts if host]

    if mode == 'direct':
        _add_hosts_to_no_proxy(host_list)
        logger.info('代理策略: direct（DashScope 直连）')
        return

    if mode == 'manual':
        proxy = (proxy_url or '').strip()
        if proxy:
            for key in ('HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy'):
                os.environ[key] = proxy
            _remove_hosts_from_no_proxy(host_list)
            logger.info(f'代理策略: manual（{redact_proxy_url(proxy)}）')
            return
        logger.warning('代理模式为 manual 但未填写代理地址，回退到 system')

    # system：仅在检测到本机代理无法转发时自动直连。
    proxy = effective_proxy('https://dashscope.aliyuncs.com')
    if proxy and is_loopback_proxy(proxy) and not proxy_supports_connect(proxy, 'dashscope.aliyuncs.com'):
        logger.warning(
            f'检测到本地代理 {redact_proxy_url(proxy)} 不可用，DashScope 请求将直连。'
            '请检查代理/VPN，或在设置中关闭“使用系统代理”。'
        )
        _add_hosts_to_no_proxy(host_list)
    else:
        logger.info(f'代理策略: system（{redact_proxy_url(proxy) or "无代理"}）')

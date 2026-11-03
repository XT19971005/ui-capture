"""Shared URL checks for the host controller and Django; no framework dependency."""
import ipaddress
from urllib.parse import urlsplit


def endpoint(value, schemes=('https',)):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 or c in '\\\x7f' for c in value):
        raise ValueError('站点或登录端点 URL 含无效字符')
    u = urlsplit(value)
    if (u.scheme not in schemes or not u.hostname or u.username or u.password or u.query or u.fragment
            or (u.port is not None and not 1 <= u.port <= 65535)):
        raise ValueError('站点或登录端点协议/地址无效，不允许凭据、查询参数或 fragment')
    return u


def broker_endpoint(oidc):
    allowed = oidc.get('allow_public_http_token_exchange', False)
    if type(allowed) is not bool:
        raise ValueError('allow_public_http_token_exchange 必须为布尔值')
    override = oidc.get('token_exchange_url', '')
    if not override:
        return oidc.get('token_url', '')
    if oidc.get('mode') != 'broker':
        raise ValueError('token_exchange_url 仅用于 broker 模式')
    target = endpoint(override, ('http', 'https'))
    if target.scheme == 'http':
        try:
            address = ipaddress.ip_address(target.hostname)
        except ValueError as exc:
            raise ValueError('HTTP Broker 后台端点必须使用明确 IP') from exc
        if (address.is_multicast or address.is_unspecified
                or not (address.is_private or (allowed and address.is_global))):
            raise ValueError('公网 HTTP Broker 后台端点须显式开启 allow_public_http_token_exchange')
    return override


def validate_transport(site, oidc, production=True):
    allowed = site.get('allow_http', False)
    if type(allowed) is not bool:
        raise ValueError('site.allow_http 必须为布尔值')
    public = endpoint(site['public_url'], ('http', 'https') if allowed or not production else ('https',))
    for name in ('discovery_url', 'login_url', 'token_url'):
        if oidc.get(name):
            endpoint(oidc[name])
    broker_endpoint(oidc)
    return public

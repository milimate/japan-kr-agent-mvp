from __future__ import annotations

import base64
import time
from typing import Any
from typing import Optional

import bcrypt
import httpx

from app.config import settings


class NaverAuthError(Exception):
    pass


class NaverApiError(Exception):
    pass


class NaverClient:
    def __init__(self) -> None:
        self._access_token: Optional[str] = None
        self._token_expire_at: float = 0

    def _get_bearer_token(self) -> str:
        now_ms = int(time.time() * 1000)
        if self._access_token and now_ms < self._token_expire_at - 60_000:
            return self._access_token

        client_id = settings.naver_client_id
        client_secret = settings.naver_client_secret
        token_type = settings.naver_token_type

        if not client_id or not client_secret:
            raise NaverAuthError("NAVER_CLIENT_ID/NAVER_CLIENT_SECRET 설정이 필요합니다.")

        if token_type.upper() == "SELLER" and not settings.naver_account_id:
            raise NaverAuthError("SELLER 타입은 NAVER_ACCOUNT_ID 설정이 필요합니다.")

        timestamp = str(now_ms)
        password = f"{client_id}_{timestamp}"
        hashed = bcrypt.hashpw(password.encode("utf-8"), client_secret.encode("utf-8"))
        client_secret_sign = base64.b64encode(hashed).decode("utf-8")

        data = {
            "client_id": client_id,
            "timestamp": timestamp,
            "client_secret_sign": client_secret_sign,
            "grant_type": "client_credentials",
            "type": token_type,
        }
        if settings.naver_account_id:
            data["account_id"] = settings.naver_account_id

        token_url = f"{settings.naver_api_base_url.rstrip('/')}/v1/oauth2/token"
        with httpx.Client(timeout=20.0) as client:
            res = client.post(token_url, data=data)

        if res.status_code >= 400:
            raise NaverAuthError(f"토큰 발급 실패: {res.status_code} {res.text[:300]}")

        payload = res.json()
        token = payload.get("access_token")
        expires_in = int(payload.get("expires_in", 0))
        if not token:
            raise NaverAuthError("토큰 응답에 access_token이 없습니다.")

        self._access_token = token
        self._token_expire_at = now_ms + max(expires_in, 0) * 1000
        return token

    def create_product(self, product_payload: dict[str, Any]) -> dict[str, Any]:
        token = self._get_bearer_token()
        url = f"{settings.naver_api_base_url.rstrip('/')}{settings.naver_product_create_path}"
        headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

        with httpx.Client(timeout=30.0) as client:
            res = client.post(url, headers=headers, json=product_payload)
            if res.status_code == 401:
                # 토큰 만료/인증 오류 시 1회 재시도
                self._access_token = None
                retry_token = self._get_bearer_token()
                headers["Authorization"] = f"Bearer {retry_token}"
                res = client.post(url, headers=headers, json=product_payload)

        if res.status_code >= 400:
            raise NaverApiError(f"상품등록 실패: {res.status_code} {res.text[:500]}")

        return res.json() if res.text else {}

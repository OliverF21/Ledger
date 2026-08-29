"""
Plaid SDK wrapper for real Plaid API integration.
"""

import os
import logging
import requests
from typing import List, Dict, Any, Iterator, Optional
from datetime import date, datetime

from app.enrichment import extract_plaid_enrichment
from app.plaid_errors import raise_for_plaid_response

logger = logging.getLogger(__name__)

# Bound every Plaid HTTP call so a stalled socket cannot freeze the API.
_HTTP_TIMEOUT_SECONDS = 30


class PlaidService:
    """Real Plaid service using REST API."""

    _HTTP_TIMEOUT_SECONDS = _HTTP_TIMEOUT_SECONDS

    @staticmethod
    def _get_headers() -> Dict[str, str]:
        """Get headers for Plaid API requests."""
        return {
            "Content-Type": "application/json",
        }

    @staticmethod
    def _setting(name: str) -> Optional[str]:
        """Resolve a Plaid setting: app_config table first, os.getenv fallback.

        On env fallback, PLAID_SECRET maps to the env-specific secret var.
        """
        # app_config (desktop BYOK) takes precedence.
        try:
            from app.database import SessionLocal
            from app import app_config
            db = SessionLocal()
            try:
                val = app_config.get(db, name)
            finally:
                db.close()
            if val:
                return val
        except Exception:
            pass  # DB not ready (early startup) — fall through to env

        if name == "PLAID_SECRET":
            env = (PlaidService._setting("PLAID_ENV") or "sandbox").lower()
            var = "PLAID_PROD_SECRET" if env == "production" else "PLAID_SANDBOX_SECRET"
            return os.getenv(var)
        return os.getenv(name)

    @staticmethod
    def is_configured() -> bool:
        return bool(PlaidService._setting("PLAID_CLIENT_ID") and PlaidService._setting("PLAID_SECRET"))

    @staticmethod
    def _get_plaid_url() -> str:
        """Get Plaid API base URL."""
        env = (PlaidService._setting("PLAID_ENV") or "sandbox").lower()
        return "https://production.plaid.com" if env == "production" else "https://sandbox.plaid.com"

    @staticmethod
    def _get_credentials() -> Dict[str, str]:
        """Get Plaid credentials, selecting secret based on environment."""
        return {
            "client_id": PlaidService._setting("PLAID_CLIENT_ID"),
            "secret": PlaidService._setting("PLAID_SECRET"),
        }

    @staticmethod
    def validate_config() -> None:
        """Desktop BYOK: never block launch. Log a warning if production is
        selected without production credentials."""
        env = (PlaidService._setting("PLAID_ENV") or "sandbox").lower()
        if env == "production" and not (
            PlaidService._setting("PLAID_CLIENT_ID") and PlaidService._setting("PLAID_SECRET")
        ):
            logger.warning(
                "PLAID_ENV=production but production Plaid credentials are missing; "
                "bank sync will fail until configured in Settings -> Plaid."
            )

    @staticmethod
    def create_link_token(
        user_id: int,
        client_name: str = "Ledger",
        *,
        access_token: Optional[str] = None,
    ) -> tuple[str, str]:
        """
        Create a Plaid Hosted Link token for the frontend.

        With Hosted Link, Plaid hosts the whole Link experience — including the
        OAuth "log in at your bank" redirect — on its own HTTPS domain. The
        client therefore needs no redirect URI of its own, which is what made
        OAuth banks impossible in the packaged http://127.0.0.1 desktop app
        (Plaid rejects non-HTTPS redirect URIs in production).

        Returns (link_token, hosted_link_url): open hosted_link_url in the
        system browser and poll get_link_session(link_token) for the result.

        When access_token is provided, Link opens in update mode for re-auth.
        """
        try:
            url = f"{PlaidService._get_plaid_url()}/link/token/create"
            payload = {
                **PlaidService._get_credentials(),
                'user': {'client_user_id': str(user_id)},
                'client_name': client_name,
                'language': 'en',
                'country_codes': ['US'],
                # transactions only in products — banks like Capital One don't support
                # investments; brokerages get investments via required_if_supported.
                'products': ['transactions'],
                'optional_products': ['auth'],
                'required_if_supported_products': ['investments'],
                # Plaid hosts the flow and owns the OAuth redirect.
                'hosted_link': {},
            }
            if access_token:
                payload['access_token'] = access_token
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            raise_for_plaid_response(response, "Failed to create link token")
            data = response.json()
            return data['link_token'], data['hosted_link_url']
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to create link token: {str(e)}")

    @staticmethod
    def get_link_session(link_token: str) -> Dict[str, Any]:
        """Fetch Link session details for a Hosted Link token.

        Retrieves the outcome of a Hosted Link flow without webhooks (a packaged
        desktop app has no public URL Plaid can call back). The completed
        public_token — and any early exit — is reported here for six hours after
        the session ends. Parsed by routes/plaid.py::get_link_session.
        """
        try:
            url = f"{PlaidService._get_plaid_url()}/link/token/get"
            payload = {
                **PlaidService._get_credentials(),
                'link_token': link_token,
            }
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            raise_for_plaid_response(response, "Failed to get link session")
            return response.json()
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to get link session: {str(e)}")

    @staticmethod
    def exchange_public_token(public_token: str) -> tuple[str, str]:
        """Exchange public token for access token."""
        try:
            url = f"{PlaidService._get_plaid_url()}/item/public_token/exchange"
            payload = {
                **PlaidService._get_credentials(),
                'public_token': public_token,
            }
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            return data['access_token'], data['item_id']
        except Exception as e:
            raise ValueError(f"Failed to exchange token: {str(e)}")

    @staticmethod
    def get_accounts(access_token: str) -> List[Dict[str, Any]]:
        """Fetch accounts for an access token."""
        try:
            url = f"{PlaidService._get_plaid_url()}/accounts/get"
            payload = {
                **PlaidService._get_credentials(),
                'access_token': access_token,
            }
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()

            accounts = []
            for account in data.get('accounts', []):
                accounts.append({
                    "plaid_account_id": account['account_id'],
                    "name": account['name'],
                    "type": account['type'],
                    "subtype": account['subtype'],
                    "current_balance": account['balances']['current'] or 0,
                })
            return accounts
        except Exception as e:
            raise ValueError(f"Failed to get accounts: {str(e)}")

    @staticmethod
    def is_plaid_institution_id(value: Optional[str]) -> bool:
        return bool(value and value.startswith('ins_'))

    @staticmethod
    def _logo_data_uri(logo_b64: Optional[str]) -> Optional[str]:
        if not logo_b64:
            return None
        return f'data:image/png;base64,{logo_b64}'

    @staticmethod
    def get_institution_details(institution_id: Optional[str]) -> Dict[str, Any]:
        """Fetch institution name, logo, and brand color from Plaid."""
        fallback_name = institution_id or 'Unknown Institution'
        result: Dict[str, Any] = {
            'institution_id': institution_id if PlaidService.is_plaid_institution_id(institution_id) else None,
            'name': fallback_name,
            'logo': None,
            'primary_color': None,
        }
        if not institution_id:
            return result
        if not PlaidService.is_plaid_institution_id(institution_id):
            result['name'] = institution_id
            return result

        try:
            url = f"{PlaidService._get_plaid_url()}/institutions/get_by_id"
            payload = {
                **PlaidService._get_credentials(),
                'institution_id': institution_id,
                'country_codes': ['US'],
                'options': {'include_optional_metadata': True},
            }
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            inst = response.json().get('institution', {})
            result['name'] = inst.get('name', institution_id)
            result['logo'] = PlaidService._logo_data_uri(inst.get('logo'))
            result['primary_color'] = inst.get('primary_color')
            return result
        except Exception:
            return result

    @staticmethod
    def resolve_institution_name(institution_id: Optional[str]) -> str:
        """Map a Plaid institution_id (e.g. ins_56) to a human-readable name."""
        return PlaidService.get_institution_details(institution_id)['name']

    @staticmethod
    def search_institution_id(name: str) -> Optional[str]:
        """Best-effort lookup of Plaid institution_id from a display name."""
        if not name or PlaidService.is_plaid_institution_id(name):
            return name if PlaidService.is_plaid_institution_id(name) else None
        try:
            url = f"{PlaidService._get_plaid_url()}/institutions/search"
            payload = {
                **PlaidService._get_credentials(),
                'query': name,
                'country_codes': ['US'],
                'products': ['transactions'],
            }
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            institutions = response.json().get('institutions', [])
            name_lower = name.lower()
            for inst in institutions:
                if inst.get('name', '').lower() == name_lower:
                    return inst.get('institution_id')
            return institutions[0].get('institution_id') if institutions else None
        except Exception:
            return None

    @staticmethod
    def apply_institution_metadata(item: Any, details: Dict[str, Any]) -> bool:
        """Apply institution details to an Item row. Returns True if anything changed."""
        changed = False
        if details.get('institution_id') and item.institution_id != details['institution_id']:
            item.institution_id = details['institution_id']
            changed = True
        name = details.get('name')
        if name and not PlaidService.is_plaid_institution_id(name) and item.institution_name != name:
            item.institution_name = name
            changed = True
        if details.get('logo') and item.institution_logo != details['logo']:
            item.institution_logo = details['logo']
            changed = True
        if details.get('primary_color') and item.institution_color != details['primary_color']:
            item.institution_color = details['primary_color']
            changed = True
        return changed

    @staticmethod
    def refresh_item_institution_metadata(item: Any) -> bool:
        """Resolve missing institution metadata for one Item (no DB commit)."""
        institution_id = item.institution_id
        if PlaidService.is_plaid_institution_id(item.institution_name):
            institution_id = item.institution_name
        elif not institution_id and item.institution_name:
            institution_id = PlaidService.search_institution_id(item.institution_name)

        if not institution_id:
            return False

        needs_refresh = (
            not item.institution_id
            or PlaidService.is_plaid_institution_id(item.institution_name)
            or not item.institution_logo
            or not item.institution_color
        )
        if not needs_refresh:
            return False

        details = PlaidService.get_institution_details(institution_id)
        if not details.get('institution_id'):
            details['institution_id'] = institution_id
        return PlaidService.apply_institution_metadata(item, details)

    @staticmethod
    def get_accounts_with_institution(access_token: str) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
        """Fetch accounts and resolve the linked institution's metadata."""
        try:
            url = f"{PlaidService._get_plaid_url()}/accounts/get"
            payload = {
                **PlaidService._get_credentials(),
                'access_token': access_token,
            }
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()

            accounts = []
            for account in data.get('accounts', []):
                accounts.append({
                    "plaid_account_id": account['account_id'],
                    "name": account['name'],
                    "type": account['type'],
                    "subtype": account['subtype'],
                    "current_balance": account['balances']['current'] or 0,
                })
            institution_id = data.get('item', {}).get('institution_id')
            details = PlaidService.get_institution_details(institution_id)
            return accounts, details
        except Exception as e:
            raise ValueError(f"Failed to get accounts: {str(e)}")

    @staticmethod
    def sync_transactions(access_token: str, cursor: str = None) -> Dict[str, Any]:
        """Sync transactions using cursor-based endpoint."""
        try:
            url = f"{PlaidService._get_plaid_url()}/transactions/sync"
            payload = {
                **PlaidService._get_credentials(),
                'access_token': access_token,
                'options': {
                    'personal_finance_category_version': 'v2',
                    'include_original_description': True,
                },
            }
            if cursor:
                payload['cursor'] = cursor

            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            raise_for_plaid_response(response, "Failed to sync transactions")
            data = response.json()

            transactions = []
            for txn in data.get('added', []) + data.get('modified', []):
                transactions.append(PlaidService.parse_sync_transaction(txn))

            return {
                "transactions": transactions,
                "removed": [r['transaction_id'] for r in data.get('removed', [])],
                "next_cursor": data.get('next_cursor'),
                "has_more": data.get('has_more', False),
            }
        except ValueError:
            raise
        except Exception as e:
            raise ValueError(f"Failed to sync transactions: {str(e)}")

    @staticmethod
    def iter_transactions(
        access_token: str,
        start_date: date,
        end_date: date,
        *,
        page_size: int = 500,
    ) -> Iterator[Dict[str, Any]]:
        """Yield raw Plaid transaction objects from /transactions/get (paginated)."""
        url = f"{PlaidService._get_plaid_url()}/transactions/get"
        offset = 0
        while True:
            payload = {
                **PlaidService._get_credentials(),
                "access_token": access_token,
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "options": {
                    "personal_finance_category_version": "v2",
                    "include_original_description": True,
                    "count": page_size,
                    "offset": offset,
                },
            }
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            data = response.json()
            batch = data.get("transactions", [])
            for txn in batch:
                yield txn
            total = data.get("total_transactions", 0)
            offset += len(batch)
            if not batch or offset >= total:
                break

    @staticmethod
    def get_investment_holdings(access_token: str) -> Dict[str, Any]:
        """POST /investments/holdings/get → {accounts, holdings, securities}"""
        try:
            url = f"{PlaidService._get_plaid_url()}/investments/holdings/get"
            payload = {
                **PlaidService._get_credentials(),
                'access_token': access_token,
            }
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            error_code = None
            try:
                error_code = e.response.json().get('error_code')
            except Exception:
                pass
            raise ValueError(f"Failed to get investment holdings: {error_code or str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to get investment holdings: {str(e)}")

    @staticmethod
    def get_investment_transactions(
        access_token: str, start_date: date, end_date: date, *, offset: int = 0, count: int = 500
    ) -> Dict[str, Any]:
        """POST /investments/transactions/get — one page; caller loops using total_investment_transactions."""
        try:
            url = f"{PlaidService._get_plaid_url()}/investments/transactions/get"
            payload = {
                **PlaidService._get_credentials(),
                'access_token': access_token,
                'start_date': start_date.isoformat(),
                'end_date': end_date.isoformat(),
                'options': {
                    'count': count,
                    'offset': offset,
                },
            }
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            error_code = None
            try:
                error_code = e.response.json().get('error_code')
            except Exception:
                pass
            raise ValueError(f"Failed to get investment transactions: {error_code or str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to get investment transactions: {str(e)}")

    @staticmethod
    def refresh_investments(access_token: str) -> Dict[str, Any]:
        """POST /investments/refresh — on-demand holdings refresh."""
        try:
            url = f"{PlaidService._get_plaid_url()}/investments/refresh"
            payload = {
                **PlaidService._get_credentials(),
                'access_token': access_token,
            }
            response = requests.post(
                url,
                json=payload,
                headers=PlaidService._get_headers(),
                timeout=_HTTP_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            return response.json()
        except requests.HTTPError as e:
            error_code = None
            try:
                error_code = e.response.json().get('error_code')
            except Exception:
                pass
            raise ValueError(f"Failed to refresh investments: {error_code or str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to refresh investments: {str(e)}")

    @staticmethod
    def normalize_holdings_response(data: Dict[str, Any]) -> list[Dict[str, Any]]:
        """
        Join holdings → securities by security_id.
        Return flat list of dicts ready for DB upsert, each containing both
        holding fields and nested security fields.
        """
        securities_by_id = {s['security_id']: s for s in data.get('securities', [])}
        normalized = []
        for holding in data.get('holdings', []):
            security = securities_by_id.get(holding.get('security_id'), {})
            close_price_as_of = security.get('close_price_as_of')
            normalized.append({
                'account_id': holding['account_id'],
                'security_id': holding['security_id'],
                'quantity': holding['quantity'],
                'institution_price': holding.get('institution_price'),
                'institution_value': holding.get('institution_value'),
                'cost_basis': holding.get('cost_basis'),
                'iso_currency_code': holding.get('iso_currency_code'),
                'unofficial_currency_code': holding.get('unofficial_currency_code'),
                'security_ticker_symbol': security.get('ticker_symbol'),
                'security_name': security.get('name'),
                'security_type': security.get('type'),
                'security_subtype': security.get('subtype'),
                'security_close_price': security.get('close_price'),
                'security_close_price_as_of': date.fromisoformat(close_price_as_of) if close_price_as_of else None,
                'security_iso_currency_code': security.get('iso_currency_code'),
                'security_is_cash_equivalent': security.get('is_cash_equivalent', False),
            })
        return normalized

    @staticmethod
    def parse_sync_transaction(txn: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize a raw Plaid transaction object into our sync payload shape."""
        raw_date = txn["date"]
        txn_date = date.fromisoformat(raw_date) if isinstance(raw_date, str) else raw_date
        enrichment = extract_plaid_enrichment(txn)
        return {
            "plaid_transaction_id": txn["transaction_id"],
            "account_id": txn["account_id"],
            "amount": txn["amount"],
            "date": txn_date,
            "pending": txn["pending"],
            **enrichment,
        }

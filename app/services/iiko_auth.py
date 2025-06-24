import httpx
import logging
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)


class IikoAuthService:
    def __init__(self, base_url: str):
        self.base_url = base_url
        self.login = "Tanat"
        self.password = "7c4a8d09ca3762af61e59520943dc26494f8941b"
        self.token = None
        self.token_expires_at = None
    
    async def get_auth_token(self) -> str:
        """Get authentication token, refresh if needed"""
        if self.token and self.token_expires_at and datetime.now() < self.token_expires_at:
            return self.token
        
        return await self._refresh_token()
    
    async def _refresh_token(self) -> str:
        """Refresh authentication token"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/resto/api/auth",
                    params={
                        "login": self.login,
                        "pass": self.password
                    }
                )
                response.raise_for_status()
                
                self.token = response.text.strip()
                self.token_expires_at = datetime.now() + timedelta(minutes=55)  # Refresh 5 minutes before expiry
                
                logger.info("Successfully refreshed iiko authentication token")
                return self.token
                
        except httpx.HTTPError as e:
            logger.error(f"Error refreshing iiko token: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error refreshing token: {e}")
            raise
import logging
import subprocess
from typing import Optional

import requests

logger = logging.getLogger(__name__)

WEB_TIMEOUT = 15
BROWSER_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def obtain_content(url: str) -> Optional[str]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": BROWSER_UA, "Accept-Language": "vi-VN,vi;q=0.9"},
            timeout=WEB_TIMEOUT,
        )
        response.raise_for_status()
        return response.text
    except Exception as exc:
        logger.debug("requests failed for %s: %s", url, exc)

    try:
        result = subprocess.run(
            [
                "curl",
                "-s",
                "-L",
                "--max-time",
                str(WEB_TIMEOUT),
                "-A",
                BROWSER_UA,
                url,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        content = result.stdout
        return content if content else None
    except Exception as exc:
        logger.error("curl failed for %s: %s", url, exc)
        return None

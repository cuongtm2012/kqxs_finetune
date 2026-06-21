from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="RBK_", env_file=".env", extra="ignore")

    port: int = 8081
    database_url: str = "postgresql://rbk:rbk@127.0.0.1:5436/rbk"

    url: str = "https://rongbachkim.com/ketqua.php?getkq&ngay=%s&days=1&wday=0"
    chotkq: str = "https://rongbachkim.com/chot.php?getlist&ngay=%s&lastid=0&lastupdate=0"
    trend_url: str = "https://rongbachkim.com/trend.php?list&alone&day=%s&trendlimit=100"
    caudep_url: str = (
        "https://rongbachkim.com/soicau.html?submit=1&setmode=full&exactlimit=0"
        "&limit=%s&ngay=%s&nhay=%s&lon=%s"
    )
    caudep_page_url: str = "https://rongbachkim.com/soicau.html"
    rss_mn_url: str = "https://xskt.com.vn/rss-feed/mien-nam-xsmn.rss"
    rss_mt_url: str = "https://xskt.com.vn/rss-feed/mien-trung-xsmt.rss"
    rss_mb_url: str = "https://xskt.com.vn/rss-feed/mien-bac-xsmb.rss"

    enable_scheduler: bool = True
    scrape_delay_seconds: float = 1.0


settings = Settings()

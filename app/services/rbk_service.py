import json
import logging
from datetime import date, timedelta

import feedparser
from bs4 import BeautifulSoup

from app.caudep_fields import caudep_field_name, iter_caudep_combinations
from app.config import settings
from app.repositories.rbk_repo import rbk_repo
from app.utils.http_util import obtain_content
from app.utils.validator import validate_string, validate_strings

logger = logging.getLogger(__name__)


class RbkService:
    def als_chot_kq(self, url: str, day: str) -> None:
        items = self.parse_chot_kq(url)
        rbk_repo.insert_chot_kq(items, day)

    def als_ket_qua_sx(self, url: str, day: str) -> None:
        kq = self.ket_qua_sx(url)
        kq["ngaychot"] = day
        rbk_repo.insert_ket_qua(kq)

    def als_trend(self, url: str, day: str) -> None:
        trending = self.trend_arr(url)
        rbk_repo.delete_trend(day)
        rbk_repo.insert_trend({"ngaychot": day, "lotto": str(trending)})

    def als_caudep(self, cd: dict, url: str, limit: int, day: str, nhay: int, lon: int) -> None:
        values = self.caudep_arr(url)
        cd["ngaychot"] = day
        cd[caudep_field_name(limit, nhay, lon)] = str(values)

    def imp_caudep(self, cd: dict) -> None:
        rbk_repo.insert_cau_dep(cd)

    def limit_caudep(self, url: str) -> int:
        try:
            response = obtain_content(url)
            if not response:
                return 0
            soup = BeautifulSoup(response, "html.parser")
            return len(soup.select(".showdays_td"))
        except Exception as exc:
            logger.error("%s", exc)
            return 0

    def import_kqxs_days(self, days: int = 3) -> int:
        from app.services.xskt_service import import_mb_from_xskt

        imported = 0
        for i in range(days):
            day = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
            if import_mb_from_xskt(day):
                imported += 1
        return imported

    def import_chotkq_days(self, days: int = 2) -> int:
        imported = 0
        for i in range(days):
            day = (date.today() - timedelta(days=i)).strftime("%Y-%m-%d")
            url = settings.chotkq % day
            self.als_chot_kq(url, day)
            imported += 1
        return imported

    def import_caudep_full(self, max_limit: int = 15) -> dict:
        day = date.today().strftime("%Y-%m-%d")
        limitday = self.limit_caudep(settings.caudep_page_url)
        cd: dict = {"ngaychot": day}
        for limit, nhay, lon in iter_caudep_combinations(max_limit):
            url = settings.caudep_url % (limit, day, nhay, lon)
            self.als_caudep(cd, url, limit, day, nhay, lon)
        self.imp_caudep(cd)
        return {"limitday": limitday}

    def import_rss_mn(self) -> int:
        from app.services.xskt_service import parse_draw_date_from_link
        from app.utils.http_util import obtain_content

        content = obtain_content(settings.rss_mn_url)
        if not content:
            return 0
        feed = feedparser.parse(content)
        imported = 0
        for entry in feed.entries:
            ngaychot = self.parse_date(entry.title)
            if not validate_string(ngaychot):
                continue
            draw_date = parse_draw_date_from_link(getattr(entry, "link", "")) or date.today().strftime("%Y-%m-%d")
            description = getattr(entry, "description", "") or entry.get("summary", "")
            lotto = self.parse_number(description, ngaychot)
            rbk_repo.insert_ket_qua_mn(lotto, ngaychot, draw_date)
            imported += 1
        return imported

    def import_rss_mt(self) -> int:
        from app.services.xskt_service import parse_draw_date_from_link
        from app.utils.http_util import obtain_content

        content = obtain_content(settings.rss_mt_url)
        if not content:
            return 0
        feed = feedparser.parse(content)
        imported = 0
        for entry in feed.entries:
            ngaychot = self.parse_date_mt(entry.title)
            if not validate_string(ngaychot):
                continue
            draw_date = parse_draw_date_from_link(getattr(entry, "link", "")) or date.today().strftime("%Y-%m-%d")
            description = getattr(entry, "description", "") or entry.get("summary", "")
            lotto = self.parse_number_mt(description, ngaychot)
            rbk_repo.insert_ket_qua_mt(lotto, ngaychot, draw_date)
            imported += 1
        return imported

    def import_rss_mb(self) -> int:
        from app.services.xskt_service import import_mb_from_xskt, parse_draw_date_from_link
        from app.utils.http_util import obtain_content

        content = obtain_content(settings.rss_mb_url)
        if not content:
            return 0
        feed = feedparser.parse(content)
        imported = 0
        for entry in feed.entries:
            draw_date = parse_draw_date_from_link(getattr(entry, "link", ""))
            if not draw_date:
                continue
            if import_mb_from_xskt(draw_date):
                imported += 1
        return imported

    def parse_chot_kq(self, url: str) -> list[dict]:
        results: list[dict] = []
        try:
            content = obtain_content(url)
            if not content:
                return results
            payload = json.loads(content)
            for obj in payload.get("list", []):
                ratio_de = ratio_lo = ratio_lobt = ratio_debt = ""
                ratio = obj.get("ratio")
                if isinstance(ratio, dict):
                    if ratio.get("de") and len(ratio["de"]) >= 2:
                        ratio_de = f"{ratio['de'][0]}/{ratio['de'][1]}"
                    if ratio.get("lo") and len(ratio["lo"]) >= 2:
                        ratio_lo = f"{ratio['lo'][0]}/{ratio['lo'][1]}"
                    if ratio.get("lobt") and len(ratio["lobt"]) >= 2:
                        ratio_lobt = f"{ratio['lobt'][0]}/{ratio['lobt'][1]}"
                    if ratio.get("debt") and len(ratio["debt"]) >= 2:
                        ratio_debt = f"{ratio['debt'][0]}/{ratio['debt'][1]}"

                rank = 0
                if "rank" in obj and isinstance(obj["rank"], int):
                    rank = hash(obj["rank"])

                item = {
                    "lo": [str(v) for v in obj.get("lo", [])],
                    "lodau": [str(v) for v in obj.get("lodau", [])],
                    "lodit": [str(v) for v in obj.get("lodit", [])],
                    "lobt": obj.get("lobt", ""),
                    "dedau": [str(v) for v in obj.get("dedau", [])],
                    "dedit": [str(v) for v in obj.get("dedit", [])],
                    "debt": obj.get("debt", ""),
                    "email": obj.get("email", ""),
                    "name": obj.get("name", ""),
                    "rank": rank,
                    "ratio_de": ratio_de,
                    "ratio_lo": ratio_lo,
                    "ratio_lobt": ratio_lobt,
                    "ratio_debt": ratio_debt,
                }
                results.append(item)
        except Exception as exc:
            logger.error("%s", exc)
        return results

    def ket_qua_sx(self, url: str) -> dict:
        kq = {f"kq{i}": "" for i in range(27)}
        kq.update({f"dau{i}": "" for i in range(10)})
        kq.update({f"dit{i}": "" for i in range(10)})
        kq["kqAr"] = []
        try:
            content = obtain_content(url)
            if not content:
                return kq
            content = content[17:202].replace('"', "")
            prizes = content.split(",")
            if len(prizes) < 27:
                return kq

            last_two = [p[-2:] for p in prizes[:27]]
            last_two.sort()
            kq["kqAr"] = last_two

            dau = {i: [] for i in range(10)}
            dit = {i: [] for i in range(10)}
            for idx, prize in enumerate(prizes[:27]):
                kq[f"kq{idx}"] = prize
                self._parsing_number(dau, dit, prize[-2:])

            for bucket in (dau, dit):
                for i in range(10):
                    bucket[i].sort()

            for i in range(10):
                kq[f"dau{i}"] = str(dau[i])
                kq[f"dit{i}"] = str(dit[i])
        except Exception as exc:
            logger.error("%s", exc)
        return kq

    def trend_arr(self, url: str) -> list[str]:
        values: list[str] = []
        try:
            response = obtain_content(url)
            if not response:
                return values
            soup = BeautifulSoup(response, "html.parser")
            for element in soup.select(".trend_number"):
                values.append(element.decode_contents())
        except Exception as exc:
            logger.error("%s", exc)
        return values

    def caudep_arr(self, url: str) -> list[str]:
        values: list[str] = []
        try:
            if not url:
                return values
            response = obtain_content(url)
            if not response:
                return values
            soup = BeautifulSoup(response, "html.parser")
            for element in soup.select(".a_cau"):
                values.append(element.decode_contents())
        except Exception as exc:
            logger.error("%s", exc)
        return values

    def parse_date(self, title: str) -> str:
        try:
            date_part = title.replace("KẾT QUẢ XỔ SỐ MIỀN NAM NGÀY ", "")[:5]
            thu = title[title.index("(") + 1 : title.index(")")]
            return f"{thu}, {date_part}"
        except Exception:
            return ""

    def parse_date_mt(self, title: str) -> str:
        try:
            date_part = title.replace("KẾT QUẢ XỔ SỐ MIỀN TRUNG NGÀY ", "")[:5]
            thu = title[title.index("(") + 1 : title.index(")")]
            return f"{thu}, {date_part}"
        except Exception:
            return ""

    def parse_number(self, value: str, ngaychot: str) -> list[dict]:
        results: list[dict] = []
        try:
            ketqua_str = value.replace("\n", "")
            first = ketqua_str.index("[")
            second = ketqua_str.index("[", first + 1)
            third = ketqua_str.index("[", second + 1)
            four = ketqua_str.find("[", third + 1)

            first_str = ketqua_str[first:second]
            second_str = ketqua_str[second:third]
            third_str = ketqua_str[third:]
            if four > 0:
                third_str = ketqua_str[third:four]
                four_str = ketqua_str[four:]
                results.append(self._parse_ket_qua_mn(four_str, ngaychot))

            results.extend(
                [
                    self._parse_ket_qua_mn(first_str, ngaychot),
                    self._parse_ket_qua_mn(second_str, ngaychot),
                    self._parse_ket_qua_mn(third_str, ngaychot),
                ]
            )
        except Exception as exc:
            logger.exception(exc)
        return results

    def parse_number_mt(self, value: str, ngaychot: str) -> list[dict]:
        results: list[dict] = []
        try:
            ketqua_str = value.replace("\n", "")
            first = ketqua_str.index("[")
            second = ketqua_str.index("[", first + 1)
            first_str = ketqua_str[first:second]
            second_str = ketqua_str[second:]
            results.append(self._parse_ket_qua_mt(first_str, ngaychot))
            results.append(self._parse_ket_qua_mt(second_str, ngaychot))
        except Exception as exc:
            logger.exception(exc)
        return results

    def _parse_ket_qua_mn(self, first_str: str, ngaychot: str) -> dict:
        kq: dict = {f"kq{i}": "" for i in range(18)}
        try:
            location = first_str[first_str.index("[") + 1 : first_str.index("]")]
            s = first_str[first_str.index("]") :]
            kq["kq0"] = s[s.index("ĐB:") + 3 : s.index("1:")].strip()
            s = s[s.index("1:") :]
            kq["kq1"] = s[s.index("1:") + 3 : s.index("2:")].strip()
            s = s[s.index("2:") :]
            kq["kq2"] = s[s.index("2:") + 3 : s.index("3:")].strip()
            s = s[s.index("3:") :]
            kq["kq3"] = s[s.index("3:") + 3 : s.index("3:") + 8].strip()
            kq["kq4"] = s[s.index("-") + 2 : s.index("4:")].strip()
            s = s[s.index("4:") :]
            kq["kq5"] = s[s.index("4:") + 3 : s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq6"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq7"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq8"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq9"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq10"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq11"] = s[: s.index("5:")].strip()
            s = s[s.index("5:") + 3 :]
            kq["kq12"] = s[: s.index("6:")].strip()
            s = s[s.index("6:") + 2 :]
            kq["kq13"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq14"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq15"] = s[: s.index("7:")].strip()
            s = s[s.index("7:") + 2 :]
            kq["kq16"] = s[: s.index("8:")].strip()
            s = s[s.index("8:") + 2 :]
            kq["kq17"] = s[:3].strip()
            kq["location"] = location
            kq["ngaychot"] = ngaychot
        except Exception as exc:
            logger.exception(exc)
        return kq

    def _parse_ket_qua_mt(self, first_str: str, ngaychot: str) -> dict:
        kq: dict = {f"kq{i}": "" for i in range(18)}
        try:
            location = first_str[first_str.index("[") + 1 : first_str.index("]")]
            s = first_str[first_str.index("]") :]
            kq["kq0"] = s[s.index("ĐB:") + 3 : s.index("1:")].strip()
            s = s[s.index("1:") :]
            kq["kq1"] = s[s.index("1:") + 3 : s.index("2:")].strip()
            s = s[s.index("2:") :]
            kq["kq2"] = s[s.index("2:") + 3 : s.index("3:")].strip()
            s = s[s.index("3:") :]
            kq["kq3"] = s[s.index("3:") + 3 : s.index("3:") + 8].strip()
            kq["kq4"] = s[s.index("-") + 2 : s.index("4:")].strip()
            s = s[s.index("4:") :]
            kq["kq5"] = s[s.index("4:") + 3 : s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq6"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq7"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq8"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq9"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq10"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq11"] = s[: s.index("5:")].strip()
            s = s[s.index("5:") + 3 :]
            kq["kq12"] = s[: s.index("6:")].strip()
            s = s[s.index("6:") + 2 :]
            kq["kq13"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq14"] = s[: s.index("-")].strip()
            s = s[s.index("-") + 2 :]
            kq["kq15"] = s[: s.index("7:")].strip()
            s = s[s.index("7:") + 2 :]
            kq["kq16"] = s[: s.index("8:")].strip()
            s = s[s.index("8:") + 2 :]
            kq["kq17"] = s[:].strip()
            kq["location"] = location
            kq["ngaychot"] = ngaychot
        except Exception as exc:
            logger.exception(exc)
        return kq

    def _parsing_number(self, dau: dict, dit: dict, val: str) -> None:
        if not validate_string(val):
            return
        try:
            val_int = int(val)
            dit[val_int % 10].append(val)
            dau[int(val_int / 10)].append(val)
        except Exception:
            pass


rbk_service = RbkService()

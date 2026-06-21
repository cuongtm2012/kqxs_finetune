from app.repositories.kqxs_repo import kqxs_repo


class KqxsService:
    def get_chot_kq(self, ngaychot: str, email: str, name: str, skip: int, limit: int):
        return kqxs_repo.get_chot_kq(ngaychot, email, name, skip, limit)

    def get_ket_qua(self, ngaychot: str, skip: int, limit: int):
        return kqxs_repo.get_ket_qua(ngaychot, skip, limit)

    def get_trending(self, ngaychot: str):
        return kqxs_repo.get_trending(ngaychot)

    def get_caudep(self, ngaychot: str, limit: int, nhay: int, lon: int):
        return kqxs_repo.get_caudep(ngaychot, limit, nhay, lon)

    def get_ket_qua_mn(self, ngaychot: str):
        return kqxs_repo.get_ket_qua_mn(ngaychot)

    def get_ket_qua_mt(self, ngaychot: str):
        return kqxs_repo.get_ket_qua_mt(ngaychot)


kqxs_service = KqxsService()

from app.odoo.source_service import SourceService


class FakeOdooClient:
    database, password = "db", "secret"
    def authenticate(self): return 9
    def call(self, *args):
        return [{"id": 3, "display_name": "Nhóm Toán", "network": "facebook", "group_code": "12345"}]


def test_source_service_uses_configured_odoo_field_mapping():
    service = SourceService(FakeOdooClient(), "x.source", name_field="display_name", platform_field="network",
        external_id_field="group_code", enabled_field="active")
    source = service.list_enabled()[0]
    assert source.name == "Nhóm Toán"
    assert source.external_id == "12345"

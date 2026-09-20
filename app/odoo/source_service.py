from app.schemas import Source


class SourceService:
    """Maps the configured Odoo source model into the application schema."""
    def __init__(self, client, model: str = "social.tutor.source", *, name_field: str = "name",
                 platform_field: str = "platform", external_id_field: str = "facebook_group_id",
                 enabled_field: str = "enabled"):
        self.client, self.model = client, model
        self.name_field, self.platform_field = name_field, platform_field
        self.external_id_field, self.enabled_field = external_id_field, enabled_field

    def list_enabled(self) -> list[Source]:
        uid = self.client.authenticate()
        fields = [self.name_field, self.platform_field, self.external_id_field]
        records = self.client.call("object", "execute_kw", self.client.database, uid, self.client.password,
            self.model, "search_read", [[(self.enabled_field, "=", True)]], {"fields": fields})
        return [Source(id=str(item["id"]), name=item[self.name_field],
            platform=item.get(self.platform_field) or "facebook",
            external_id=str(item[self.external_id_field]) if item.get(self.external_id_field) else None)
            for item in records]

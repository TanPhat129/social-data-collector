import yaml

from app.group_candidate_service import GroupCandidateService


class Store:
    def __init__(self): self.approved = []
    def list_group_candidates(self): return []
    def approve_group_candidate(self, candidate_id): self.approved.append(candidate_id)
    def record_group_event(self, candidate_id, account_id, action, detail=None): pass


def test_approve_accessible_candidate_adds_source_and_assignment(tmp_path):
    path = tmp_path / "accounts.yaml"
    path.write_text("""accounts:
  - {id: fb_001, facebook_uid: "1001", profile_path: .secrets/facebook-profiles/1001}
pools:
  - {id: pilot, account_ids: [fb_001]}
sources: []
assignments: []
""", encoding="utf-8")
    candidate = {"candidate_id": 7, "canonical_group_url": "https://www.facebook.com/groups/12345",
                 "group_name": "Nhóm test", "access_status": "ACCESSIBLE"}
    store = Store()
    source_id = GroupCandidateService(store, str(path)).approve_and_assign(candidate, "fb_001", 2, "pilot")
    saved = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert source_id == "fb_group_12345"
    assert saved["sources"][0]["source_url"] == candidate["canonical_group_url"]
    assert saved["assignments"][0]["shard"] == 2
    assert store.approved == [7]
